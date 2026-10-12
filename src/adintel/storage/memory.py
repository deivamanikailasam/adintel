"""In-memory backend: thread-safe, deep-copying, with hash-based unique indexes, (tenant, brand) buckets
for fast scoped lookups, and brute-force vector search over the pre-filtered set."""

from __future__ import annotations

import copy
import itertools
import math
import threading
from collections.abc import Iterable, Sequence
from typing import Any

from adintel.storage.base import Collection, Database, Doc, DuplicateKey, Filter, SortSpec
from adintel.storage.matching import apply_update, get_path, matches, sort_docs


def cosine(a: Sequence[float], b: Sequence[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=False))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return 0.0 if na == 0 or nb == 0 else dot / (na * nb)


def _hashable(v: Any) -> Any:
    try:
        hash(v)
        return v
    except TypeError:
        return repr(v)


class MemoryCollection(Collection):
    def __init__(self, name: str) -> None:
        self.name = name
        self._docs: dict[int, Doc] = {}
        self._ids = itertools.count()
        self._unique: dict[tuple[str, ...], dict[tuple[Any, ...], int]] = {}
        self._buckets: dict[tuple[Any, Any], set[int]] = {}
        self._lock = threading.RLock()

    # ---- index maintenance ---------------------------------------------------------------------
    @staticmethod
    def _bucket_key(doc: Doc) -> tuple[Any, Any]:
        return (_hashable(doc.get("tenant_id")), _hashable(doc.get("brand_id")))

    def _ukey(self, keys: tuple[str, ...], doc: Doc) -> tuple[Any, ...]:
        return tuple(_hashable(get_path(doc, k)) for k in keys)

    def _index(self, i: int, doc: Doc) -> None:
        self._buckets.setdefault(self._bucket_key(doc), set()).add(i)
        for keys, m in self._unique.items():
            m[self._ukey(keys, doc)] = i

    def _unindex(self, i: int, doc: Doc) -> None:
        self._buckets.get(self._bucket_key(doc), set()).discard(i)
        for keys, m in self._unique.items():
            k = self._ukey(keys, doc)
            if m.get(k) == i:
                del m[k]

    def _check_unique(self, doc: Doc, ignore: int | None = None) -> None:
        for keys, m in self._unique.items():
            k = self._ukey(keys, doc)
            if k in m and m[k] != ignore:
                raise DuplicateKey(f"{self.name}: duplicate key {dict(zip(keys, k, strict=True))}")

    def _candidates(self, flt: Filter) -> Iterable[tuple[int, Doc]]:
        t, b = flt.get("tenant_id"), flt.get("brand_id")
        if isinstance(t, str) and isinstance(b, str):
            ids = sorted(self._buckets.get((t, b), ()))
            return [(i, self._docs[i]) for i in ids]
        return list(self._docs.items())

    # ---- API -----------------------------------------------------------------------------------
    def insert_one(self, doc: Doc) -> None:
        with self._lock:
            d = copy.deepcopy(doc)
            self._check_unique(d)
            i = next(self._ids)
            self._docs[i] = d
            self._index(i, d)

    def find(
        self,
        flt: Filter,
        *,
        sort: SortSpec | None = None,
        limit: int | None = None,
        projection: dict[str, int] | None = None,
    ) -> list[Doc]:
        with self._lock:
            rows = [d for _, d in self._candidates(flt) if matches(d, flt)]
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
            for i, d in self._candidates(flt):
                if matches(d, flt):
                    candidate = copy.deepcopy(d)
                    apply_update(candidate, update)
                    self._check_unique(candidate, ignore=i)
                    self._unindex(i, d)
                    self._docs[i] = candidate
                    self._index(i, candidate)
                    return 1
            if upsert:
                new: Doc = {k: v for k, v in flt.items() if not k.startswith("$") and not isinstance(v, dict)}
                apply_update(new, update, inserting=True)
                self._check_unique(new)
                i = next(self._ids)
                self._docs[i] = new
                self._index(i, new)
            return 0

    def update_many(self, flt: Filter, update: Doc) -> int:
        with self._lock:
            n = 0
            for i, d in list(self._candidates(flt)):
                if matches(d, flt):
                    candidate = copy.deepcopy(d)
                    apply_update(candidate, update)
                    self._unindex(i, d)
                    self._docs[i] = candidate
                    self._index(i, candidate)
                    n += 1
            return n

    def delete_many(self, flt: Filter) -> int:
        with self._lock:
            gone = [(i, d) for i, d in self._candidates(flt) if matches(d, flt)]
            for i, d in gone:
                self._unindex(i, d)
                del self._docs[i]
            return len(gone)

    def count(self, flt: Filter) -> int:
        with self._lock:
            return sum(1 for _, d in self._candidates(flt) if matches(d, flt))

    def create_index(
        self, keys: Sequence[tuple[str, int]], *, unique: bool = False, ttl_seconds: int | None = None
    ) -> None:
        if not unique:
            return
        names = tuple(k for k, _ in keys)
        with self._lock:
            if names in self._unique:
                return
            m: dict[tuple[Any, ...], int] = {}
            for i, d in self._docs.items():
                k = self._ukey(names, d)
                if k in m:
                    raise DuplicateKey(f"{self.name}: existing duplicates for unique index {names}")
                m[k] = i
            self._unique[names] = m

    def vector_search(
        self, vector: Sequence[float], flt: Filter, *, limit: int, num_candidates: int, path: str = "embedding"
    ) -> list[tuple[Doc, float]]:
        with self._lock:
            candidates = [d for _, d in self._candidates(flt) if matches(d, flt) and isinstance(d.get(path), list)]
            scored = [(copy.deepcopy(d), cosine(vector, d[path])) for d in candidates]
        scored.sort(key=lambda t: (-t[1], str(t[0].get("chunk_id", t[0].get("_id", "")))))
        return scored[:limit]

    def _raw(self) -> list[Doc]:
        return list(self._docs.values())


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
