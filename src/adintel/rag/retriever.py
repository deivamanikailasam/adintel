"""Hybrid retrieval with a mandatory tenant pre-filter.

query → embed (cached) → [vector search ∥ BM25] inside the filter → RRF (0.65 semantic / 0.35 keyword)
→ top 25 → cross-encoder rerank → top 6 → fenced into the prompt with source info.
Ties are broken by chunk ID, so retrieval is deterministic.
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Any

from adintel.core.errors import AdIntelError
from adintel.core.hashing import sha256_obj
from adintel.observability.metrics import CACHE, TOOL_FAILURES
from adintel.rag.bm25 import bm25_scores
from adintel.rag.embeddings import get_embedder
from adintel.rag.rerank import get_reranker
from adintel.storage.base import Database
from adintel.storage.tenant_repo import TenantScopedRepo

log = logging.getLogger(__name__)

SEMANTIC_WEIGHT, KEYWORD_WEIGHT, RRF_K = 0.65, 0.35, 60
OVERFETCH, TOP_K = 25, 6
CACHE_TTL = 600.0


class RetrievalUnavailable(AdIntelError):
    pass


@dataclass
class RetrievedChunk:
    chunk_id: str
    doc_id: str
    doc_title: str
    doc_type: str
    heading: str
    text: str
    content_hash: str
    score: float
    anonymised: bool = False

    def as_evidence(self) -> dict[str, Any]:
        return {"chunk_id": self.chunk_id, "title": self.doc_title, "type": self.doc_type,
                "section": self.heading, "text": self.text}


@dataclass
class RetrievalResult:
    chunks: list[RetrievedChunk]
    reranked: bool
    degraded: list[str] = field(default_factory=list)

    @property
    def ids(self) -> list[str]:
        return [c.chunk_id for c in self.chunks]


_cache: dict[str, tuple[float, RetrievalResult]] = {}
_cache_lock = threading.Lock()


class Retriever:
    def __init__(self, db: Database, tenant_id: str) -> None:
        self.tenant_id = tenant_id
        self._repo = TenantScopedRepo(db, "kb_chunks", tenant_id)

    @staticmethod
    def build_filter(*, brand_id: str, vertical: str | None, doc_types: list[str] | None,
                     date_from: str | None = None, cross_brand_incidents: bool = True) -> dict[str, Any]:
        scope: list[dict[str, Any]] = [{"brand_id": {"$in": [brand_id, "*"]}}]
        if cross_brand_incidents and vertical:
            scope.append({"doc_type": "incident", "vertical": vertical, "anonymised": True})
        flt: dict[str, Any] = {"is_active": True, "$or": scope}
        if doc_types:
            flt["doc_type"] = {"$in": doc_types}
        if date_from:
            flt["date"] = {"$gte": date_from}
        return flt

    def search(self, query: str, *, brand_id: str, vertical: str | None = None, doc_types: list[str] | None = None,
               date_from: str | None = None, k: int = TOP_K, use_cache: bool = True) -> RetrievalResult:
        flt = self.build_filter(brand_id=brand_id, vertical=vertical, doc_types=doc_types, date_from=date_from)
        key = sha256_obj({"t": self.tenant_id, "b": brand_id, "q": query, "f": flt, "k": k})
        if use_cache:
            with _cache_lock:
                hit = _cache.get(key)
            if hit and time.monotonic() - hit[0] < CACHE_TTL:
                CACHE.labels(cache="rag", result="hit").inc()
                return hit[1]
            CACHE.labels(cache="rag", result="miss").inc()
        try:
            qv = get_embedder().embed_one(query)
            vec_hits = self._repo.vector_search(qv, flt, limit=OVERFETCH, num_candidates=OVERFETCH * 12)
            candidates = self._repo.find(flt, projection={"embedding": 0})
        except Exception as exc:
            TOOL_FAILURES.labels(tool="vector_search").inc()
            raise RetrievalUnavailable(str(exc)) from exc
        by_id = {d["chunk_id"]: d for d in candidates}
        sem_rank = {d["chunk_id"]: i for i, (d, _) in enumerate(vec_hits)}
        kw = bm25_scores(query, [f"{d['doc_title']} {d.get('heading', '')} {d['text']}" for d in candidates])
        kw_sorted = sorted(zip(candidates, kw, strict=True), key=lambda t: (-t[1], t[0]["chunk_id"]))
        kw_rank = {d["chunk_id"]: i for i, (d, s) in enumerate(kw_sorted) if s > 0}
        fused: dict[str, float] = {}
        for cid, r in sem_rank.items():
            fused[cid] = fused.get(cid, 0.0) + SEMANTIC_WEIGHT / (RRF_K + r + 1)
        for cid, r in kw_rank.items():
            fused[cid] = fused.get(cid, 0.0) + KEYWORD_WEIGHT / (RRF_K + r + 1)
        top = sorted(fused.items(), key=lambda t: (-t[1], t[0]))[:OVERFETCH]
        docs = [by_id[c] for c, _ in top if c in by_id]
        degraded: list[str] = []
        reranked = True
        try:
            scores = get_reranker().scores(query, [d["text"] for d in docs])
            order = sorted(zip(docs, scores, strict=True), key=lambda t: (-t[1], t[0]["chunk_id"]))
        except Exception as exc:  # noqa: BLE001 - reranker down → raw fused order (degraded)
            log.warning("reranker_unavailable", extra={"reason": str(exc)[:200]})
            TOOL_FAILURES.labels(tool="reranker").inc()
            order = [(d, fused[d["chunk_id"]]) for d in docs]
            reranked = False
            degraded.append("reranker_unavailable")
        result = RetrievalResult(
            chunks=[RetrievedChunk(chunk_id=d["chunk_id"], doc_id=d["doc_id"], doc_title=d["doc_title"],
                                   doc_type=d["doc_type"], heading=d.get("heading", ""), text=d["text"],
                                   content_hash=d["content_hash"], score=round(float(s), 6),
                                   anonymised=bool(d.get("anonymised"))) for d, s in order[:k]],
            reranked=reranked, degraded=degraded)
        if use_cache:
            with _cache_lock:
                _cache[key] = (time.monotonic(), result)
        return result


def clear_cache() -> None:
    with _cache_lock:
        _cache.clear()
