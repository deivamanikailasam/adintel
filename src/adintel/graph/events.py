"""Run progress events (persisted in ``run_events`` and streamed to the UI over SSE)."""

from __future__ import annotations

import threading
from typing import Any

from adintel.core.clock import utcnow
from adintel.storage.base import Database
from adintel.storage.tenant_repo import TenantScopedRepo

_seq_lock = threading.Lock()
_seq: dict[str, int] = {}


def publish(db: Database, tenant_id: str, run_id: str, kind: str, data: dict[str, Any]) -> None:
    with _seq_lock:
        _seq[run_id] = _seq.get(run_id, 0) + 1
        seq = _seq[run_id]
    TenantScopedRepo(db, "run_events", tenant_id).insert(
        {"run_id": run_id, "seq": seq, "kind": kind, "data": data, "at": utcnow().isoformat()}
    )


def since(db: Database, tenant_id: str, run_id: str, after_seq: int) -> list[dict[str, Any]]:
    return TenantScopedRepo(db, "run_events", tenant_id).find(
        {"run_id": run_id, "seq": {"$gt": after_seq}}, sort=[("seq", 1)], limit=200
    )
