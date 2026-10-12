"""What every agent receives besides the state: tenant-scoped data access, the LLM gateway, the
usage meter and a cancellation token. Agents never receive the raw database."""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Any

from adintel.core.errors import AdIntelError
from adintel.harness.budget import UsageMeter
from adintel.llm.gateway import LLMGateway
from adintel.storage.base import Database
from adintel.storage.tenant_repo import TenantScopedRepo


class Cancelled(AdIntelError):
    """The harness timed the agent out; stop at the next safe point."""


@dataclass
class AgentContext:
    _db: Database
    tenant_id: str
    brand_id: str
    run_id: str
    llm: LLMGateway
    meter: UsageMeter
    cancel: threading.Event = field(default_factory=threading.Event)
    extras: dict[str, Any] = field(default_factory=dict)

    def repo(self, collection: str) -> TenantScopedRepo:
        return TenantScopedRepo(self._db, collection, self.tenant_id)

    def check_cancelled(self) -> None:
        if self.cancel.is_set():
            raise Cancelled("agent timed out")

    def retriever(self) -> Any:
        if "retriever" not in self.extras:
            from adintel.rag.retriever import Retriever

            self.extras["retriever"] = Retriever(self._db, self.tenant_id)
        return self.extras["retriever"]
