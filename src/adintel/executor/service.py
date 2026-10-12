"""Executor: verify the signed approval → re-read live state → apply the change → record and audit.

* Refuses anything without a valid HMAC signature, an APPROVED recommendation, a matching snapshot hash,
  and no prior execution (executions are unique per recommendation).
* Writes retry **at most once**, and only when the platform rejected the call outright; a partly applied
  change is never retried automatically: it is marked failed and a human is paged.
"""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from adintel.approvals.constraints import in_blackout, snapshot_hash
from adintel.audit import AuditLog
from adintel.config import get_settings
from adintel.connectors import get_connector
from adintel.core.clock import utcnow
from adintel.core.errors import AdIntelError, ExecutionError, PlatformUnavailable
from adintel.core.hashing import hmac_verify
from adintel.domain.enums import ActionType, AuditAction, RecommendationStatus
from adintel.domain.models import Approval, BrandRules, Execution, Recommendation
from adintel.observability.alerts import Severity, raise_alert
from adintel.security.secrets import SecretStore
from adintel.storage.base import Database, DuplicateKey
from adintel.storage.tenant_repo import TenantScopedRepo

log = logging.getLogger(__name__)
EXECUTION_GRACE = timedelta(hours=6)  # an approval granted just before expiry may still execute shortly after


def plan_writes(rec: Recommendation, amount: float, live: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    if rec.action_type == ActionType.BUDGET_SHIFT:
        assert rec.source_entity_id
        src, tgt = live[rec.source_entity_id], live[rec.target_entity_id]
        # decrease first: if the second write fails, money was removed, never doubled
        return [{"op": "set_daily_budget", "entity_id": rec.source_entity_id,
                 "daily_budget": round(float(src["daily_budget"]) - amount, 2), "previous": src["daily_budget"]},
                {"op": "set_daily_budget", "entity_id": rec.target_entity_id,
                 "daily_budget": round(float(tgt["daily_budget"]) + amount, 2), "previous": tgt["daily_budget"]}]
    if rec.action_type == ActionType.BUDGET_CHANGE:
        tgt = live[rec.target_entity_id]
        return [{"op": "set_daily_budget", "entity_id": rec.target_entity_id,
                 "daily_budget": round(float(tgt["daily_budget"]) + amount, 2), "previous": tgt["daily_budget"]}]
    if rec.action_type == ActionType.PAUSE_ENTITY:
        return [{"op": "pause", "entity_id": rec.target_entity_id}]
    raise ExecutionError(f"unsupported action {rec.action_type}")


class Executor:
    def __init__(self, db: Database, tenant_id: str) -> None:
        self.db = db
        self.tenant_id = tenant_id
        self.recs = TenantScopedRepo(db, "recommendations", tenant_id)
        self.execs = TenantScopedRepo(db, "executions", tenant_id)
        self.audit = AuditLog(db, tenant_id, system_version=get_settings().system_version)

    def _refuse(self, rec_id: str, reason: str, run_id: str | None = None) -> dict[str, Any]:
        self.audit.append(AuditAction.EXECUTION_REFUSED, actor_type="system", actor_id="system:executor",
                          subject_type="recommendation", subject_id=rec_id, run_id=run_id, details={"reason": reason})
        log.error("execution_refused", extra={"recommendation_id": rec_id, "reason": reason})
        return {"status": "refused", "reason": reason}

    def execute(self, recommendation_id: str, approval_id: str) -> dict[str, Any]:
        rec_doc = self.recs.find_one({"recommendation_id": recommendation_id})
        apr_doc = TenantScopedRepo(self.db, "approvals", self.tenant_id).find_one({"approval_id": approval_id})
        if rec_doc is None or apr_doc is None:
            return self._refuse(recommendation_id, "recommendation or approval not found")
        rec = Recommendation.from_doc(rec_doc)
        approval = Approval.from_doc(apr_doc)
        payload = approval.model_dump(mode="json", exclude={"signature"})
        if not hmac_verify(get_settings().approval_signing_key, payload, approval.signature):
            raise_alert(Severity.P1, "Forged or tampered approval record", tenant_id=self.tenant_id,
                        details={"recommendation_id": recommendation_id}, audience="security")
            return self._refuse(recommendation_id, "approval signature invalid", rec.run_id)
        if approval.recommendation_id != recommendation_id or rec_doc.get("approval_id") != approval_id:
            return self._refuse(recommendation_id, "approval does not belong to this recommendation", rec.run_id)
        if rec.status != RecommendationStatus.APPROVED:
            return self._refuse(recommendation_id, f"recommendation is {rec.status}", rec.run_id)
        if utcnow() > rec.expires_at + EXECUTION_GRACE:
            return self._refuse(recommendation_id, "approval is too old to execute", rec.run_id)
        if self.execs.find_one({"recommendation_id": recommendation_id}):
            return self._refuse(recommendation_id, "already executed (replay)", rec.run_id)
        rules_doc = TenantScopedRepo(self.db, "brand_rules", self.tenant_id).find_one({"brand_id": rec.brand_id})
        if rules_doc and in_blackout(BrandRules.from_doc(rules_doc), utcnow()):
            return self._refuse(recommendation_id, "blackout window active", rec.run_id)

        cred = SecretStore().get(self.tenant_id, str(rec.platform), "write")
        conn = get_connector(rec.platform)
        ids = [i for i in (rec.source_entity_id, rec.target_entity_id) if i]
        live = {i: conn.get_entity(cred, rec.brand_id, i) for i in ids}  # re-read live state before writing
        if snapshot_hash(live, ids) != approval.snapshot_hash:
            return self._refuse(recommendation_id, "live entity changed after approval", rec.run_id)
        amount = float(rec_doc.get("approved_amount_usd_per_day", rec.amount_usd_per_day))
        writes = plan_writes(rec, amount, live)
        self.recs.update_one({"recommendation_id": recommendation_id},
                             {"$set": {"status": str(RecommendationStatus.EXECUTING)}})
        self.audit.append(AuditAction.EXECUTION_STARTED, actor_type="system", actor_id="system:executor",
                          subject_type="recommendation", subject_id=recommendation_id, run_id=rec.run_id,
                          details={"writes": writes, "approval_id": approval_id})
        applied: list[dict[str, Any]] = []
        error: str | None = None
        attempts = 0
        for w in writes:
            for attempt in (1, 2):
                attempts += 1
                try:
                    applied.append(conn.apply_change(cred, rec.brand_id, w))
                    break
                except PlatformUnavailable as exc:
                    if attempt == 1 and not applied:  # retry at most once, and never after a partial apply
                        continue
                    error = str(exc)
                    break
                except AdIntelError as exc:
                    error = str(exc)
                    break
            if error:
                break
        status = "succeeded" if not error else "failed"
        execution = Execution(tenant_id=self.tenant_id, brand_id=rec.brand_id, recommendation_id=recommendation_id,
                              approval_id=approval_id, platform=rec.platform, request={"writes": writes},
                              status=status, platform_response={"applied": applied}, error=error, attempts=attempts)
        try:
            self.execs.insert(execution.model_dump(mode="json"))
        except DuplicateKey:
            return self._refuse(recommendation_id, "concurrent execution detected", rec.run_id)
        new_status = RecommendationStatus.EXECUTED if not error else RecommendationStatus.EXECUTION_FAILED
        self.recs.update_one({"recommendation_id": recommendation_id}, {"$set": {
            "status": str(new_status), "execution_id": execution.execution_id}})
        self.audit.append(AuditAction.EXECUTION_SUCCEEDED if not error else AuditAction.EXECUTION_FAILED,
                          actor_type="system", actor_id="system:executor", subject_type="recommendation",
                          subject_id=recommendation_id, run_id=rec.run_id,
                          details={"execution_id": execution.execution_id, "applied": len(applied),
                                   "planned": len(writes), "error": error})
        TenantScopedRepo(self.db, "notifications", self.tenant_id).insert({
            "kind": "execution_result", "brand_id": rec.brand_id, "recommendation_id": recommendation_id,
            "audience": "account_manager", "title": f"Change {status}", "detail": error or "applied as approved",
            "created_at": utcnow().isoformat()})
        if error:
            sev = Severity.P1 if applied else Severity.P2
            raise_alert(sev, "Approved execution failed" + (" after a partial apply" if applied else ""),
                        tenant_id=self.tenant_id, brand_id=rec.brand_id,
                        details={"recommendation_id": recommendation_id, "error": error, "applied": len(applied)})
        return {"status": status, "execution_id": execution.execution_id, "error": error}
