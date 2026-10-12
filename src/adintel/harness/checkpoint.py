"""Checkpointing (ADR L-06): the RunState is saved after every step with a content hash.

A run that touched paid APIs must resume, not restart. A corrupt checkpoint must fail cleanly instead
of resuming from garbage.
"""

from __future__ import annotations

from datetime import timedelta

from adintel.core.clock import utcnow
from adintel.core.errors import CheckpointCorrupted
from adintel.core.hashing import sha256_text
from adintel.domain.state import RunState
from adintel.storage.base import Database
from adintel.storage.tenant_repo import TenantScopedRepo

RETENTION = timedelta(days=30)


class CheckpointStore:
    def __init__(self, db: Database, tenant_id: str) -> None:
        self._repo = TenantScopedRepo(db, "run_checkpoints", tenant_id)

    def save(self, state: RunState, *, version: int) -> str:
        payload = state.model_dump_json()
        digest = sha256_text(payload)
        self._repo.update_one(
            {"run_id": state.run_id, "step": version},
            {"$set": {"run_id": state.run_id, "step": version, "state": payload, "state_hash": digest,
                      "status": str(state.status), "created_at": utcnow().isoformat(),
                      "expire_at": utcnow() + RETENTION}},
            upsert=True,
        )
        return digest

    def latest(self, run_id: str) -> tuple[int, RunState] | None:
        doc = self._repo.find_one({"run_id": run_id}, sort=[("step", -1)])
        if doc is None:
            return None
        if sha256_text(doc["state"]) != doc["state_hash"]:
            raise CheckpointCorrupted(f"run {run_id} checkpoint v{doc['step']} failed its integrity check")
        try:
            return int(doc["step"]), RunState.model_validate_json(doc["state"])
        except ValueError as exc:
            raise CheckpointCorrupted(f"run {run_id} checkpoint v{doc['step']} is not a valid RunState") from exc

    def versions(self, run_id: str) -> list[int]:
        return [int(d["step"]) for d in self._repo.find({"run_id": run_id}, sort=[("step", 1)],
                                                        projection={"step": 1})]
