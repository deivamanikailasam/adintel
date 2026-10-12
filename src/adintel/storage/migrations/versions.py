"""The migration list. Append only; never edit or reorder an applied migration (``status`` flags drift).

Each ``up`` must be idempotent: its filter selects only documents that still need the change.
"""

from __future__ import annotations

from typing import Any

from adintel.domain.models import BrandProfile
from adintel.storage.base import Database
from adintel.storage.collections import ensure_indexes
from adintel.storage.migrations import Migration
from adintel.storage.tenant_repo import SystemRepo


def _baseline(db: Database) -> dict[str, Any]:
    ensure_indexes(db)
    return {"indexes": "ensured"}


def _brand_profile_defaults(db: Database) -> dict[str, Any]:
    """Brands created before brand profiles existed get the default profile (tone cluster, timezone…)."""
    repo = SystemRepo(db, "brands", purpose="migration 0002")
    default = BrandProfile().model_dump(mode="json")
    n = 0
    for b in repo.find({"profile": {"$exists": False}}):
        n += repo.update_one({"tenant_id": b["tenant_id"], "brand_id": b["brand_id"]}, {"$set": {"profile": default}})
    return {"brands_backfilled": n}


def _tenant_active_flag(db: Database) -> dict[str, Any]:
    """Make ``active`` explicit on every tenant (offboarding sets it to false; readers stop guessing)."""
    repo = SystemRepo(db, "tenants", purpose="migration 0003")
    n = 0
    for t in repo.find({"active": {"$exists": False}}):
        n += repo.update_one({"tenant_id": t["tenant_id"]}, {"$set": {"active": True}})
    return {"tenants_backfilled": n}


MIGRATIONS: list[Migration] = [
    Migration("0001_baseline_indexes", "Create every catalogued index", _baseline),
    Migration("0002_brand_profile_defaults", "Backfill default brand profiles", _brand_profile_defaults),
    Migration("0003_tenant_active_flag", "Make tenants.active explicit", _tenant_active_flag),
]
