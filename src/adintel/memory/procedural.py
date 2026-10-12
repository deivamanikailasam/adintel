"""Procedural memory — what makes AdIntel feel like it learns, without ever learning silently.

After an account manager dismisses three similar anomalies (same brand, campaign, metric and reason),
the system **proposes** a suppression rule. A senior person approves it; only then does anomaly
detection apply it. Every step is audited.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from adintel.audit import AuditLog
from adintel.core.clock import utcnow
from adintel.core.errors import AuthError
from adintel.core.ids import new_id
from adintel.domain.enums import AuditAction, Role
from adintel.domain.models import BrandRules, Suppression, User
from adintel.observability.metrics import ANOMALY_DISMISSALS
from adintel.storage.base import Database
from adintel.storage.tenant_repo import TenantScopedRepo

DISMISSAL_REASONS = ("planned_promo", "seasonal", "known_tracking_change", "noise", "other")
PROPOSAL_AFTER = 3
WINDOW = timedelta(days=90)


class ProceduralMemory:
    def __init__(self, db: Database, tenant_id: str) -> None:
        self.db = db
        self.tenant_id = tenant_id
        self.anomalies = TenantScopedRepo(db, "anomalies", tenant_id)
        self.proposals = TenantScopedRepo(db, "rule_proposals", tenant_id)
        self.audit = AuditLog(db, tenant_id)

    def dismiss(self, anomaly_id: str, user: User, *, reason: str, note: str = "") -> dict[str, Any]:
        if reason not in DISMISSAL_REASONS:
            raise ValueError(f"reason must be one of {DISMISSAL_REASONS}")
        a = self.anomalies.find_one({"anomaly_id": anomaly_id})
        if a is None:
            raise KeyError(anomaly_id)
        now = utcnow()
        self.anomalies.update_one({"anomaly_id": anomaly_id}, {"$set": {
            "status": "dismissed", "dismissal": {"by": user.user_id, "reason": reason, "note": note[:500],
                                                 "at": now.isoformat()}}})
        self.audit.append(AuditAction.ANOMALY_DISMISSED, actor_type="human", actor_id=user.user_id,
                          subject_type="anomaly", subject_id=anomaly_id, details={"reason": reason})
        ANOMALY_DISMISSALS.labels(reason=reason).inc()
        TenantScopedRepo(self.db, "feedback", self.tenant_id).insert({
            "kind": "anomaly_dismissed", "anomaly_id": anomaly_id, "brand_id": a["brand_id"], "reason": reason,
            "created_at": now.isoformat()})
        similar = [d for d in self.anomalies.find({"brand_id": a["brand_id"], "campaign_id": a["campaign_id"],
                                                   "metric": a["metric"], "status": "dismissed"})
                   if d.get("dismissal", {}).get("reason") == reason
                   and d["dismissal"]["at"] >= (now - WINDOW).isoformat()]
        proposal = None
        if len(similar) >= PROPOSAL_AFTER and reason in ("planned_promo", "seasonal"):
            key = {"brand_id": a["brand_id"], "campaign_id": a["campaign_id"], "metric": a["metric"],
                   "reason": reason}
            if not self.proposals.find_one({**key, "status": "proposed"}):
                proposal = {"proposal_id": new_id("prop"), **key, "status": "proposed",
                            "evidence_anomaly_ids": [d["anomaly_id"] for d in similar],
                            "description": f"Don't flag {a['metric']} changes on {a['entity_name']} ({reason}); "
                                           f"dismissed {len(similar)} times in 90 days.",
                            "month": now.month if reason == "seasonal" else None,
                            "created_at": now.isoformat()}
                self.proposals.insert(proposal)
                self.audit.append(AuditAction.RULE_PROPOSED, actor_type="system", actor_id="system:procedural",
                                  subject_type="rule_proposal", subject_id=proposal["proposal_id"], details=key)
        return {"dismissed": anomaly_id, "proposal": proposal}

    def decide(self, proposal_id: str, user: User, *, approve: bool) -> dict[str, Any]:
        if not set(user.roles) & {Role.SENIOR_ACCOUNT_MANAGER, Role.HEAD_OF_PERFORMANCE}:
            raise AuthError("only a senior account manager or Head of Performance may approve learned rules")
        p = self.proposals.find_one({"proposal_id": proposal_id, "status": "proposed"})
        if p is None:
            raise KeyError(proposal_id)
        now = utcnow()
        self.proposals.update_one({"proposal_id": proposal_id}, {"$set": {
            "status": "approved" if approve else "rejected", "decided_by": user.user_id, "decided_at": now.isoformat()}})
        if approve:
            rules_repo = TenantScopedRepo(self.db, "brand_rules", self.tenant_id)
            doc = rules_repo.find_one({"brand_id": p["brand_id"]})
            rules = BrandRules.from_doc(doc) if doc else BrandRules(tenant_id=self.tenant_id, brand_id=p["brand_id"])
            rules.suppressions.append(Suppression(description=p["description"], metric=p["metric"],
                                                  entity_id=p["campaign_id"], month=p.get("month"),
                                                  approved_by=user.user_id, approved_at=now))
            rules.version += 1
            rules_repo.update_one({"brand_id": p["brand_id"]}, {"$set": rules.model_dump(mode="json")}, upsert=True)
            self.audit.append(AuditAction.RULE_APPROVED, actor_type="human", actor_id=user.user_id,
                              subject_type="rule_proposal", subject_id=proposal_id,
                              details={"brand_rules_version": rules.version})
        return {"proposal_id": proposal_id, "status": "approved" if approve else "rejected"}
