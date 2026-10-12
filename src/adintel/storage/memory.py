"""In-memory backend: thread-safe, deep-copying, with unique indexes and brute-force vector search."""

from __future__ import annotations

import copy
import math
import threading
from collections.abc import Sequence
from typing import Any

from adintel.storage.base import Collection, Database, Doc, DuplicateKey, Filter, SortSpec
from adintel.storage.matching import apply_update, get_path, matches, sort_docs


def cosine(a: Sequence[float], b: Sequence[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=False))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return 0.0 if na == 0 or nb == 0 else dot / (na * nb)


class MemoryCollection(Collection):
    def __init__(self, name: str) -> None:
        self.name = name
        self._docs: list[Doc] = []
        self._unique: list[tuple[str, ...]] = []
        self._lock = threading.RLock()

    def _check_unique(self, doc: Doc, ignore: Doc | None = None) -> None:
        for keys in self._unique:
            values = tuple(get_path(doc, k) for k in keys)
            for other in self._docs:
                if other is ignore:
                    continue
                if tuple(get_path(other, k) for k in keys) == values:
                    raise DuplicateKey(f"{self.name}: duplicate key {dict(zip(keys, values, strict=True))}")

    def insert_one(self, doc: Doc) -> None:
        with self._lock:
            d = copy.deepcopy(doc)
            self._check_unique(d)
            self._docs.append(d)

    def find(
        self,
        flt: Filter,
        *,
        sort: SortSpec | None = None,
        limit: int | None = None,
        projection: dict[str, int] | None = None,
    ) -> list[Doc]:
        with self._lock:
            rows = [d for d in self._docs if matches(d, flt)]
            if sort:
                rows = sort_docs(rows, sort)
            if limit is not None:
                rows = rows[:limit]
            out = [copy.deepcopy(d) for d in rows]
        if projection:
            keep = {k for k, v in projection.items() if v}
            drop = {k for k, v in projection.items() if not v}
            if keep:
                out = [{k: v for k, v in d.items() if k in keep} for d in out]
            elif drop:
                out = [{k: v for k, v in d.items() if k not in drop} for d in out]
        return out

    def update_one(self, flt: Filter, update: Doc, *, upsert: bool = False) -> int:
        with self._lock:
            for d in self._docs:
                if matches(d, flt):
                    candidate = copy.deepcopy(d)
                    apply_update(candidate, update)
                    self._check_unique(candidate, ignore=d)
                    d.clear()
                    d.update(candidate)
                    return 1
            if upsert:
                new: Doc = {k: v for k, v in flt.items() if not k.startswith("$") and not isinstance(v, dict)}
                apply_update(new, update, inserting=True)
                self._check_unique(new)
                self._docs.append(new)
                return 0
            return 0

    def update_many(self, flt: Filter, update: Doc) -> int:
        with self._lock:
            n = 0
            for d in self._docs:
                if matches(d, flt):
                    apply_update(d, update)
                    n += 1
            return n

    def delete_many(self, flt: Filter) -> int:
        with self._lock:
            before = len(self._docs)
            self._docs = [d for d in self._docs if not matches(d, flt)]
            return before - len(self._docs)

    def count(self, flt: Filter) -> int:
        with self._lock:
            return sum(1 for d in self._docs if matches(d, flt))

    def create_index(
        self, keys: Sequence[tuple[str, int]], *, unique: bool = False, ttl_seconds: int | None = None
    ) -> None:
        if unique:
            names = tuple(k for k, _ in keys)
            with self._lock:
                if names not in self._unique:
                    self._unique.append(names)

    def vector_search(
        self, vector: Sequence[float], flt: Filter, *, limit: int, num_candidates: int, path: str = "embedding"
    ) -> list[tuple[Doc, float]]:
        with self._lock:
            candidates = [d for d in self._docs if matches(d, flt) and isinstance(d.get(path), list)]
            scored = [(copy.deepcopy(d), cosine(vector, d[path])) for d in candidates]
        scored.sort(key=lambda t: (-t[1], str(t[0].get("chunk_id", t[0].get("_id", "")))))
        return scored[:limit]

    # test helper
    def _raw(self) -> list[Doc]:
        return self._docs


class MemoryDatabase(Database):
    def __init__(self) -> None:
        self._collections: dict[str, MemoryCollection] = {}
        self._lock = threading.Lock()

    def collection(self, name: str) -> MemoryCollection:
        with self._lock:
            if name not in self._collections:
                self._collections[name] = MemoryCollection(name)
            return self._collections[name]

    def ping(self) -> bool:
        return True

    def drop_all(self) -> None:
        with self._lock:
            self._collections.clear()

    def stats(self) -> dict[str, Any]:
        return {name: len(c._docs) for name, c in self._collections.items()}
