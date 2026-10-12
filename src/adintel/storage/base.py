"""Backend-neutral storage interfaces (a deliberately small subset of the MongoDB API)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence
from typing import Any

from adintel.core.errors import AdIntelError

Doc = dict[str, Any]
Filter = dict[str, Any]
SortSpec = Sequence[tuple[str, int]]


class DuplicateKey(AdIntelError):
    """A unique index rejected the write (idempotency keys rely on this)."""


class Collection(ABC):
    name: str

    @abstractmethod
    def insert_one(self, doc: Doc) -> None: ...

    def insert_many(self, docs: Sequence[Doc]) -> None:
        for d in docs:
            self.insert_one(d)

    @abstractmethod
    def find(
        self,
        flt: Filter,
        *,
        sort: SortSpec | None = None,
        limit: int | None = None,
        projection: dict[str, int] | None = None,
    ) -> list[Doc]: ...

    def find_one(self, flt: Filter, *, sort: SortSpec | None = None) -> Doc | None:
        rows = self.find(flt, sort=sort, limit=1)
        return rows[0] if rows else None

    @abstractmethod
    def update_one(self, flt: Filter, update: Doc, *, upsert: bool = False) -> int: ...

    @abstractmethod
    def update_many(self, flt: Filter, update: Doc) -> int: ...

    @abstractmethod
    def delete_many(self, flt: Filter) -> int: ...

    @abstractmethod
    def count(self, flt: Filter) -> int: ...

    @abstractmethod
    def create_index(
        self, keys: Sequence[tuple[str, int]], *, unique: bool = False, ttl_seconds: int | None = None
    ) -> None: ...

    @abstractmethod
    def vector_search(
        self, vector: Sequence[float], flt: Filter, *, limit: int, num_candidates: int, path: str = "embedding"
    ) -> list[tuple[Doc, float]]:
        """Return (doc, cosine similarity) pairs. ``flt`` is a *pre-filter* applied inside the search."""


class Database(ABC):
    @abstractmethod
    def collection(self, name: str) -> Collection: ...

    @abstractmethod
    def ping(self) -> bool: ...

    def ensure_vector_index(self, collection: str, dimensions: int, filter_paths: Sequence[str]) -> None:
        """Create the vector index if the backend needs one (no-op for memory)."""
        return None
