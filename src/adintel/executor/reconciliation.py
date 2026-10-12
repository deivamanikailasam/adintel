"""Nightly reconciliation: every executed change must match what was approved (SLO: 100%).
Any mismatch pages immediately (P1). No model is involved."""

from __future__ import annotations

from typing import Any

from adintel.audit import AuditLog
from adintel.connectors import get_connector
from adintel.domain.enums import AuditAction, Platform
from adintel.observability.alerts import Severity, raise_alert
from adintel.observability.metrics import EXECUTION_MISMATCHES
from adintel.security.secrets import SecretStore
from adintel.storage.base import Database
from adintel.storage.tenant_repo import SystemRepo, TenantScopedRepo


def reconcile(db: Database) -> dict[str, Any]:
    checked = mismatches = 0
    tenants = [t["tenant_id"] for t in SystemRepo(db, "tenants", purpose="execution reconciliation").find()]
    for t in tenants:
        for ex in TenantScopedRepo(db, "executions", t).find({"status": "succeeded"}):
            platform = Platform(ex["platform"])
            cred = SecretStore().get(t, str(platform), "read")
            conn = get_connector(platform)
            for w in ex["request"]["writes"]:
                checked += 1
                live = conn.get_entity(cred, ex["brand_id"], w["entity_id"])
                expected_ok = (
                    (live.get("status") == "PAUSED")
                    if w["op"] == "pause"
                    else (abs(float(live.get("daily_budget", -1)) - float(w["daily_budget"])) < 0.01)
                )
                approved = (
                    TenantScopedRepo(db, "recommendations", t).find_one({"recommendation_id": ex["recommendation_id"]})
                    or {}
                )
                if not expected_ok or approved.get("status") != "executed":
                    mismatches += 1
                    EXECUTION_MISMATCHES.inc()
                    AuditLog(db, t).append(
                        AuditAction.RECONCILIATION_MISMATCH,
                        actor_type="system",
                        actor_id="system:reconciliation",
                        subject_type="execution",
                        subject_id=ex["execution_id"],
                        details={"entity_id": w["entity_id"], "expected": w, "live": live},
                    )
                    raise_alert(
                        Severity.P1,
                        "Execution reconciliation mismatch",
                        tenant_id=t,
                        brand_id=ex["brand_id"],
                        details={"execution_id": ex["execution_id"], "entity_id": w["entity_id"]},
                    )
    return {"checked": checked, "mismatches": mismatches}
