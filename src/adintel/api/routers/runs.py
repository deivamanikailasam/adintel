from __future__ import annotations

import time
from collections.abc import Iterator
from datetime import date, timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from adintel.api.deps import ANY_STAFF, APPROVERS, check_brand, db, require
from adintel.api.sse import sse
from adintel.core.clock import utcnow
from adintel.core.errors import AdIntelError, KillSwitchEngaged, RateLimited
from adintel.graph import events
from adintel.graph.engine import RunEngine
from adintel.queueing import AGENT_RUNS, get_queue
from adintel.security.auth import Principal
from adintel.storage.base import Database
from adintel.storage.tenant_repo import TenantScopedRepo

router = APIRouter(tags=["runs"])


class RunRequest(BaseModel):
    brand_id: str
    period_start: date | None = None
    period_end: date | None = None
    goal: str = "weekly_report"


def default_period(today: date) -> tuple[date, date]:
    """The last complete Monday–Sunday week."""
    end = today - timedelta(days=today.weekday() + 1)
    return end - timedelta(days=6), end


@router.post("/runs", status_code=202)
def create_run(body: RunRequest, p: Principal = Depends(require(*APPROVERS)),
               database: Database = Depends(db)) -> dict[str, Any]:
    check_brand(p, body.brand_id)
    start, end = (body.period_start, body.period_end) if body.period_start and body.period_end else \
        default_period(utcnow().date())
    try:
        doc, created = RunEngine(database).start(tenant_id=p.tenant_id, brand_id=body.brand_id, period_start=start,
                                                 period_end=end, goal=body.goal, trigger="api",
                                                 requested_by=p.user_id)
    except KillSwitchEngaged as exc:
        raise HTTPException(423, f"kill switch engaged: {exc}") from exc
    except RateLimited as exc:
        raise HTTPException(429, str(exc)) from exc
    except AdIntelError as exc:
        raise HTTPException(400, str(exc)) from exc
    if created:
        get_queue(AGENT_RUNS).send({"tenant_id": p.tenant_id, "run_id": doc["run_id"]}, dedup_id=doc["run_id"])
    return {"run_id": doc["run_id"], "created": created, "status": doc["status"]}


@router.get("/runs")
def list_runs(brand_id: str | None = None, limit: int = 50, p: Principal = Depends(require(*ANY_STAFF)),
              database: Database = Depends(db)) -> list[dict[str, Any]]:
    flt: dict[str, Any] = {}
    if brand_id:
        check_brand(p, brand_id)
        flt["brand_id"] = brand_id
    rows = TenantScopedRepo(database, "runs", p.tenant_id).find(flt, sort=[("created_at", -1)], limit=min(limit, 200))
    return [r for r in rows if p.can_see_brand(r["brand_id"])]


def _run(database: Database, p: Principal, run_id: str) -> dict[str, Any]:
    run = TenantScopedRepo(database, "runs", p.tenant_id).find_one({"run_id": run_id})
    if run is None:
        raise HTTPException(404, "run not found")
    check_brand(p, run["brand_id"])
    return run


@router.get("/runs/{run_id}")
def get_run(run_id: str, p: Principal = Depends(require(*ANY_STAFF)), database: Database = Depends(db)) -> dict[str, Any]:
    return _run(database, p, run_id)


@router.get("/runs/{run_id}/trace")
def run_trace(run_id: str, p: Principal = Depends(require(*ANY_STAFF)),
              database: Database = Depends(db)) -> dict[str, Any]:
    """Explainability: from any report or recommendation, walk back to every step, model call and source."""
    run = _run(database, p, run_id)
    t = p.tenant_id
    cp = TenantScopedRepo(database, "run_checkpoints", t).find_one({"run_id": run_id}, sort=[("step", -1)])
    state = __import__("json").loads(cp["state"]) if cp else {}
    calls = TenantScopedRepo(database, "llm_calls", t).find({"run_id": run_id}, sort=[("created_at", 1)])
    archive = TenantScopedRepo(database, "prompt_archive", t)
    for c in calls:
        c.pop("expire_at", None)
        prompt = archive.find_one({"sha256": c["prompt_hash"]})
        response = archive.find_one({"sha256": c["response_hash"]})
        c["prompt"] = prompt["body"] if prompt else None
        c["response"] = response["body"] if response else None
    chunk_ids = sorted({cid for c in calls for cid in c.get("retrieved_doc_ids", [])})
    chunks = TenantScopedRepo(database, "kb_chunks", t).find({"chunk_id": {"$in": chunk_ids}},
                                                             projection={"embedding": 0}) if chunk_ids else []
    return {"run": run, "decisions": state.get("decisions", []), "traces": state.get("traces", []),
            "degradations": state.get("degradations", []), "dq": state.get("dq"),
            "anomalies": state.get("anomalies", []), "root_causes": state.get("root_causes", []),
            "recommendations": state.get("recommendations", []), "guardrail": state.get("guardrail"),
            "llm_calls": calls, "retrieved_sources": chunks,
            "audit": [e for e in TenantScopedRepo(database, "audit_log", t).find({"run_id": run_id},
                                                                                sort=[("seq", 1)])]}


@router.get("/runs/{run_id}/events")
def run_events(run_id: str, request: Request, p: Principal = Depends(require(*ANY_STAFF)),
               database: Database = Depends(db)) -> StreamingResponse:
    _run(database, p, run_id)
    last = int(request.headers.get("last-event-id", "0") or 0)

    def gen() -> Iterator[str]:
        nonlocal last
        deadline = time.monotonic() + 900
        while time.monotonic() < deadline:
            for ev in events.since(database, p.tenant_id, run_id, last):
                last = ev["seq"]
                yield sse({"kind": ev["kind"], **ev["data"], "at": ev["at"]}, event=ev["kind"], id=ev["seq"])
                if ev["kind"] in ("run_finished", "interrupted"):
                    return
            run = TenantScopedRepo(database, "runs", p.tenant_id).find_one({"run_id": run_id}) or {}
            if run.get("finished_at") and not events.since(database, p.tenant_id, run_id, last):
                yield sse({"kind": "run_finished", "status": run.get("status")}, event="run_finished")
                return
            yield ": keep-alive\n\n"
            time.sleep(0.5)

    return StreamingResponse(gen(), media_type="text/event-stream", headers={"Cache-Control": "no-cache",
                                                                            "X-Accel-Buffering": "no"})


@router.post("/runs/{run_id}/replay", status_code=202)
def replay(run_id: str, p: Principal = Depends(require(*APPROVERS)), database: Database = Depends(db)) -> dict[str, Any]:
    """Runbook 'report not delivered by 08:00': resume from the last checkpoint."""
    run = _run(database, p, run_id)
    if run["status"] not in ("running", "pending"):
        raise HTTPException(409, f"run is {run['status']}; only unfinished runs can be resumed")
    get_queue(AGENT_RUNS).send({"tenant_id": p.tenant_id, "run_id": run_id})
    return {"run_id": run_id, "requeued": True}


@router.get("/reports/{report_id}")
def get_report(report_id: str, p: Principal = Depends(require(*ANY_STAFF)),
               database: Database = Depends(db)) -> dict[str, Any]:
    r = TenantScopedRepo(database, "reports", p.tenant_id).find_one({"report_id": report_id})
    if r is None:
        raise HTTPException(404, "report not found")
    check_brand(p, r["brand_id"])
    return r


class Rating(BaseModel):
    rating: int
    comment: str = ""


@router.post("/reports/{report_id}/rating")
def rate_report(report_id: str, body: Rating, p: Principal = Depends(require(*APPROVERS)),
                database: Database = Depends(db)) -> dict[str, Any]:
    from adintel.observability.metrics import REPORT_RATINGS

    if not 1 <= body.rating <= 5:
        raise HTTPException(422, "rating must be 1-5")
    r = get_report(report_id, p, database)
    TenantScopedRepo(database, "feedback", p.tenant_id).insert({
        "kind": "report_rating", "report_id": report_id, "brand_id": r["brand_id"], "rating": body.rating,
        "comment": body.comment[:1000], "user_id": p.user_id, "created_at": utcnow().isoformat()})
    REPORT_RATINGS.observe(body.rating)
    return {"ok": True}
