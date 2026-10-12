"""Semantic cache for near-duplicate chat questions: cosine ≥ 0.97, 15-minute TTL, and the **tenant and
brand are part of the key**, so a cached answer can never cross a client boundary."""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Any

from adintel.observability.metrics import CACHE
from adintel.rag.embeddings import get_embedder
from adintel.storage.memory import cosine

THRESHOLD = 0.97
TTL_SECONDS = 900.0
MAX_ENTRIES_PER_SCOPE = 500


@dataclass
class _Entry:
    vector: list[float]
    question: str
    answer: dict[str, Any]
    at: float


class SemanticCache:
    def __init__(self, threshold: float = THRESHOLD, ttl: float = TTL_SECONDS) -> None:
        self.threshold = threshold
        self.ttl = ttl
        self._store: dict[tuple[str, str], list[_Entry]] = {}
        self._lock = threading.Lock()

    @staticmethod
    def _norm(q: str) -> str:
        return " ".join(q.lower().split())

    def get(self, tenant_id: str, brand_id: str, question: str) -> dict[str, Any] | None:
        v = get_embedder().embed_one(self._norm(question))
        now = time.monotonic()
        with self._lock:
            entries = [e for e in self._store.get((tenant_id, brand_id), []) if now - e.at < self.ttl]
            self._store[(tenant_id, brand_id)] = entries
            best = max(entries, key=lambda e: cosine(v, e.vector), default=None)
        if best is not None and cosine(v, best.vector) >= self.threshold:
            CACHE.labels(cache="semantic", result="hit").inc()
            return {**best.answer, "cached": True}
        CACHE.labels(cache="semantic", result="miss").inc()
        return None

    def put(self, tenant_id: str, brand_id: str, question: str, answer: dict[str, Any]) -> None:
        v = get_embedder().embed_one(self._norm(question))
        with self._lock:
            entries = self._store.setdefault((tenant_id, brand_id), [])
            entries.append(_Entry(v, question, answer, time.monotonic()))
            del entries[:-MAX_ENTRIES_PER_SCOPE]


_cache = SemanticCache()


def get_semantic_cache() -> SemanticCache:
    return _cache
