"""Scheduled jobs. Each is a plain function so it can run from APScheduler, the CLI or a test."""

from __future__ import annotations

import hashlib
import logging
from datetime import date, timedelta
from typing import Any

from adintel.approvals.service import ApprovalService
from adintel.audit import verify_all_tenants
from adintel.core.clock import utcnow
from adintel.core.errors import AdIntelError
from adintel.graph.engine import RunEngine
from adintel.observability.alerts import Severity, raise_alert
from adintel.observability.metrics import AUDIT_CHAIN_BROKEN
from adintel.queueing import AGENT_RUNS, EXECUTIONS, get_queue
from adintel.storage.base import Database
from adintel.storage.tenant_repo import SystemRepo, TenantScopedRepo

log = logging.getLogger(__name__)


def stagger_minutes(tenant_id: str, brand_id: str, window: int = 90) -> int:
    """Deterministic offset in [0, window) so 02:00 is not a thundering herd."""
    return int(hashlib.sha256(f"{tenant_id}/{brand_id}".encode()).hexdigest()[:8], 16) % window


def last_complete_week(today: date) -> tuple[date, date]:
    end = today - timedelta(days=today.weekday() + 1)
    return end - timedelta(days=6), end


def trigger_brand_run(db: Database, tenant_id: str, brand_id: str, *, today: date | None = None) -> dict[str, Any]:
    today = today or utcnow().date()
    start, end = last_complete_week(today)
    try:
        doc, created = RunEngine(db).start(tenant_id=tenant_id, brand_id=brand_id, period_start=start, period_end=end,
                                           trigger="schedule", schedule_date=today)
    except AdIntelError as exc:
        log.warning("scheduled_run_not_admitted", extra={"tenant_id": tenant_id, "brand_id": brand_id,
                                                         "reason": str(exc)})
        return {"admitted": False, "reason": str(exc)}
    if created:
        get_queue(AGENT_RUNS).send({"tenant_id": tenant_id, "run_id": doc["run_id"]}, dedup_id=doc["run_id"])
    return {"admitted": True, "run_id": doc["run_id"], "created": created}


def active_brands(db: Database) -> list[dict[str, Any]]:
    return [b for b in SystemRepo(db, "brands", purpose="scheduling").find({}) if b.get("active", True)]


def verify_audit_job(db: Database) -> dict[str, Any]:
    results = verify_all_tenants(db)
    broken = [r for r in results if not r.ok]
    for r in results:
        AUDIT_CHAIN_BROKEN.labels(tenant=r.tenant_id).set(0 if r.ok else 1)
    for r in broken:
        raise_alert(Severity.P1, "Audit hash chain break", tenant_id=r.tenant_id,
                    details={"seq": r.broken_at_seq, "reason": r.reason}, audience="security")
    return {"tenants": len(results), "broken": [r.tenant_id for r in broken]}


def expire_recommendations_job(db: Database) -> int:
    return sum(ApprovalService(db, t["tenant_id"]).expire_stale()
               for t in SystemRepo(db, "tenants", purpose="expiry").find())


def dlq_check_job() -> dict[str, int]:
    depths = {q: get_queue(q).dlq_depth() for q in (AGENT_RUNS, EXECUTIONS)}
    for q, n in depths.items():
        if n > 0:
            raise_alert(Severity.P2, f"Dead-letter queue {q} has {n} message(s)", details={"queue": q})
    return depths


def cost_anomaly_job(db: Database) -> list[str]:
    """Page on a > 2x day-over-day cost jump per tenant (runbook: cost spike over 2x)."""
    today = utcnow().date()
    flagged = []
    for t in SystemRepo(db, "tenants", purpose="cost check").find():
        repo = TenantScopedRepo(db, "cost_events", t["tenant_id"])
        cur = sum(r["cost_usd"] for r in repo.find({"day": today.isoformat()}))
        prev = sum(r["cost_usd"] for r in repo.find({"day": (today - timedelta(days=1)).isoformat()}))
        if prev > 0 and cur > 2 * prev:
            flagged.append(t["tenant_id"])
            raise_alert(Severity.P3, "AI cost more than 2x yesterday", tenant_id=t["tenant_id"],
                        details={"today": round(cur, 4), "yesterday": round(prev, 4)})
    return flagged


def narratives_job(db: Database) -> int:
    """Nightly: turn each campaign's last week into a sentence and index it (numbers are never embedded)."""
    from adintel.analytics.frames import load_frame, totals
    from adintel.rag.indexer import index_document
    from adintel.rag.narratives import campaign_narrative

    n = 0
    for b in active_brands(db):
        repo = TenantScopedRepo(db, "metrics_daily", b["tenant_id"])
        latest = repo.find_one({"brand_id": b["brand_id"]}, sort=[("date", -1)])
        if not latest:
            continue
        end = date.fromisoformat(latest["date"])
        start = end - timedelta(days=6)
        df = load_frame(repo, b["brand_id"], start - timedelta(days=7), end)
        for (platform, cid, cname), g in df.groupby(["platform", "campaign_id", "campaign_name"]):
            cur = totals(g[g["date"] >= start])
            prev = totals(g[g["date"] < start])
            text = campaign_narrative(brand_name=b["name"], platform=str(platform), campaign_name=str(cname),
                                      start=start, end=end, cur=cur, prev=prev)
            index_document(db, b["tenant_id"], doc_id=f"narrative:{b['brand_id']}:{cid}:{end}", title=f"{cname} {end}",
                           text=text, doc_type="narrative", brand_id=b["brand_id"], doc_date=end, source="nightly")
            n += 1
    return n


def reconcile_job(db: Database) -> dict[str, Any]:
    """Runs in the executor's process role (needs read credentials, never a model)."""
    from adintel.executor.reconciliation import reconcile

    return reconcile(db)
