"""Logical backup and restore that works for every storage backend (memory or MongoDB).

* ``backup`` writes every catalogued collection to a verifiable bundle (``ops/bundle.py``).
* ``restore`` refuses a bundle whose checksums don't match, refuses to write into a non-empty database
  unless ``force=True``, recreates indexes, and finishes by verifying every tenant's audit chain — a
  restore is only "done" when the history it restored is provably intact.
* ``restore_drill`` proves a backup is restorable without touching the live database: it restores into a
  fresh in-memory database and compares document counts and audit chains. Run it after every backup (the
  quarterly DR test in production uses the same idea with an Atlas restore).

For large MongoDB datasets prefer the native ``scripts/backup.sh`` (``mongodump``); this module is the
backend-independent path and the one the tests exercise.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from adintel.audit import verify_all_tenants
from adintel.config import get_settings
from adintel.core.clock import utcnow
from adintel.ops.bundle import read_bundle, verify_bundle, write_bundle
from adintel.storage.base import Database
from adintel.storage.collections import CATALOGUE, ensure_indexes
from adintel.storage.tenant_repo import SystemRepo

DATETIME_FIELDS = ("expire_at",)  # TTL indexes need real dates, not ISO strings


def backup(db: Database, out_root: Path) -> dict[str, Any]:
    stamp = utcnow().strftime("%Y%m%dT%H%M%SZ")
    out = out_root / stamp
    data = {c.name: SystemRepo(db, c.name, purpose="backup").find({}) for c in CATALOGUE}
    s = get_settings()
    manifest = write_bundle(
        out, data, meta={"kind": "backup", "system_version": s.system_version, "storage": s.storage}
    )
    return {"path": str(out), "documents": sum(f["documents"] for f in manifest["files"].values())}


def _revive(doc: dict[str, Any]) -> dict[str, Any]:
    for k in DATETIME_FIELDS:
        if isinstance(doc.get(k), str):
            doc[k] = datetime.fromisoformat(doc[k])
    return doc


def restore(db: Database, in_dir: Path, *, force: bool = False) -> dict[str, Any]:
    problems = verify_bundle(in_dir)
    if problems:
        raise ValueError(f"backup failed verification, nothing restored: {problems}")
    data = read_bundle(in_dir)
    existing = sum(SystemRepo(db, c, purpose="restore check").count({}) for c in data)
    if existing and not force:
        raise RuntimeError(f"target database is not empty ({existing} documents); pass force=True to overwrite")
    ensure_indexes(db)
    restored: dict[str, int] = {}
    for name, docs in data.items():
        coll = db.collection(name)
        if force:
            coll.delete_many({})
        if docs:
            coll.insert_many([_revive(d) for d in docs])
        restored[name] = len(docs)
    chains = verify_all_tenants(db)
    return {
        "restored": {k: v for k, v in restored.items() if v},
        "audit_chains_ok": all(c.ok for c in chains),
        "broken_chains": [c.tenant_id for c in chains if not c.ok],
    }


def restore_drill(in_dir: Path) -> dict[str, Any]:
    from adintel.storage.memory import MemoryDatabase

    scratch = MemoryDatabase()
    out = restore(scratch, in_dir)
    expected = {f: n for f, n in ((c, len(d)) for c, d in read_bundle(in_dir).items()) if n}
    out["counts_match"] = out["restored"] == expected
    out["passed"] = out["counts_match"] and out["audit_chains_ok"]
    return out
