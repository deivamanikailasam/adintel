"""The approval endpoint, checked in code. When someone clicks Approve, the server checks, in order:

1. It is still pending and not expired.
2. **The typed exposure matches** the recommendation's exposure (stops blind clicking).
3. The approver's role and personal limit cover this exposure and risk.
4. Above the threshold, a **second, different approver** is required (four-eyes).
5. Not in a blackout window.
6. **Brand constraints still pass now**, not just at 2 AM.
7. **The live ad entity hasn't changed**: its snapshot hash matches the one the recommendation was made on.

Then the approval is signed (HMAC), audit-logged and queued to the executor, which has no LLM. A failed
check is audit-logged with the check's name and raises ``ApprovalError``.
"""

from __future__ import annotations

import logging
from typing import Any

from adintel.approvals import constraints
from adintel.approvals.matrix import can_approve, requirement
from adintel.audit import AuditLog
from adintel.config import get_settings
from adintel.connectors import get_connector
from adintel.core.clock import utcnow
from adintel.core.errors import AdIntelError, ApprovalError
from adintel.core.hashing import hmac_sign
from adintel.domain.enums import AuditAction, RecommendationStatus, Role
from adintel.domain.models import Approval, BrandRules, Recommendation, User
from adintel.observability.metrics import RECOMMENDATION_DECISIONS, REJECTION_REASONS
from adintel.queueing import EXECUTIONS, get_queue
from adintel.security.secrets import SecretStore
from adintel.storage.base import Database
from adintel.storage.tenant_repo import TenantScopedRepo

log = logging.getLogger(__name__)

REJECTION_CATEGORIES = ("wrong_diagnosis", "right_diagnosis_wrong_action", "violates_unstated_preference",
                        "poorly_explained", "stale", "other")
PENDING = (RecommendationStatus.PENDING_APPROVAL, RecommendationStatus.AWAITING_SECOND_APPROVAL)


def approval_payload(a: Approval) -> dict[str, Any]:
    """The canonical fields covered by the signature."""
    return a.model_dump(mode="json", exclude={"signature"})


class ApprovalService:
    def __init__(self, db: Database, tenant_id: str) -> None:
        self.db = db
        self.tenant_id = tenant_id
        self.recs = TenantScopedRepo(db, "recommendations", tenant_id)
        self.approvals = TenantScopedRepo(db, "approvals", tenant_id)
        self.audit = AuditLog(db, tenant_id, system_version=get_settings().system_version)

    # ---- helpers -----------------------------------------------------------------------------------
    def _rec(self, rec_id: str) -> Recommendation:
        doc = self.recs.find_one({"recommendation_id": rec_id})
        if doc is None:
            raise ApprovalError("exists", "recommendation not found")
        return Recommendation.from_doc(doc)

    def _deny(self, rec: Recommendation, user: User, check: str, msg: str) -> ApprovalError:
        self.audit.append(AuditAction.APPROVAL_DENIED, actor_type="human", actor_id=user.user_id,
                          subject_type="recommendation", subject_id=rec.recommendation_id, run_id=rec.run_id,
                          details={"check": check, "message": msg})
        log.warning("approval_denied", extra={"check": check, "recommendation_id": rec.recommendation_id})
        return ApprovalError(check, msg)

    def _live(self, rec: Recommendation) -> dict[str, dict[str, Any]]:
        cred = SecretStore().get(self.tenant_id, str(rec.platform), "read")
        conn = get_connector(rec.platform)
        ids = [i for i in (rec.source_entity_id, rec.target_entity_id) if i]
        return {i: conn.get_entity(cred, rec.brand_id, i) for i in ids}

    # ---- approve -----------------------------------------------------------------------------------
    def approve(self, rec_id: str, user: User, *, typed_exposure_usd: float,
                modified_amount_usd_per_day: float | None = None) -> dict[str, Any]:
        rec = self._rec(rec_id)
        now = utcnow()
        # 1. pending and not expired
        if rec.status not in PENDING:
            raise self._deny(rec, user, "pending", f"recommendation is {rec.status}")
        if now > rec.expires_at:
            self.recs.update_one({"recommendation_id": rec_id}, {"$set": {"status": str(RecommendationStatus.EXPIRED)}})
            self.audit.append(AuditAction.RECOMMENDATION_EXPIRED, actor_type="system", actor_id="system:approvals",
                              subject_type="recommendation", subject_id=rec_id, run_id=rec.run_id)
            RECOMMENDATION_DECISIONS.labels(decision="expired").inc()
            raise self._deny(rec, user, "not_expired", "recommendation has expired")
        brand = TenantScopedRepo(self.db, "brands", self.tenant_id).find_one({"brand_id": rec.brand_id}) or {}
        rules_doc = TenantScopedRepo(self.db, "brand_rules", self.tenant_id).find_one({"brand_id": rec.brand_id})
        rules = BrandRules.from_doc(rules_doc) if rules_doc else BrandRules(tenant_id=self.tenant_id,
                                                                                  brand_id=rec.brand_id)
        amount = rec.amount_usd_per_day
        if modified_amount_usd_per_day is not None:
            if rec.status == RecommendationStatus.AWAITING_SECOND_APPROVAL:
                raise self._deny(rec, user, "modification", "the second approver cannot modify the amount")
            if not 0 < abs(modified_amount_usd_per_day) <= abs(rec.amount_usd_per_day) + 0.005:
                raise self._deny(rec, user, "modification", "a modification may only reduce the amount")
            amount = modified_amount_usd_per_day
        live = self._live(rec)
        exposure = constraints.exposure_usd(rec.action_type, amount, live, rec.target_entity_id)
        pending_doc = self.recs.find_one({"recommendation_id": rec_id}) or {}
        first = pending_doc.get("first_approval")
        if first:
            exposure = float(first["exposure_usd"])
            amount = float(first["amount_usd_per_day"])
        # 2. typed exposure matches
        if abs(typed_exposure_usd - exposure) > 0.005:
            raise self._deny(rec, user, "typed_exposure", f"typed ${typed_exposure_usd:,.2f} does not match the "
                                                          f"exposure ${exposure:,.2f}/day")
        # 3. role and limit
        ok, why = can_approve(user, rec, exposure, brand.get("assigned_am"))
        if not ok:
            raise self._deny(rec, user, "authority", why)
        req = requirement(rec, exposure)
        # 4. four-eyes
        if first and first["approver_id"] == user.user_id:
            raise self._deny(rec, user, "second_approver", "the second approver must be a different person")
        if first and Role.HEAD_OF_PERFORMANCE not in user.roles:
            raise self._deny(rec, user, "second_approver", "the second approver must be Head of Performance")
        # 5. blackout
        reason = constraints.in_blackout(rules, now)
        if reason:
            raise self._deny(rec, user, "blackout", f"blackout window: {reason}")
        # 6. constraints still pass now
        violations = constraints.check(action=rec.action_type, source=rec.source_entity_id, target=rec.target_entity_id,
                                       amount=amount, rules=rules, entities=live,
                                       citations=[c.chunk_id for c in rec.citations],
                                       retrieved_ids=[c.chunk_id for c in rec.citations], now=now)
        if violations:
            raise self._deny(rec, user, "constraints_now", "; ".join(violations))
        # 7. live entity unchanged
        ids = [i for i in (rec.source_entity_id, rec.target_entity_id) if i]
        if constraints.snapshot_hash(live, ids) != rec.entity_snapshot_hash:
            raise self._deny(rec, user, "snapshot", "the live ad entity changed since the recommendation was made")

        if req.second_approver and not first:
            self.recs.update_one({"recommendation_id": rec_id}, {"$set": {
                "status": str(RecommendationStatus.AWAITING_SECOND_APPROVAL),
                "first_approval": {"approver_id": user.user_id, "at": now.isoformat(), "exposure_usd": exposure,
                                   "amount_usd_per_day": amount}}})
            self.audit.append(AuditAction.RECOMMENDATION_APPROVED, actor_type="human", actor_id=user.user_id,
                              subject_type="recommendation", subject_id=rec_id, run_id=rec.run_id,
                              details={"stage": "first", "exposure_usd": exposure, "requirement": req.description})
            return {"status": str(RecommendationStatus.AWAITING_SECOND_APPROVAL), "requirement": req.description}

        approval = Approval(tenant_id=self.tenant_id, recommendation_id=rec_id,
                            approver_id=first["approver_id"] if first else user.user_id,
                            second_approver_id=user.user_id if first else None,
                            second_approved_at=now if first else None, typed_exposure_usd=typed_exposure_usd,
                            modified_amount_usd_per_day=amount if abs(amount - rec.amount_usd_per_day) > 0.005 else None,
                            snapshot_hash=rec.entity_snapshot_hash)
        approval.signature = hmac_sign(get_settings().approval_signing_key, approval_payload(approval))
        self.approvals.insert(approval.model_dump(mode="json"))
        self.recs.update_one({"recommendation_id": rec_id}, {"$set": {
            "status": str(RecommendationStatus.APPROVED), "approval_id": approval.approval_id,
            "approved_amount_usd_per_day": amount, "approved_at": now.isoformat()}})
        self.audit.append(AuditAction.RECOMMENDATION_SECOND_APPROVAL if first else AuditAction.RECOMMENDATION_APPROVED,
                          actor_type="human", actor_id=user.user_id, subject_type="recommendation",
                          subject_id=rec_id, run_id=rec.run_id,
                          details={"approval_id": approval.approval_id, "exposure_usd": exposure,
                                   "modified": approval.modified_amount_usd_per_day is not None})
        decision = "modified" if approval.modified_amount_usd_per_day is not None else "approved"
        RECOMMENDATION_DECISIONS.labels(decision=decision).inc()
        TenantScopedRepo(self.db, "feedback", self.tenant_id).insert({
            "kind": f"recommendation_{decision}", "recommendation_id": rec_id, "brand_id": rec.brand_id,
            "run_id": rec.run_id, "user_id": user.user_id, "original_amount": rec.amount_usd_per_day,
            "approved_amount": amount, "created_at": now.isoformat()})
        get_queue(EXECUTIONS).send({"tenant_id": self.tenant_id, "recommendation_id": rec_id,
                                    "approval_id": approval.approval_id}, dedup_id=rec_id)
        return {"status": str(RecommendationStatus.APPROVED), "approval_id": approval.approval_id,
                "queued_for_execution": True}

    # ---- reject ------------------------------------------------------------------------------------
    def reject(self, rec_id: str, user: User, *, category: str, note: str = "") -> dict[str, Any]:
        rec = self._rec(rec_id)
        if category not in REJECTION_CATEGORIES:
            raise ApprovalError("category", f"category must be one of {REJECTION_CATEGORIES}")
        if rec.status not in PENDING:
            raise self._deny(rec, user, "pending", f"recommendation is {rec.status}")
        if not set(user.roles) & {Role.ACCOUNT_MANAGER, Role.SENIOR_ACCOUNT_MANAGER, Role.HEAD_OF_PERFORMANCE}:
            raise self._deny(rec, user, "authority", "only account managers can reject")
        now = utcnow().isoformat()
        self.recs.update_one({"recommendation_id": rec_id}, {"$set": {
            "status": str(RecommendationStatus.REJECTED), "rejection": {"by": user.user_id, "category": category,
                                                                       "note": note[:1000], "at": now}}})
        self.audit.append(AuditAction.RECOMMENDATION_REJECTED, actor_type="human", actor_id=user.user_id,
                          subject_type="recommendation", subject_id=rec_id, run_id=rec.run_id,
                          details={"category": category})
        RECOMMENDATION_DECISIONS.labels(decision="rejected").inc()
        REJECTION_REASONS.labels(category=category).inc()
        TenantScopedRepo(self.db, "feedback", self.tenant_id).insert({
            "kind": "recommendation_rejected", "recommendation_id": rec_id, "brand_id": rec.brand_id,
            "run_id": rec.run_id, "user_id": user.user_id, "category": category, "note": note[:1000],
            "created_at": now})
        return {"status": str(RecommendationStatus.REJECTED)}

    def expire_stale(self) -> int:
        now = utcnow().isoformat()
        n = 0
        for doc in self.recs.find({"status": {"$in": [str(s) for s in PENDING]}}):
            if doc["expires_at"] < now:
                self.recs.update_one({"recommendation_id": doc["recommendation_id"]},
                                     {"$set": {"status": str(RecommendationStatus.EXPIRED)}})
                self.audit.append(AuditAction.RECOMMENDATION_EXPIRED, actor_type="system",
                                  actor_id="system:expiry", subject_type="recommendation",
                                  subject_id=doc["recommendation_id"], run_id=doc.get("run_id"))
                RECOMMENDATION_DECISIONS.labels(decision="expired").inc()
                n += 1
        return n


def load_user(db: Database, tenant_id: str, user_id: str) -> User:
    doc = TenantScopedRepo(db, "users", tenant_id).find_one({"user_id": user_id})
    if doc is None:
        raise AdIntelError(f"unknown user {user_id}")
    return User.from_doc(doc)
