from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from adintel.api.deps import ANY_STAFF, APPROVERS, SENIORS, check_brand, db, require
from adintel.approvals.service import REJECTION_CATEGORIES, ApprovalService, load_user
from adintel.core.errors import ApprovalError
from adintel.memory.procedural import DISMISSAL_REASONS, ProceduralMemory
from adintel.security.auth import Principal
from adintel.storage.base import Database
from adintel.storage.tenant_repo import TenantScopedRepo

router = APIRouter(tags=["approvals"])


@router.get("/recommendations")
def list_recs(
    status: str | None = None,
    brand_id: str | None = None,
    p: Principal = Depends(require(*ANY_STAFF)),
    database: Database = Depends(db),
) -> list[dict[str, Any]]:
    flt: dict[str, Any] = {}
    if status:
        flt["status"] = status
    if brand_id:
        check_brand(p, brand_id)
        flt["brand_id"] = brand_id
    rows = TenantScopedRepo(database, "recommendations", p.tenant_id).find(flt, sort=[("created_at", -1)], limit=200)
    return [r for r in rows if p.can_see_brand(r["brand_id"])]


@router.get("/recommendations/{rec_id}")
def get_rec(
    rec_id: str, p: Principal = Depends(require(*ANY_STAFF)), database: Database = Depends(db)
) -> dict[str, Any]:
    """The approval screen: the recommendation plus its evidence, one click away."""
    t = p.tenant_id
    rec = TenantScopedRepo(database, "recommendations", t).find_one({"recommendation_id": rec_id})
    if rec is None:
        raise HTTPException(404, "recommendation not found")
    check_brand(p, rec["brand_id"])
    anomaly = TenantScopedRepo(database, "anomalies", t).find_one({"anomaly_id": rec.get("anomaly_id")})
    history = TenantScopedRepo(database, "run_history", t).find_one({"run_id": rec["run_id"]})
    return {
        "recommendation": rec,
        "anomaly": anomaly,
        "root_causes": (history or {}).get("root_causes", []),
        "approval_requirement": _requirement(rec),
        "audit": TenantScopedRepo(database, "audit_log", t).find({"subject_id": rec_id}, sort=[("seq", 1)]),
    }


def _requirement(rec: dict[str, Any]) -> str:
    from adintel.approvals.matrix import requirement
    from adintel.domain.models import Recommendation

    r = Recommendation.from_doc(rec)
    return requirement(r, r.daily_exposure_usd).description


class ApproveBody(BaseModel):
    typed_exposure_usd: float
    modified_amount_usd_per_day: float | None = None


@router.post("/recommendations/{rec_id}/approve")
def approve(
    rec_id: str, body: ApproveBody, p: Principal = Depends(require(*APPROVERS)), database: Database = Depends(db)
) -> dict[str, Any]:
    try:
        return ApprovalService(database, p.tenant_id).approve(
            rec_id,
            load_user(database, p.tenant_id, p.user_id),
            typed_exposure_usd=body.typed_exposure_usd,
            modified_amount_usd_per_day=body.modified_amount_usd_per_day,
        )
    except ApprovalError as exc:
        raise HTTPException(409, {"check": exc.check, "message": exc.message}) from exc


class RejectBody(BaseModel):
    category: str
    note: str = ""


@router.post("/recommendations/{rec_id}/reject")
def reject(
    rec_id: str, body: RejectBody, p: Principal = Depends(require(*APPROVERS)), database: Database = Depends(db)
) -> dict[str, Any]:
    try:
        return ApprovalService(database, p.tenant_id).reject(
            rec_id, load_user(database, p.tenant_id, p.user_id), category=body.category, note=body.note
        )
    except ApprovalError as exc:
        raise HTTPException(409, {"check": exc.check, "message": exc.message}) from exc


@router.get("/meta/rejection-categories")
def categories() -> dict[str, Any]:
    return {"rejection": list(REJECTION_CATEGORIES), "dismissal": list(DISMISSAL_REASONS)}


@router.get("/anomalies")
def list_anomalies(
    brand_id: str | None = None,
    status: str = "open",
    p: Principal = Depends(require(*ANY_STAFF)),
    database: Database = Depends(db),
) -> list[dict[str, Any]]:
    flt: dict[str, Any] = {"status": status}
    if brand_id:
        check_brand(p, brand_id)
        flt["brand_id"] = brand_id
    rows = TenantScopedRepo(database, "anomalies", p.tenant_id).find(flt, sort=[("created_at", -1)], limit=200)
    return [r for r in rows if p.can_see_brand(r["brand_id"])]


class DismissBody(BaseModel):
    reason: str
    note: str = ""


@router.post("/anomalies/{anomaly_id}/dismiss")
def dismiss(
    anomaly_id: str, body: DismissBody, p: Principal = Depends(require(*APPROVERS)), database: Database = Depends(db)
) -> dict[str, Any]:
    try:
        return ProceduralMemory(database, p.tenant_id).dismiss(
            anomaly_id, load_user(database, p.tenant_id, p.user_id), reason=body.reason, note=body.note
        )
    except (KeyError, ValueError) as exc:
        raise HTTPException(400, str(exc)) from exc


@router.get("/rule-proposals")
def proposals(p: Principal = Depends(require(*ANY_STAFF)), database: Database = Depends(db)) -> list[dict[str, Any]]:
    return TenantScopedRepo(database, "rule_proposals", p.tenant_id).find({"status": "proposed"})


class Decision(BaseModel):
    approve: bool


@router.post("/rule-proposals/{proposal_id}/decision")
def decide(
    proposal_id: str, body: Decision, p: Principal = Depends(require(*SENIORS)), database: Database = Depends(db)
) -> dict[str, Any]:
    return ProceduralMemory(database, p.tenant_id).decide(
        proposal_id, load_user(database, p.tenant_id, p.user_id), approve=body.approve
    )
