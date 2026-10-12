"""Forward-only, recorded, locked data migrations.

Indexes are created idempotently at startup (``ensure_indexes``), so most changes need no migration. A
migration is for changing the *shape of existing documents* (backfilling a new field, renaming one,
splitting a collection) — the kind of change that must happen exactly once, in order, on every
environment, before the new code serves traffic.

Rules (enforced or checked here):

* **Ordered and recorded** — each run is written to ``schema_migrations`` with the checksum of its code;
  ``status`` warns if an applied migration's code was edited afterwards (drift).
* **One at a time** — a lock document in the same collection; a second runner refuses to start.
* **Idempotent** — every migration must be safe to re-run (filters select only un-migrated documents).
* **Forward-only** — there is no "down". The rollback is the backup taken immediately before
  (``adintel migrate --backup-dir backups``), restored with ``adintel restore``.
* **Expand, then contract** — add fields first (old and new code both work), remove old fields in a later
  release once nothing reads them. This is what makes blue/green deploys safe.

Production: CI runs ``adintel migrate --check`` (fails if anything is pending) and the deploy runs
``adintel migrate`` as a one-off ECS task before shifting traffic.
"""

from __future__ import annotations

import hashlib
import inspect
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from adintel.core.clock import utcnow
from adintel.storage.base import Database, DuplicateKey
from adintel.storage.tenant_repo import SystemRepo

log = logging.getLogger(__name__)
LOCK_ID = "__lock__"
STALE_LOCK = timedelta(minutes=30)


@dataclass(frozen=True)
class Migration:
    migration_id: str  # "0002_brand_profile_defaults" — sorted lexically
    description: str
    up: Callable[[Database], dict[str, Any]]

    @property
    def checksum(self) -> str:
        return hashlib.sha256(inspect.getsource(self.up).encode()).hexdigest()[:16]


class MigrationLocked(RuntimeError):
    pass


def _repo(db: Database) -> SystemRepo:
    return SystemRepo(db, "schema_migrations", purpose="schema migrations")


def registry() -> list[Migration]:
    from adintel.storage.migrations.versions import MIGRATIONS

    ids = [m.migration_id for m in MIGRATIONS]
    if ids != sorted(ids) or len(set(ids)) != len(ids):
        raise ValueError("migration ids must be unique and in order")
    return list(MIGRATIONS)


def status(db: Database) -> list[dict[str, Any]]:
    applied = {r["migration_id"]: r for r in _repo(db).find({"migration_id": {"$ne": LOCK_ID}})}
    out = []
    for m in registry():
        r = applied.get(m.migration_id)
        out.append(
            {
                "migration_id": m.migration_id,
                "description": m.description,
                "applied_at": r["applied_at"] if r else None,
                "drift": bool(r and r["checksum"] != m.checksum),
            }
        )
    return out


def pending(db: Database) -> list[Migration]:
    done = {r["migration_id"] for r in _repo(db).find({"migration_id": {"$ne": LOCK_ID}})}
    return [m for m in registry() if m.migration_id not in done]


def _acquire(db: Database, owner: str, break_stale: bool) -> None:
    repo = _repo(db)
    try:
        repo.insert({"migration_id": LOCK_ID, "owner": owner, "at": utcnow().isoformat()})
        return
    except DuplicateKey:
        lock = repo.find_one({"migration_id": LOCK_ID}) or {}
    held_since = str(lock.get("at", ""))
    stale = held_since and held_since < (utcnow() - STALE_LOCK).isoformat()
    if not (break_stale and stale):
        raise MigrationLocked(f"migrations locked by {lock.get('owner')} since {held_since}")
    log.warning("breaking_stale_migration_lock", extra={"owner": lock.get("owner"), "since": held_since})
    repo.update_one({"migration_id": LOCK_ID}, {"$set": {"owner": owner, "at": utcnow().isoformat()}})


def migrate(
    db: Database, *, dry_run: bool = False, owner: str = "cli", break_stale_lock: bool = False
) -> list[dict[str, Any]]:
    todo = pending(db)
    if dry_run or not todo:
        return [{"migration_id": m.migration_id, "would_apply": True} for m in todo]
    _acquire(db, owner, break_stale_lock)
    results = []
    try:
        for m in pending(db):  # re-read under the lock
            t0 = time.perf_counter()
            result = m.up(db)
            rec = {
                "migration_id": m.migration_id,
                "description": m.description,
                "checksum": m.checksum,
                "applied_at": utcnow().isoformat(),
                "duration_ms": round((time.perf_counter() - t0) * 1000, 1),
                "result": result,
                "owner": owner,
            }
            _repo(db).insert(rec)
            log.info("migration_applied", extra={"migration_id": m.migration_id, "result": result})
            results.append(rec)
    finally:
        _repo(db).delete_many({"migration_id": LOCK_ID})
    return results
