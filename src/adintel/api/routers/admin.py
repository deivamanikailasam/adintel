from __future__ import annotations

from collections import defaultdict
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from adintel.api.deps import SENIORS, db, require
from adintel.audit import AuditLog
from adintel.core.clock import utcnow
from adintel.domain.enums import Role
from adintel.feedback.triage import weekly_triage
from adintel.harness.flags import DEFAULTS, FeatureFlags
from adintel.harness.killswitch import KillSwitches
from adintel.llm.registry import get_registry
from adintel.privacy.subjects import erase_user, export_user
from adintel.queueing import AGENT_RUNS, EXECUTIONS, get_queue
from adintel.security.auth import Principal
from adintel.storage.base import Database
from adintel.storage.tenant_repo import TenantScopedRepo

router = APIRouter(prefix="/admin", tags=["admin"])


class Switch(BaseModel):
    scope: str
    key: str
    engaged: bool
    reason: str


@router.get("/kill-switches")
def switches(
    p: Principal = Depends(require(Role.ADMIN, *SENIORS)), database: Database = Depends(db)
) -> list[dict[str, Any]]:
    return KillSwitches(database).list()


@router.post("/kill-switches")
def set_switch(
    body: Switch, p: Principal = Depends(require(Role.ADMIN)), database: Database = Depends(db)
) -> dict[str, Any]:
    key = body.key
    if body.scope == "tenant":
        key = p.tenant_id  # an admin can only switch off their own tenant
    if body.scope == "brand":
        key = f"{p.tenant_id}/{body.key.split('/')[-1]}"
    return KillSwitches(database).set(
        body.scope, key, body.engaged, actor_id=p.user_id, reason=body.reason, tenant_id_for_audit=p.tenant_id
    )


class FlagChange(BaseModel):
    flag: str
    enabled: bool
    reason: str
    brand_id: str | None = None


@router.get("/flags")
def flags(
    brand_id: str | None = None,
    p: Principal = Depends(require(Role.ADMIN, *SENIORS)),
    database: Database = Depends(db),
) -> dict[str, Any]:
    ff = FeatureFlags(database, p.tenant_id)
    return {"defaults": DEFAULTS, "effective": ff.effective(brand_id=brand_id), "overrides": ff.overrides()}


@router.post("/flags")
def set_flag(
    body: FlagChange, p: Principal = Depends(require(Role.ADMIN)), database: Database = Depends(db)
) -> dict[str, Any]:
    if body.flag not in DEFAULTS:
        raise HTTPException(422, f"unknown flag; one of {sorted(DEFAULTS)}")
    return FeatureFlags(database, p.tenant_id).set(
        body.flag, body.enabled, actor_id=p.user_id, reason=body.reason, brand_id=body.brand_id
    )


@router.get("/triage")
def triage(
    days: int = 7, p: Principal = Depends(require(Role.ADMIN, *SENIORS)), database: Database = Depends(db)
) -> dict[str, Any]:
    return weekly_triage(database, p.tenant_id, days=max(1, min(days, 90)))


@router.get("/outcomes")
def outcomes(
    p: Principal = Depends(require(Role.ADMIN, *SENIORS)), database: Database = Depends(db)
) -> list[dict[str, Any]]:
    return TenantScopedRepo(database, "outcomes", p.tenant_id).find({}, sort=[("measured_at", -1)], limit=200)


class Erasure(BaseModel):
    reason: str


@router.get("/privacy/users/{user_id}/export")
def privacy_export(
    user_id: str, p: Principal = Depends(require(Role.ADMIN)), database: Database = Depends(db)
) -> dict[str, Any]:
    try:
        return export_user(database, p.tenant_id, user_id, actor_id=p.user_id)
    except LookupError as exc:
        raise HTTPException(404, "user not found") from exc


@router.post("/privacy/users/{user_id}/erase")
def privacy_erase(
    user_id: str, body: Erasure, p: Principal = Depends(require(Role.ADMIN)), database: Database = Depends(db)
) -> dict[str, int]:
    if user_id == p.user_id:
        raise HTTPException(409, "ask another admin to erase your own account")
    try:
        return erase_user(database, p.tenant_id, user_id, actor_id=p.user_id, reason=body.reason)
    except LookupError as exc:
        raise HTTPException(404, "user not found") from exc


@router.get("/audit/verify")
def verify(p: Principal = Depends(require(Role.ADMIN)), database: Database = Depends(db)) -> dict[str, Any]:
    return AuditLog(database, p.tenant_id).verify().model_dump()


@router.get("/audit")
def audit(
    subject_id: str | None = None,
    run_id: str | None = None,
    limit: int = 200,
    p: Principal = Depends(require(Role.ADMIN, *SENIORS)),
    database: Database = Depends(db),
) -> list[dict[str, Any]]:
    return [
        e.model_dump(mode="json")
        for e in AuditLog(database, p.tenant_id).entries(subject_id=subject_id, run_id=run_id, limit=min(limit, 1000))
    ]


@router.get("/cost")
def cost(
    day: str | None = None, p: Principal = Depends(require(Role.ADMIN, *SENIORS)), database: Database = Depends(db)
) -> dict[str, Any]:
    d = day or utcnow().date().isoformat()
    rows = TenantScopedRepo(database, "cost_events", p.tenant_id).find({"day": d})
    by_brand: dict[str, float] = defaultdict(float)
    by_agent: dict[str, float] = defaultdict(float)
    for r in rows:
        by_brand[str(r.get("brand_id"))] += r["cost_usd"]
        by_agent[r["agent"]] += r["cost_usd"]
    return {
        "day": d,
        "notional": True,
        "total_usd": round(sum(by_brand.values()), 6),
        "by_brand": {k: round(v, 6) for k, v in by_brand.items()},
        "by_agent": {k: round(v, 6) for k, v in by_agent.items()},
    }


@router.get("/models")
def models(p: Principal = Depends(require(Role.ADMIN, *SENIORS))) -> dict[str, Any]:
    reg = get_registry()
    health: dict[str, Any] = {}
    for name, tier in reg.tiers.items():
        if tier.provider == "openai_compat":
            from adintel.llm.providers.openai_compat import OpenAICompatProvider

            health[name] = OpenAICompatProvider.shared().health(tier)
    return {**reg.describe(), "health": health}


@router.get("/notifications")
def notifications(
    p: Principal = Depends(require(Role.ADMIN, *SENIORS, Role.ACCOUNT_MANAGER)), database: Database = Depends(db)
) -> list[dict[str, Any]]:
    return TenantScopedRepo(database, "notifications", p.tenant_id).find({}, sort=[("created_at", -1)], limit=100)


@router.get("/platform-alerts")
def platform_alerts(
    p: Principal = Depends(require(Role.ADMIN)), database: Database = Depends(db)
) -> list[dict[str, Any]]:
    """Infrastructure alerts from Alertmanager (no client data): what on-call is dealing with right now."""
    return TenantScopedRepo(database, "notifications", "_system").find(
        {"kind": "platform_alert"}, sort=[("created_at", -1)], limit=100
    )


@router.get("/queues")
def queues(p: Principal = Depends(require(Role.ADMIN))) -> dict[str, Any]:
    return {q: {"depth": get_queue(q).depth(), "dlq": get_queue(q).dlq_depth()} for q in (AGENT_RUNS, EXECUTIONS)}
