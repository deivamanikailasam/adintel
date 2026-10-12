"""Write-once archive of the audit hash chain — the local alternative to S3 Object Lock.

Why the chain alone is not enough: an attacker with database write access could rewrite *every* entry
after the one they changed, recomputing the hashes, and the chain would still verify. The defence is an
anchor outside the database that nobody can rewrite: periodic segments of the chain copied to write-once
storage. If the database later disagrees with the archive, the database was tampered with.

Layout (``ADINTEL_AUDIT_ARCHIVE_DIR``)::

    <tenant>/000001-000143.jsonl          one segment: entries seq 1..143, made read-only (0444)
    <tenant>/000001-000143.jsonl.sha256   checksum of the segment
    <tenant>/000144-000150.jsonl          the next nightly export continues where the last one ended

When ``ADINTEL_AUDIT_ARCHIVE_S3_BUCKET`` is set, every new segment is also uploaded with Object Lock
retention (MinIO in Docker Compose locally; Amazon S3 in compliance mode in production), which makes the
copy undeletable for the retention period — even by an administrator in compliance mode.
"""

from __future__ import annotations

import hashlib
import logging
import os
import stat
from dataclasses import dataclass, field
from datetime import timedelta
from pathlib import Path
from typing import Any

from adintel.audit.chain import GENESIS, AuditEntry
from adintel.config import get_settings
from adintel.core.clock import utcnow
from adintel.storage.base import Database
from adintel.storage.tenant_repo import SystemRepo

log = logging.getLogger(__name__)


@dataclass
class ArchiveCheck:
    tenant_id: str
    ok: bool
    entries: int = 0
    segments: int = 0
    problems: list[str] = field(default_factory=list)


def _root(archive_dir: Path | None) -> Path:
    return Path(archive_dir or get_settings().audit_archive_dir)


def _segments(tdir: Path) -> list[Path]:
    return sorted(p for p in tdir.glob("*.jsonl")) if tdir.is_dir() else []


def _last_seq(tdir: Path) -> int:
    segs = _segments(tdir)
    return int(segs[-1].stem.split("-")[1]) if segs else 0


def _read(seg: Path) -> list[AuditEntry]:
    with seg.open(encoding="utf-8") as f:
        return [AuditEntry.model_validate_json(line) for line in f if line.strip()]


def export_tenant(db: Database, tenant_id: str, *, archive_dir: Path | None = None) -> dict[str, Any] | None:
    """Append entries newer than the last archived segment as a new read-only segment."""
    tdir = _root(archive_dir) / tenant_id
    after = _last_seq(tdir)
    rows = SystemRepo(db, "audit_log", purpose="audit archive").find(
        {"tenant_id": tenant_id, "seq": {"$gt": after}}, sort=[("seq", 1)]
    )
    if not rows:
        return None
    entries = [AuditEntry.model_validate(r) for r in rows]
    tdir.mkdir(parents=True, exist_ok=True)
    seg = tdir / f"{entries[0].seq:06d}-{entries[-1].seq:06d}.jsonl"
    body = "".join(e.model_dump_json() + "\n" for e in entries).encode()
    seg.write_bytes(body)
    digest = hashlib.sha256(body).hexdigest()
    side = seg.with_suffix(".jsonl.sha256")
    side.write_text(f"{digest}  {seg.name}\n", encoding="utf-8")
    for p in (seg, side):
        os.chmod(p, stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)  # 0444: the local "write once"
    uploaded = _upload(tenant_id, seg, body, digest)
    return {"tenant_id": tenant_id, "segment": seg.name, "entries": len(entries), "sha256": digest, "s3": uploaded}


def _upload(tenant_id: str, seg: Path, body: bytes, digest: str) -> bool:
    s = get_settings()
    if not s.audit_archive_s3_bucket:
        return False
    import boto3  # optional dependency: pip install -e ".[aws]"

    client = boto3.client("s3", endpoint_url=s.audit_archive_s3_endpoint)
    client.put_object(
        Bucket=s.audit_archive_s3_bucket,
        Key=f"audit/{tenant_id}/{seg.name}",
        Body=body,
        ContentType="application/x-ndjson",
        Metadata={"sha256": digest},
        ObjectLockMode=s.audit_archive_lock_mode,
        ObjectLockRetainUntilDate=utcnow() + timedelta(days=s.audit_archive_lock_days),
    )
    return True


def verify_archive(tenant_id: str, *, archive_dir: Path | None = None) -> ArchiveCheck:
    """Re-verify the chain using only the archive: checksums, contiguous seq, prev_hash links, hashes."""
    tdir = _root(archive_dir) / tenant_id
    check = ArchiveCheck(tenant_id=tenant_id, ok=True)
    prev, expected = GENESIS, 1
    for seg in _segments(tdir):
        check.segments += 1
        side = seg.with_suffix(".jsonl.sha256")
        if not side.exists() or side.read_text().split()[0] != hashlib.sha256(seg.read_bytes()).hexdigest():
            check.problems.append(f"{seg.name}: checksum mismatch or missing")
        for e in _read(seg):
            check.entries += 1
            if e.seq != expected:
                check.problems.append(f"{seg.name}: expected seq {expected}, found {e.seq}")
            if e.prev_hash != prev:
                check.problems.append(f"seq {e.seq}: prev_hash does not link")
            if e.compute_hash() != e.hash:
                check.problems.append(f"seq {e.seq}: entry hash does not match its content")
            prev, expected = e.hash, e.seq + 1
    check.ok = not check.problems
    return check


def compare_with_database(db: Database, tenant_id: str, *, archive_dir: Path | None = None) -> ArchiveCheck:
    """Detect a database rewritten after archiving (which a recomputed chain would otherwise hide)."""
    check = verify_archive(tenant_id, archive_dir=archive_dir)
    live = {
        r["seq"]: r["hash"]
        for r in SystemRepo(db, "audit_log", purpose="audit archive compare").find({"tenant_id": tenant_id})
    }
    for seg in _segments(_root(archive_dir) / tenant_id):
        for e in _read(seg):
            if e.seq not in live:
                check.problems.append(f"seq {e.seq}: archived but missing from the database")
            elif live[e.seq] != e.hash:
                check.problems.append(f"seq {e.seq}: database entry differs from the write-once archive")
    check.ok = not check.problems
    return check


def archive_job(db: Database, *, archive_dir: Path | None = None) -> dict[str, Any]:
    """Nightly: export new entries for every tenant, then compare database and archive (P1 on mismatch)."""
    from adintel.observability.alerts import Severity, raise_alert

    tenants = sorted({r["tenant_id"] for r in SystemRepo(db, "audit_log", purpose="audit archive").find({})})
    exported = [x for t in tenants if (x := export_tenant(db, t, archive_dir=archive_dir))]
    mismatched = []
    for t in tenants:
        c = compare_with_database(db, t, archive_dir=archive_dir)
        if not c.ok:
            mismatched.append(t)
            raise_alert(
                Severity.P1,
                "Audit log differs from its write-once archive",
                tenant_id=t,
                details={"problems": c.problems[:5]},
                audience="security",
            )
    return {"exported": exported, "mismatched": mismatched}
