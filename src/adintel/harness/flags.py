"""Per-tenant (and per-brand) feature flags: roll a capability out to one agency or one brand at a time.

Flags are not kill switches. A kill switch is an emergency brake that stops runs; a flag is a planned
rollout control that turns one capability on or off while everything else keeps working. A flag that turns
an agent off produces the same visible degradation as that agent being unavailable, so the client report
still says what was skipped.

Resolution order: brand override → tenant override → default below. Every change is audited.
"""

from __future__ import annotations

from typing import Any

from adintel.audit import AuditLog
from adintel.core.clock import utcnow
from adintel.domain.enums import AgentName, AuditAction
from adintel.storage.base import Database
from adintel.storage.tenant_repo import TenantScopedRepo

DEFAULTS: dict[str, bool] = {
    "agent.analyst": True,  # root-cause investigation (frontier model + sandbox)
    "agent.optimizer": True,  # budget proposals (frontier model + RAG); off = report only
    "chat.frontier_route": True,  # complex chat questions go to the frontier tier + RAG
    "outcome_tracking": True,  # measure actual vs predicted impact 14 days after execution
}

AGENT_FLAGS: dict[AgentName, str] = {
    AgentName.ANALYST: "agent.analyst",
    AgentName.OPTIMIZER: "agent.optimizer",
}


class FeatureFlags:
    def __init__(self, db: Database, tenant_id: str) -> None:
        self._db = db
        self.tenant_id = tenant_id
        self._repo = TenantScopedRepo(db, "feature_flags", tenant_id)

    def enabled(self, flag: str, *, brand_id: str | None = None) -> bool:
        if flag not in DEFAULTS:
            raise KeyError(f"unknown feature flag {flag!r}")
        if brand_id:
            doc = self._repo.find_one({"flag": flag, "brand_id": brand_id})
            if doc:
                return bool(doc["enabled"])
        doc = self._repo.find_one({"flag": flag, "brand_id": None})
        return bool(doc["enabled"]) if doc else DEFAULTS[flag]

    def set(
        self, flag: str, enabled: bool, *, actor_id: str, reason: str, brand_id: str | None = None
    ) -> dict[str, Any]:
        if flag not in DEFAULTS:
            raise KeyError(f"unknown feature flag {flag!r}")
        doc = {
            "flag": flag,
            "brand_id": brand_id,
            "enabled": enabled,
            "reason": reason,
            "actor_id": actor_id,
            "updated_at": utcnow().isoformat(),
        }
        self._repo.update_one({"flag": flag, "brand_id": brand_id}, {"$set": doc}, upsert=True)
        AuditLog(self._db, self.tenant_id).append(
            AuditAction.FEATURE_FLAG_CHANGED,
            actor_type="human",
            actor_id=actor_id,
            subject_type="feature_flag",
            subject_id=f"{flag}@{brand_id or '*'}",
            details={"enabled": enabled, "reason": reason},
        )
        return {k: v for k, v in doc.items()}

    def effective(self, *, brand_id: str | None = None) -> dict[str, bool]:
        return {f: self.enabled(f, brand_id=brand_id) for f in DEFAULTS}

    def overrides(self) -> list[dict[str, Any]]:
        return self._repo.find({}, sort=[("flag", 1)])
