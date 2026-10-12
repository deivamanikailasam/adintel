from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from adintel.api.deps import ANY_STAFF, check_brand, db, require
from adintel.security.auth import Principal
from adintel.storage.base import Database
from adintel.storage.tenant_repo import TenantScopedRepo

router = APIRouter(tags=["brands"])


@router.get("/brands")
def list_brands(p: Principal = Depends(require(*ANY_STAFF)), database: Database = Depends(db)) -> list[dict[str, Any]]:
    out = []
    runs = TenantScopedRepo(database, "runs", p.tenant_id)
    for b in TenantScopedRepo(database, "brands", p.tenant_id).find({}, sort=[("name", 1)]):
        if not p.can_see_brand(b["brand_id"]):
            continue
        last = runs.find_one({"brand_id": b["brand_id"]}, sort=[("created_at", -1)])
        out.append(
            {
                **b,
                "last_run": {k: last.get(k) for k in ("run_id", "status", "health", "finished_at", "path")}
                if last
                else None,
            }
        )
    return out


@router.get("/brands/{brand_id}/summary")
def brand_summary(
    brand_id: str, p: Principal = Depends(require(*ANY_STAFF)), database: Database = Depends(db)
) -> dict[str, Any]:
    check_brand(p, brand_id)
    t = p.tenant_id
    brand = TenantScopedRepo(database, "brands", t).find_one({"brand_id": brand_id})
    if brand is None:
        raise HTTPException(404, "brand not found")
    return {
        "brand": brand,
        "runs": TenantScopedRepo(database, "runs", t).find({"brand_id": brand_id}, sort=[("created_at", -1)], limit=10),
        "open_anomalies": TenantScopedRepo(database, "anomalies", t).find(
            {"brand_id": brand_id, "status": "open"}, limit=20
        ),
        "latest_report": TenantScopedRepo(database, "reports", t).find_one(
            {"brand_id": brand_id}, sort=[("created_at", -1)]
        ),
        "rules": TenantScopedRepo(database, "brand_rules", t).find_one({"brand_id": brand_id}),
    }
