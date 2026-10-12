"""Append-only, hash-chained audit log (one chain per tenant).

Each entry stores the hash of the previous entry, and its own hash covers every field including that
link. Changing, deleting or reordering any historical entry therefore breaks every hash after it, so
tampering is *detectable* by a daily verification job (``adintel verify-audit``).

The class exposes only ``append`` and read methods: there is no update or delete path in code. In
production the database role used by services has insert+find privileges only on ``audit_log`` and a
daily export goes to S3 with Object Lock (see docs/10-audit/audit-and-reproducibility.md).
"""

from __future__ import annotations

import logging
import threading
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from adintel.core.clock import utcnow
from adintel.core.hashing import sha256_obj
from adintel.domain.enums import AuditAction
from adintel.storage.base import Database, DuplicateKey
from adintel.storage.tenant_repo import SystemRepo, TenantScopedRepo

log = logging.getLogger(__name__)

GENESIS = "0" * 64
_append_lock = threading.Lock()


class AuditEntry(BaseModel):
    tenant_id: str
    seq: int
    at: datetime
    actor_type: str  # human | agent | system
    actor_id: str  # user id, "agent:<name>@<model>" or "system:<job>"
    action: AuditAction
    subject_type: str
    subject_id: str
    run_id: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)
    system_version: str = ""
    prev_hash: str
    hash: str = ""

    def compute_hash(self) -> str:
        return sha256_obj(self.model_dump(mode="json", exclude={"hash"}))


class ChainVerification(BaseModel):
    tenant_id: str
    ok: bool
    entries: int
    broken_at_seq: int | None = None
    reason: str | None = None


class AuditLog:
    def __init__(self, db: Database, tenant_id: str, *, system_version: str = "") -> None:
        self._repo = TenantScopedRepo(db, "audit_log", tenant_id)
        self.tenant_id = tenant_id
        self.system_version = system_version

    def _head(self) -> dict[str, Any] | None:
        return self._repo.find_one({}, sort=[("seq", -1)])

    def append(
        self,
        action: AuditAction,
        *,
        actor_type: str,
        actor_id: str,
        subject_type: str,
        subject_id: str,
        run_id: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> AuditEntry:
        for _attempt in range(20):
            with _append_lock:
                head = self._head()
                entry = AuditEntry(
                    tenant_id=self.tenant_id,
                    seq=(head["seq"] + 1) if head else 1,
                    at=utcnow(),
                    actor_type=actor_type,
                    actor_id=actor_id,
                    action=action,
                    subject_type=subject_type,
                    subject_id=subject_id,
                    run_id=run_id,
                    details=details or {},
                    system_version=self.system_version,
                    prev_hash=head["hash"] if head else GENESIS,
                )
                entry.hash = entry.compute_hash()
                try:
                    self._repo.insert(entry.model_dump(mode="json"))
                    return entry
                except DuplicateKey:
                    continue  # another process appended concurrently; re-read head and retry
        raise RuntimeError("audit append contention: could not obtain a sequence number")

    def entries(
        self, *, subject_id: str | None = None, run_id: str | None = None, limit: int | None = None
    ) -> list[AuditEntry]:
        flt: dict[str, Any] = {}
        if subject_id:
            flt["subject_id"] = subject_id
        if run_id:
            flt["run_id"] = run_id
        rows = self._repo.find(flt, sort=[("seq", 1)], limit=limit)
        return [AuditEntry.model_validate(r) for r in rows]

    def verify(self) -> ChainVerification:
        rows = self._repo.find({}, sort=[("seq", 1)])
        prev = GENESIS
        expected_seq = 1
        for row in rows:
            entry = AuditEntry.model_validate(row)
            if entry.seq != expected_seq:
                return ChainVerification(
                    tenant_id=self.tenant_id,
                    ok=False,
                    entries=len(rows),
                    broken_at_seq=entry.seq,
                    reason=f"gap: expected seq {expected_seq}",
                )
            if entry.prev_hash != prev:
                return ChainVerification(
                    tenant_id=self.tenant_id,
                    ok=False,
                    entries=len(rows),
                    broken_at_seq=entry.seq,
                    reason="prev_hash does not link",
                )
            if entry.compute_hash() != entry.hash:
                return ChainVerification(
                    tenant_id=self.tenant_id,
                    ok=False,
                    entries=len(rows),
                    broken_at_seq=entry.seq,
                    reason="content hash mismatch (edited)",
                )
            prev = entry.hash
            expected_seq += 1
        return ChainVerification(tenant_id=self.tenant_id, ok=True, entries=len(rows))


def verify_all_tenants(db: Database) -> list[ChainVerification]:
    tenants = {r["tenant_id"] for r in SystemRepo(db, "tenants", purpose="audit chain verification").find()}
    audit = SystemRepo(db, "audit_log", purpose="audit chain verification")
    tenants |= {r["tenant_id"] for r in audit.find({}, limit=None)}
    results = [AuditLog(db, t).verify() for t in sorted(tenants)]
    for r in results:
        if not r.ok:
            log.critical(
                "audit_chain_broken", extra={"tenant_id": r.tenant_id, "seq": r.broken_at_seq, "reason": r.reason}
            )
    return results
