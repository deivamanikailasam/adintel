"""MongoDB backend (MongoDB Atlas in production, ``mongodb/mongodb-atlas-local`` in development).

Vector search uses ``$vectorSearch`` with a pre-filter when the server supports it (Atlas / Atlas
Local). With ``ADINTEL_VECTOR_SEARCH=auto`` it falls back to brute-force cosine over the
*tenant-filtered* candidate set, so isolation semantics are identical either way.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from typing import Any

from adintel.storage.base import Collection, Database, Doc, DuplicateKey, Filter, SortSpec
from adintel.storage.memory import cosine

log = logging.getLogger(__name__)

VECTOR_INDEX_NAME = "kb_vector"


class MongoCollection(Collection):
    def __init__(self, coll: Any, vector_mode: str) -> None:
        self._c = coll
        self.name = coll.name
        self._vector_mode = vector_mode

    @staticmethod
    def _strip(doc: Doc | None) -> Doc | None:
        if doc is not None:
            doc.pop("_id", None)
        return doc

    def insert_one(self, doc: Doc) -> None:
        from pymongo.errors import DuplicateKeyError

        try:
            self._c.insert_one(dict(doc))
        except DuplicateKeyError as exc:
            raise DuplicateKey(str(exc)) from exc

    def insert_many(self, docs: Sequence[Doc]) -> None:
        from pymongo.errors import BulkWriteError

        if not docs:
            return
        try:
            self._c.insert_many([dict(d) for d in docs], ordered=True)
        except BulkWriteError as exc:
            raise DuplicateKey(str(exc)) from exc

    def find(
        self,
        flt: Filter,
        *,
        sort: SortSpec | None = None,
        limit: int | None = None,
        projection: dict[str, int] | None = None,
    ) -> list[Doc]:
        cur = self._c.find(flt, projection)
        if sort:
            cur = cur.sort(list(sort))
        if limit is not None:
            cur = cur.limit(limit)
        return [self._strip(d) or {} for d in cur]

    def update_one(self, flt: Filter, update: Doc, *, upsert: bool = False) -> int:
        from pymongo.errors import DuplicateKeyError

        try:
            return int(self._c.update_one(flt, update, upsert=upsert).matched_count)
        except DuplicateKeyError as exc:
            raise DuplicateKey(str(exc)) from exc

    def update_many(self, flt: Filter, update: Doc) -> int:
        return int(self._c.update_many(flt, update).matched_count)

    def delete_many(self, flt: Filter) -> int:
        return int(self._c.delete_many(flt).deleted_count)

    def count(self, flt: Filter) -> int:
        return int(self._c.count_documents(flt))

    def create_index(
        self, keys: Sequence[tuple[str, int]], *, unique: bool = False, ttl_seconds: int | None = None
    ) -> None:
        kwargs: dict[str, Any] = {"unique": unique}
        if ttl_seconds is not None:
            kwargs["expireAfterSeconds"] = ttl_seconds
        self._c.create_index(list(keys), **kwargs)

    def vector_search(
        self, vector: Sequence[float], flt: Filter, *, limit: int, num_candidates: int, path: str = "embedding"
    ) -> list[tuple[Doc, float]]:
        if self._vector_mode in ("atlas", "auto"):
            try:
                pipeline = [
                    {
                        "$vectorSearch": {
                            "index": VECTOR_INDEX_NAME,
                            "path": path,
                            "queryVector": list(vector),
                            "numCandidates": num_candidates,
                            "limit": limit,
                            "filter": flt,
                        }
                    },
                    {"$addFields": {"_score": {"$meta": "vectorSearchScore"}}},
                ]
                out: list[tuple[Doc, float]] = []
                for d in self._c.aggregate(pipeline):
                    score = float(d.pop("_score", 0.0))
                    d.pop("_id", None)
                    # Atlas cosine score is (1 + cos) / 2; convert back to cosine for one scale everywhere.
                    out.append((d, 2 * score - 1))
                out.sort(key=lambda t: (-t[1], str(t[0].get("chunk_id", ""))))
                return out
            except Exception as exc:  # noqa: BLE001 - any server-side failure falls back below
                if self._vector_mode == "atlas":
                    raise
                log.warning("vector_search_fallback", extra={"reason": str(exc)[:200]})
        docs = [d for d in self.find(flt) if isinstance(d.get(path), list)]
        scored = [(d, cosine(vector, d[path])) for d in docs]
        scored.sort(key=lambda t: (-t[1], str(t[0].get("chunk_id", ""))))
        return scored[:limit]


class MongoDatabase(Database):
    def __init__(self, uri: str, db_name: str, vector_mode: str = "auto") -> None:
        from pymongo import MongoClient

        self._client: Any = MongoClient(uri, serverSelectionTimeoutMS=5000, tz_aware=True, appname="adintel")
        self._db = self._client[db_name]
        self._vector_mode = vector_mode

    def collection(self, name: str) -> MongoCollection:
        return MongoCollection(self._db[name], self._vector_mode)

    def ping(self) -> bool:
        try:
            self._client.admin.command("ping")
            return True
        except Exception:  # noqa: BLE001
            return False

    def ensure_vector_index(self, collection: str, dimensions: int, filter_paths: Sequence[str]) -> None:
        if self._vector_mode == "python":
            return
        try:
            from pymongo.operations import SearchIndexModel

            coll = self._db[collection]
            existing = {ix.get("name") for ix in coll.list_search_indexes()}
            if VECTOR_INDEX_NAME in existing:
                return
            fields: list[dict[str, Any]] = [
                {"type": "vector", "path": "embedding", "numDimensions": dimensions, "similarity": "cosine"}
            ]
            fields += [{"type": "filter", "path": p} for p in filter_paths]
            coll.create_search_index(
                SearchIndexModel(definition={"fields": fields}, name=VECTOR_INDEX_NAME, type="vectorSearch")
            )
            log.info("vector_index_created", extra={"collection": collection, "dims": dimensions})
        except Exception as exc:  # noqa: BLE001
            if self._vector_mode == "atlas":
                raise
            log.warning("vector_index_unavailable", extra={"reason": str(exc)[:200]})
