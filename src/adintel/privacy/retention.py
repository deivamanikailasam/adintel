"""Retention enforcement: delete what the catalogue says we no longer need.

The retention period of every collection is declared once, in ``storage/collections.py``. This job turns
those declarations into deletes, daily, for both backends (MongoDB TTL indexes cover the ``expire_at``
collections in production; the memory backend has no TTL, so the job handles those too).

* **Never purged here:** ``audit_log``. Deleting old entries would break the hash chain; it is archived
  to write-once storage instead (``audit/archive.py``) and expires there.
* **Legal hold:** a tenant with ``legal_hold: true`` is skipped entirely (litigation, regulator request).
* Each purge is summarised in the ``_system`` audit chain (counts only, no content).
"""

from __future__ import annotations

import logging
import re
from datetime import date, timedelta
from typing import Any

from adintel.audit import AuditLog
from adintel.core.clock import utcnow
from adintel.domain.enums import AuditAction
from adintel.storage.base import Database
from adintel.storage.collections import CATALOGUE
from adintel.storage.tenant_repo import SystemRepo

log = logging.getLogger(__name__)

NEVER_PURGED = frozenset({"audit_log"})
TIME_FIELDS: dict[str, str] = {
    "metrics_daily": "date",
    "metrics_rollups": "date",
    "cost_events": "day",
    "run_events": "at",
    "approvals": "approved_at",
    "executions": "executed_at",
    "outcomes": "measured_at",
    "secret_access_log": "at",
}
_UNIT_DAYS = {"day": 1, "days": 1, "month": 31, "months": 31, "year": 366, "years": 366}


def retention_days(text: str) -> int | None:
    """``"25 months"`` → 775. Generous rounding: we never delete a day early. ``None`` = keep."""
    m = re.match(r"^\s*(\d+)\s+(days?|months?|years?)\b", text)
    return int(m.group(1)) * _UNIT_DAYS[m.group(2)] if m else None


def plan(today: date | None = None) -> list[dict[str, Any]]:
    today = today or utcnow().date()
    out = []
    for spec in CATALOGUE:
        days = retention_days(spec.retention)
        if days is None or spec.name in NEVER_PURGED:
            continue
        out.append(
            {
                "collection": spec.name,
                "field": TIME_FIELDS.get(spec.name, "created_at"),
                "retention": spec.retention,
                "cutoff": (today - timedelta(days=days)).isoformat(),
            }
        )
    return out


def held_tenants(db: Database) -> list[str]:
    return [t["tenant_id"] for t in SystemRepo(db, "tenants", purpose="legal hold check").find({"legal_hold": True})]


def purge(db: Database, *, today: date | None = None, dry_run: bool = False) -> dict[str, int]:
    held = held_tenants(db)
    counts: dict[str, int] = {}
    now = utcnow()
    for item in plan(today):
        repo = SystemRepo(db, item["collection"], purpose="retention purge")
        flt: dict[str, Any] = {item["field"]: {"$lt": item["cutoff"]}, "tenant_id": {"$nin": held}}
        n = _apply(repo, flt, dry_run)
        n += _apply(repo, {"expire_at": {"$lt": now}, "tenant_id": {"$nin": held}}, dry_run)
        if n:
            counts[item["collection"]] = n
    if not dry_run:
        AuditLog(db, "_system").append(
            AuditAction.RETENTION_PURGE,
            actor_type="system",
            actor_id="system:retention",
            subject_type="database",
            subject_id="all",
            details={"deleted": counts, "legal_hold_tenants": held},
        )
    return counts


def _apply(repo: SystemRepo, flt: dict[str, Any], dry_run: bool) -> int:
    try:
        return repo.count(flt) if dry_run else repo.delete_many(flt)
    except TypeError:
        # memory backend only: a field stored with a different type than the cutoff (MongoDB simply doesn't
        # match across types). Logged so a purge that silently does nothing is visible.
        log.warning("retention_type_mismatch", extra={"collection": repo.collection, "filter": str(flt)})
        return 0


def retention_job(db: Database) -> dict[str, int]:
    return purge(db)


__all__ = ["plan", "purge", "retention_days", "retention_job"]
