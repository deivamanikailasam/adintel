"""Tenant isolation, layer 1: the data-access layer.

``TenantScopedRepo`` is the only way agents and API handlers touch tenant data. It injects the
tenant from the run/request context into every filter and every inserted document. If a caller
supplies a filter or document naming a *different* tenant, it raises ``TenantIsolationViolation``
and fires the violation hook (metric + P1 page), because that is either a bug or an attack.

``SystemRepo`` is the explicit, audited escape hatch for cross-tenant system jobs (scheduler,
reconciliation, audit verification). It requires a stated purpose and is never handed to agents.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Sequence
from typing import Any

from adintel.core.errors import TenantIsolationViolation
from adintel.storage.base import Database, Doc, Filter, SortSpec
from adintel.storage.collections import BY_NAME

log = logging.getLogger(__name__)

ViolationHook = Callable[[str, str, str], None]  # (tenant_id, collection, detail)
_violation_hooks: list[ViolationHook] = []


def register_violation_hook(hook: ViolationHook) -> None:
    _violation_hooks.append(hook)


def _fire(tenant_id: str, collection: str, detail: str) -> None:
    log.critical(
        "tenant_isolation_violation", extra={"tenant_id": tenant_id, "collection": collection, "detail": detail}
    )
    for hook in _violation_hooks:
        try:
            hook(tenant_id, collection, detail)
        except Exception:
            log.exception("violation_hook_failed")


def _foreign_tenants(flt: Any, tenant_id: str) -> list[Any]:
    """Every ``tenant_id`` value mentioned anywhere in a filter that is not ``tenant_id``."""
    found: list[Any] = []
    if isinstance(flt, dict):
        for k, v in flt.items():
            if k == "tenant_id":
                if v != tenant_id:
                    found.append(v)
            else:
                found.extend(_foreign_tenants(v, tenant_id))
    elif isinstance(flt, list):
        for item in flt:
            found.extend(_foreign_tenants(item, tenant_id))
    return found


class TenantScopedRepo:
    def __init__(self, db: Database, collection: str, tenant_id: str) -> None:
        if not tenant_id:
            raise TenantIsolationViolation("TenantScopedRepo requires a tenant_id")
        spec = BY_NAME.get(collection)
        if spec is None:
            raise ValueError(f"unknown collection {collection!r}")
        if not spec.tenant_scoped:
            raise ValueError(f"{collection!r} is not tenant-scoped; use SystemRepo")
        self._coll = db.collection(collection)
        self.collection = collection
        self.tenant_id = tenant_id

    # ---- scoping -------------------------------------------------------------------------------
    def _scope(self, flt: Filter | None) -> Filter:
        flt = dict(flt or {})
        foreign = _foreign_tenants(flt, self.tenant_id)
        if foreign:
            detail = f"filter referenced tenant(s) {foreign!r}"
            _fire(self.tenant_id, self.collection, detail)
            raise TenantIsolationViolation(f"{self.collection}: {detail}")
        flt["tenant_id"] = self.tenant_id
        return flt

    def _stamp(self, doc: Doc) -> Doc:
        if "tenant_id" in doc and doc["tenant_id"] != self.tenant_id:
            detail = f"insert carried tenant {doc['tenant_id']!r}"
            _fire(self.tenant_id, self.collection, detail)
            raise TenantIsolationViolation(f"{self.collection}: {detail}")
        return {**doc, "tenant_id": self.tenant_id}

    def _check_update(self, update: Doc) -> None:
        for op in ("$set", "$setOnInsert"):
            if "tenant_id" in update.get(op, {}) and update[op]["tenant_id"] != self.tenant_id:
                detail = "update tried to rewrite tenant_id"
                _fire(self.tenant_id, self.collection, detail)
                raise TenantIsolationViolation(f"{self.collection}: {detail}")

    # ---- operations ----------------------------------------------------------------------------
    def insert(self, doc: Doc) -> None:
        self._coll.insert_one(self._stamp(doc))

    def insert_many(self, docs: Sequence[Doc]) -> None:
        self._coll.insert_many([self._stamp(d) for d in docs])

    def find(
        self,
        flt: Filter | None = None,
        *,
        sort: SortSpec | None = None,
        limit: int | None = None,
        projection: dict[str, int] | None = None,
    ) -> list[Doc]:
        return self._coll.find(self._scope(flt), sort=sort, limit=limit, projection=projection)

    def find_one(self, flt: Filter | None = None, *, sort: SortSpec | None = None) -> Doc | None:
        return self._coll.find_one(self._scope(flt), sort=sort)

    def update_one(self, flt: Filter, update: Doc, *, upsert: bool = False) -> int:
        self._check_update(update)
        if upsert:
            update = {**update, "$setOnInsert": {**update.get("$setOnInsert", {}), "tenant_id": self.tenant_id}}
        return self._coll.update_one(self._scope(flt), update, upsert=upsert)

    def update_many(self, flt: Filter, update: Doc) -> int:
        self._check_update(update)
        return self._coll.update_many(self._scope(flt), update)

    def count(self, flt: Filter | None = None) -> int:
        return self._coll.count(self._scope(flt))

    def vector_search(
        self, vector: Sequence[float], flt: Filter, *, limit: int, num_candidates: int
    ) -> list[tuple[Doc, float]]:
        """Tenant isolation, layer 2: the tenant pre-filter runs *inside* the vector query."""
        return self._coll.vector_search(vector, self._scope(flt), limit=limit, num_candidates=num_candidates)

    def soft_delete(self, flt: Filter) -> int:
        """Evidence is never hard-deleted; it is deactivated so old citations stay auditable."""
        return self._coll.update_many(self._scope(flt), {"$set": {"is_active": False}})


class SystemRepo:
    """Cross-tenant access for system jobs. Requires a purpose string, which is logged."""

    def __init__(self, db: Database, collection: str, *, purpose: str) -> None:
        if not purpose:
            raise ValueError("SystemRepo requires a purpose")
        self._coll = db.collection(collection)
        self.collection = collection
        self.purpose = purpose
        log.info("system_repo_opened", extra={"collection": collection, "purpose": purpose})

    def find(self, flt: Filter | None = None, *, sort: SortSpec | None = None, limit: int | None = None) -> list[Doc]:
        return self._coll.find(dict(flt or {}), sort=sort, limit=limit)

    def find_one(self, flt: Filter | None = None) -> Doc | None:
        return self._coll.find_one(dict(flt or {}))

    def insert(self, doc: Doc) -> None:
        self._coll.insert_one(doc)

    def update_one(self, flt: Filter, update: Doc, *, upsert: bool = False) -> int:
        return self._coll.update_one(flt, update, upsert=upsert)

    def delete_many(self, flt: Filter) -> int:
        return self._coll.delete_many(flt)

    def count(self, flt: Filter | None = None) -> int:
        return self._coll.count(dict(flt or {}))
