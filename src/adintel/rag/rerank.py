"""Rerankers. A cross-encoder reads query and document together: accurate but slow, so it only sees
the 25 fused candidates."""

from __future__ import annotations

import itertools
import threading
from abc import ABC, abstractmethod

from adintel.config import get_settings
from adintel.rag.bm25 import tokenize


class Reranker(ABC):
    model_id: str

    @abstractmethod
    def scores(self, query: str, docs: list[str]) -> list[float]: ...


class LexicalReranker(Reranker):
    """Deterministic stand-in: query-term coverage plus bigram overlap."""

    model_id = "adintel/lexical-rerank-v1"

    def scores(self, query: str, docs: list[str]) -> list[float]:
        q = tokenize(query)
        qs, qb = set(q), set(itertools.pairwise(q))
        out = []
        for d in docs:
            t = tokenize(d)
            ts, tb = set(t), set(itertools.pairwise(t))
            cov = len(qs & ts) / (len(qs) or 1)
            big = len(qb & tb) / (len(qb) or 1)
            out.append(round(0.7 * cov + 0.3 * big, 6))
        return out


class FastEmbedReranker(Reranker):
    model_id = "BAAI/bge-reranker-base"

    def __init__(self) -> None:
        from fastembed.rerank.cross_encoder import TextCrossEncoder

        self._model = TextCrossEncoder(self.model_id)

    def scores(self, query: str, docs: list[str]) -> list[float]:
        return [float(s) for s in self._model.rerank(query, docs)]


_reranker: Reranker | None = None
_lock = threading.Lock()


def get_reranker() -> Reranker:
    global _reranker
    with _lock:
        if _reranker is None:
            _reranker = FastEmbedReranker() if get_settings().reranker == "fastembed" else LexicalReranker()
        return _reranker
