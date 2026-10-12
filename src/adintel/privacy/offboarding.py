"""Tenant offboarding: an agency leaves — hand back their data, then delete it.

Order matters and every step is safe to re-run:

1. **Stop**: engage the tenant kill switch so nothing new starts.
2. **Export**: every tenant-scoped collection to a verifiable bundle (JSONL + SHA-256 manifest), which is
   what the agency receives.
3. **Delete**: every tenant-scoped document, except the legal records (approvals, executions, outcomes and
   the audit log — who authorised spending client money, and what was changed) which are kept for their
   7-year retention unless ``keep_legal_records=False`` (e.g. a contract that says otherwise).
4. **Revoke**: remove the tenant's local platform credentials (in production: delete the Secrets Manager
   entries and revoke the OAuth grants on each ad platform — a manual runbook step).
5. **Record**: mark the tenant inactive and write the offboarding to the ``_system`` audit chain.

Requires ``confirm == tenant_id`` so it can't be run against the wrong agency by a typo.
"""

from __future__ import annotations

import shutil
from datetime import timedelta
from pathlib import Path
from typing import Any

from adintel.audit import AuditLog
from adintel.config import get_settings
from adintel.core.clock import utcnow
from adintel.domain.enums import AuditAction
from adintel.harness.killswitch import KillSwitches
from adintel.ops.bundle import write_bundle
from adintel.storage.base import Database
from adintel.storage.collections import CATALOGUE
from adintel.storage.tenant_repo import SystemRepo

LEGAL_RECORDS = frozenset({"approvals", "executions", "outcomes", "audit_log"})


def offboard_tenant(
    db: Database,
    tenant_id: str,
    *,
    confirm: str,
    actor_id: str,
    out_dir: Path,
    keep_legal_records: bool = True,
) -> dict[str, Any]:
    if confirm != tenant_id:
        raise ValueError("confirmation does not match the tenant id; nothing was changed")
    tenants = SystemRepo(db, "tenants", purpose="tenant offboarding")
    if tenants.find_one({"tenant_id": tenant_id}) is None:
        raise LookupError(f"tenant {tenant_id} not found")

    KillSwitches(db).set(
        "tenant", tenant_id, True, actor_id=actor_id, reason="tenant offboarding", tenant_id_for_audit="_system"
    )

    scoped = [c.name for c in CATALOGUE if c.tenant_scoped]
    export = {c: SystemRepo(db, c, purpose="tenant offboarding export").find({"tenant_id": tenant_id}) for c in scoped}
    manifest = write_bundle(out_dir / tenant_id, export, meta={"tenant_id": tenant_id, "kind": "offboarding"})

    deleted: dict[str, int] = {}
    for c in scoped:
        if keep_legal_records and c in LEGAL_RECORDS:
            continue
        n = SystemRepo(db, c, purpose="tenant offboarding delete").delete_many({"tenant_id": tenant_id})
        if n:
            deleted[c] = n

    secrets = Path(get_settings().secrets_dir) / tenant_id
    revoked = secrets.is_dir()
    if revoked:
        shutil.rmtree(secrets)

    now = utcnow()
    tenants.update_one(
        {"tenant_id": tenant_id},
        {
            "$set": {
                "active": False,
                "offboarded_at": now.isoformat(),
                "legal_records_until": (now + timedelta(days=7 * 366)).isoformat() if keep_legal_records else None,
            }
        },
    )
    summary = {
        "tenant_id": tenant_id,
        "export_dir": str(out_dir / tenant_id),
        "exported": {f["collection"]: f["documents"] for f in manifest["files"].values()},
        "deleted": deleted,
        "kept_legal_records": sorted(LEGAL_RECORDS) if keep_legal_records else [],
        "local_credentials_removed": revoked,
    }
    AuditLog(db, "_system").append(
        AuditAction.TENANT_OFFBOARDED,
        actor_type="human",
        actor_id=actor_id,
        subject_type="tenant",
        subject_id=tenant_id,
        details={k: v for k, v in summary.items() if k != "export_dir"},
    )
    return summary
