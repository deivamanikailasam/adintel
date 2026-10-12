"""Embedders behind one interface (ADR L-09). Pinned model IDs; vectors cached by content hash."""

from __future__ import annotations

import hashlib
import itertools
import math
import re
import threading
from abc import ABC, abstractmethod

from adintel.config import get_settings


class Embedder(ABC):
    model_id: str
    dimensions: int

    @abstractmethod
    def _embed(self, texts: list[str]) -> list[list[float]]: ...

    def __init__(self) -> None:
        self._cache: dict[str, list[float]] = {}
        self._lock = threading.Lock()

    def embed(self, texts: list[str]) -> list[list[float]]:
        keys = [hashlib.sha256(t.encode()).hexdigest() for t in texts]
        with self._lock:
            missing = [(k, t) for k, t in zip(keys, texts, strict=True) if k not in self._cache]
        if missing:
            vecs = self._embed([t for _, t in missing])
            with self._lock:
                for (k, _), v in zip(missing, vecs, strict=True):
                    self._cache[k] = v
        with self._lock:
            return [self._cache[k] for k in keys]

    def embed_one(self, text: str) -> list[float]:
        return self.embed([text])[0]


_WORD = re.compile(r"[a-z0-9]+")


class HashingEmbedder(Embedder):
    """Deterministic signed feature hashing of unigrams + bigrams. Offline, dependency-free, testable."""

    model_id = "adintel/hashing-v1-384"
    dimensions = 384

    def _vec(self, text: str) -> list[float]:
        from adintel.rag.bm25 import tokenize

        words = tokenize(text)
        feats = words + [f"{a}_{b}" for a, b in itertools.pairwise(words)]
        v = [0.0] * self.dimensions
        for f in feats:
            h = int(hashlib.md5(f.encode(), usedforsecurity=False).hexdigest(), 16)
            v[h % self.dimensions] += 1.0 if (h >> 9) & 1 else -1.0
        n = math.sqrt(sum(x * x for x in v)) or 1.0
        return [x / n for x in v]

    def _embed(self, texts: list[str]) -> list[list[float]]:
        return [self._vec(t) for t in texts]


class FastEmbedEmbedder(Embedder):
    model_id = "BAAI/bge-small-en-v1.5"
    dimensions = 384

    def __init__(self) -> None:
        super().__init__()
        from fastembed import TextEmbedding

        self._model = TextEmbedding(self.model_id)

    def _embed(self, texts: list[str]) -> list[list[float]]:
        return [list(map(float, v)) for v in self._model.embed(texts)]


_embedder: Embedder | None = None
_lock = threading.Lock()


def get_embedder() -> Embedder:
    global _embedder
    with _lock:
        if _embedder is None:
            _embedder = FastEmbedEmbedder() if get_settings().embedder == "fastembed" else HashingEmbedder()
        return _embedder
