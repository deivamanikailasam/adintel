"""Storage layer.

Agents never see a raw collection: they receive a :class:`TenantScopedRepo`, which injects and
enforces the tenant filter on every operation. Two interchangeable backends implement
:class:`Database`: ``memory`` (tests, zero-dependency demo) and ``mongo`` (MongoDB Atlas / Atlas Local).
"""

from adintel.storage.base import Collection, Database, DuplicateKey
from adintel.storage.factory import get_database, reset_database, set_database
from adintel.storage.tenant_repo import SystemRepo, TenantScopedRepo

__all__ = [
    "Collection",
    "Database",
    "DuplicateKey",
    "SystemRepo",
    "TenantScopedRepo",
    "get_database",
    "reset_database",
    "set_database",
]
