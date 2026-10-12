"""Kill switches at four levels — global, tenant, brand, agent — checked at admission and before
every dispatch. Flipping one takes effect on the next hop of every in-flight run."""

from __future__ import annotations

from typing import Any

from adintel.audit import AuditLog
from adintel.core.clock import utcnow
from adintel.domain.enums import AuditAction
from adintel.observability.metrics import KILL_SWITCH_BLOCKS
from adintel.storage.base import Database
from adintel.storage.tenant_repo import SystemRepo

SCOPES = ("global", "tenant", "brand", "agent")


class KillSwitches:
    def __init__(self, db: Database) -> None:
        self._db = db
        self._repo = SystemRepo(db, "kill_switches", purpose="kill switch check")

    @staticmethod
    def _keys(tenant_id: str | None, brand_id: str | None, agent: str | None) -> list[tuple[str, str]]:
        keys = [("global", "*")]
        if tenant_id:
            keys.append(("tenant", tenant_id))
        if tenant_id and brand_id:
            keys.append(("brand", f"{tenant_id}/{brand_id}"))
        if agent:
            keys.append(("agent", agent))
        return keys

    def engaged(
        self, *, tenant_id: str | None = None, brand_id: str | None = None, agent: str | None = None
    ) -> str | None:
        """Return the first engaged scope (``"tenant:t1"``) or ``None``."""
        for scope, key in self._keys(tenant_id, brand_id, agent):
            doc = self._repo.find_one({"scope": scope, "key": key, "engaged": True})
            if doc:
                KILL_SWITCH_BLOCKS.labels(scope=scope).inc()
                return f"{scope}:{key}"
        return None

    def set(
        self, scope: str, key: str, engaged: bool, *, actor_id: str, reason: str, tenant_id_for_audit: str | None = None
    ) -> dict[str, Any]:
        if scope not in SCOPES:
            raise ValueError(f"scope must be one of {SCOPES}")
        doc = {
            "scope": scope,
            "key": key,
            "engaged": engaged,
            "reason": reason,
            "actor_id": actor_id,
            "updated_at": utcnow().isoformat(),
        }
        self._repo.update_one({"scope": scope, "key": key}, {"$set": doc}, upsert=True)
        audit_tenant = tenant_id_for_audit or (key.split("/")[0] if scope in ("tenant", "brand") else "_system")
        AuditLog(self._db, audit_tenant).append(
            AuditAction.KILL_SWITCH_CHANGED,
            actor_type="human",
            actor_id=actor_id,
            subject_type="kill_switch",
            subject_id=f"{scope}:{key}",
            details={"engaged": engaged, "reason": reason},
        )
        return doc

    def list(self) -> list[dict[str, Any]]:
        return self._repo.find({}, sort=[("scope", 1), ("key", 1)])
