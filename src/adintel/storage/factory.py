"""Process-wide database handle, selected by ``ADINTEL_STORAGE``."""

from __future__ import annotations

import threading

from adintel.config import get_settings
from adintel.storage.base import Database
from adintel.storage.collections import ensure_indexes

_db: Database | None = None
_lock = threading.Lock()


def get_database() -> Database:
    global _db
    with _lock:
        if _db is None:
            settings = get_settings()
            if settings.storage == "mongo":
                from adintel.storage.mongo import MongoDatabase

                _db = MongoDatabase(settings.mongo_uri, settings.mongo_db, settings.vector_search)
            else:
                from adintel.storage.memory import MemoryDatabase

                _db = MemoryDatabase()
            ensure_indexes(_db)
        return _db


def set_database(db: Database) -> None:
    global _db
    with _lock:
        ensure_indexes(db)
        _db = db


def reset_database() -> None:
    global _db
    with _lock:
        _db = None
