"""Langfuse agent tracing via its public ingestion API (self-hosted; traces contain client data).

Optional and strictly non-blocking: events are buffered and flushed by a daemon thread; any failure
is logged and dropped. Tracing must never fail a run.
"""

from __future__ import annotations

import logging
import queue
import threading
import uuid
from datetime import UTC, datetime
from typing import Any

import httpx

log = logging.getLogger(__name__)


class LangfuseClient:
    def __init__(self, host: str, public_key: str, secret_key: str, *, flush_interval: float = 2.0) -> None:
        self._url = f"{host.rstrip('/')}/api/public/ingestion"
        self._auth = (public_key, secret_key)
        self._q: queue.Queue[dict[str, Any]] = queue.Queue(maxsize=10_000)
        self._interval = flush_interval
        threading.Thread(target=self._loop, name="langfuse-flush", daemon=True).start()

    @staticmethod
    def _now() -> str:
        return datetime.now(UTC).isoformat()

    def _event(self, kind: str, body: dict[str, Any]) -> None:
        try:
            self._q.put_nowait({"id": uuid.uuid4().hex, "type": kind, "timestamp": self._now(), "body": body})
        except queue.Full:
            log.warning("langfuse_queue_full")

    def trace(self, trace_id: str, name: str, *, tenant_id: str, metadata: dict[str, Any]) -> None:
        self._event(
            "trace-create",
            {"id": trace_id, "name": name, "userId": tenant_id, "metadata": metadata, "tags": [tenant_id]},
        )

    def generation(
        self,
        trace_id: str,
        *,
        name: str,
        model: str,
        input: Any,
        output: Any,
        usage: dict[str, int],
        metadata: dict[str, Any],
        start: datetime,
        end: datetime,
    ) -> None:
        self._event(
            "generation-create",
            {
                "id": uuid.uuid4().hex,
                "traceId": trace_id,
                "name": name,
                "model": model,
                "input": input,
                "output": output,
                "metadata": metadata,
                "startTime": start.isoformat(),
                "endTime": end.isoformat(),
                "usage": {"input": usage.get("input", 0), "output": usage.get("output", 0), "unit": "TOKENS"},
            },
        )

    def span(self, trace_id: str, *, name: str, metadata: dict[str, Any], start: datetime, end: datetime) -> None:
        self._event(
            "span-create",
            {
                "id": uuid.uuid4().hex,
                "traceId": trace_id,
                "name": name,
                "metadata": metadata,
                "startTime": start.isoformat(),
                "endTime": end.isoformat(),
            },
        )

    def _loop(self) -> None:
        with httpx.Client(timeout=5.0) as client:
            while True:
                batch: list[dict[str, Any]] = []
                try:
                    batch.append(self._q.get(timeout=self._interval))
                    while len(batch) < 100:
                        batch.append(self._q.get_nowait())
                except queue.Empty:
                    pass
                if not batch:
                    continue
                try:
                    client.post(self._url, json={"batch": batch}, auth=self._auth)
                except Exception as exc:
                    log.warning("langfuse_flush_failed", extra={"reason": str(exc)[:200]})


_client: LangfuseClient | None = None
_init_lock = threading.Lock()


def get_langfuse() -> LangfuseClient | None:
    global _client
    from adintel.config import get_settings

    s = get_settings()
    if not (s.langfuse_host and s.langfuse_public_key and s.langfuse_secret_key):
        return None
    with _init_lock:
        if _client is None:
            _client = LangfuseClient(s.langfuse_host, s.langfuse_public_key, s.langfuse_secret_key)
    return _client
