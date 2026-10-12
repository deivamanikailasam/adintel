"""Finalize: decide the final status, persist, audit, notify, index the report, emit metrics.

Output that the guardrail blocked, or that came from a run where injection was suspected, is held and
its recommendations are quarantined — nothing reaches a client or the approval queue.
"""

from __future__ import annotations

import logging
from typing import Any

from adintel.audit import AuditLog
from adintel.config import get_settings
from adintel.core.clock import utcnow
from adintel.domain.enums import AuditAction, DegradationCode, RecommendationStatus, RunStatus, Severity
from adintel.domain.state import RunState
from adintel.harness.degradation import MATRIX
from adintel.observability import metrics
from adintel.storage.base import Database
from adintel.storage.tenant_repo import TenantScopedRepo

log = logging.getLogger(__name__)


def final_status(state: RunState) -> RunStatus:
    if state.status in (RunStatus.FAILED, RunStatus.ABORTED_DATA_QUALITY, RunStatus.KILLED):
        return state.status
    if state.has_degradation(DegradationCode.INJECTION_SUSPECTED):
        return RunStatus.HELD
    if state.guardrail is not None and not state.guardrail.passed:
        return RunStatus.HELD
    if state.report is None:
        return RunStatus.FAILED
    if state.recommendations:
        return RunStatus.AWAITING_APPROVAL
    if any(MATRIX[d.code].status == RunStatus.DEGRADED for d in state.degradations):
        return RunStatus.DEGRADED
    return RunStatus.COMPLETED


def path_of(state: RunState) -> str:
    if state.status == RunStatus.ABORTED_DATA_QUALITY:
        return "abort"
    visited = set(state.visits)
    return "investigation" if "analyst" in visited else "clean"


def finalize(db: Database, state: RunState) -> dict[str, Any]:
    t = state.tenant_id
    status = final_status(state)
    audit = AuditLog(db, t, system_version=get_settings().system_version)
    now = utcnow().isoformat()
    held = status == RunStatus.HELD
    health = "degraded" if any(MATRIX[d.code].status == RunStatus.DEGRADED for d in state.degradations) else "ok"

    anomalies = TenantScopedRepo(db, "anomalies", t)
    for a in state.anomalies:
        anomalies.update_one({"anomaly_id": a.anomaly_id}, {"$set": {**a.model_dump(mode="json"), "brand_id":
                             state.brand_id, "run_id": state.run_id, "updated_at": now},
                             "$setOnInsert": {"status": "open", "created_at": now}}, upsert=True)

    recs = TenantScopedRepo(db, "recommendations", t)
    for r in state.recommendations:
        doc = r.model_dump(mode="json")
        if held:
            doc["status"] = str(RecommendationStatus.QUARANTINED)
        recs.update_one({"recommendation_id": r.recommendation_id}, {"$set": doc}, upsert=True)
        audit.append(AuditAction.RECOMMENDATION_QUARANTINED if held else AuditAction.RECOMMENDATION_CREATED,
                     actor_type="agent", actor_id=f"agent:optimizer@{_model('optimizer')}",
                     subject_type="recommendation", subject_id=r.recommendation_id, run_id=state.run_id,
                     details={"action": str(r.action_type), "exposure_usd": r.daily_exposure_usd, "risk": str(r.risk),
                              "citations": [c.chunk_id for c in r.citations]})

    report_id = None
    if state.report is not None:
        report_id = state.report.report_id
        TenantScopedRepo(db, "reports", t).update_one({"report_id": report_id}, {"$set": {
            **state.report.model_dump(mode="json"), "brand_id": state.brand_id, "run_id": state.run_id,
            "status": "held" if held else "released", "system_version": get_settings().system_version,
            "footer": (f"Prepared by AdIntel {get_settings().system_version}. AI drafts and analyses; a named "
                       "account manager approves every recommendation."), "created_at": now}}, upsert=True)
        if not held:
            audit.append(AuditAction.REPORT_RELEASED, actor_type="agent", actor_id=f"agent:report@{_model('report')}",
                         subject_type="report", subject_id=report_id, run_id=state.run_id,
                         details={"tier": state.report.model_tier, "template": state.report.deterministic_template})
            _index_report(db, state)
    if state.guardrail is not None and not state.guardrail.passed:
        audit.append(AuditAction.GUARDRAIL_BLOCK, actor_type="agent", actor_id="agent:guardrail",
                     subject_type="run", subject_id=state.run_id, run_id=state.run_id,
                     details={"findings": [f.model_dump() for f in state.guardrail.findings if f.severity == "block"]})

    notes = TenantScopedRepo(db, "notifications", t)
    if status == RunStatus.ABORTED_DATA_QUALITY:
        notes.insert({"kind": "reporting_paused", "brand_id": state.brand_id, "run_id": state.run_id,
                      "audience": "account_manager", "title": "Reporting paused: data cannot be trusted",
                      "detail": state.abort_reason, "created_at": now})
    for a in state.material_anomalies():
        if a.severity.rank >= Severity.HIGH.rank:
            notes.insert({"kind": "anomaly_alert", "brand_id": state.brand_id, "run_id": state.run_id,
                          "audience": "account_manager", "title": f"{a.severity} {a.metric} anomaly: {a.entity_name}",
                          "detail": f"{a.deviation_pct:+.1f}% for {a.days} days", "created_at": now})
    if status == RunStatus.AWAITING_APPROVAL:
        notes.insert({"kind": "approval_needed", "brand_id": state.brand_id, "run_id": state.run_id,
                      "audience": "account_manager", "title": f"{len(state.recommendations)} recommendation(s) "
                      "awaiting approval", "created_at": now})

    TenantScopedRepo(db, "run_history", t).insert({
        "brand_id": state.brand_id, "run_id": state.run_id, "status": str(status), "path": path_of(state),
        "anomalies": [a.model_dump(mode="json") for a in state.material_anomalies()],
        "root_causes": [rc.model_dump(mode="json") for rc in state.root_causes],
        "recommendation_ids": [r.recommendation_id for r in state.recommendations], "created_at": now})

    duration = (utcnow() - state.usage.started_at).total_seconds()
    TenantScopedRepo(db, "runs", t).update_one({"run_id": state.run_id}, {"$set": {
        "status": str(status), "health": health, "finished_at": now, "path": path_of(state),
        "usage": state.usage.model_dump(mode="json"), "report_id": report_id, "abort_reason": state.abort_reason,
        "degradations": sorted({str(d.code) for d in state.degradations}), "duration_s": round(duration, 1),
        "recommendation_ids": [r.recommendation_id for r in state.recommendations]}})
    audit.append(AuditAction.RUN_FINISHED, actor_type="system", actor_id="system:engine", subject_type="run",
                 subject_id=state.run_id, run_id=state.run_id,
                 details={"status": str(status), "steps": state.usage.steps, "cost_usd": state.usage.cost_usd,
                          "decisions": [f"{d.next_action}:{d.decided_by}" for d in state.decisions]})
    metrics.RUNS.labels(status=str(status)).inc()
    metrics.RUN_STEPS.observe(state.usage.steps)
    metrics.RUN_DURATION.labels(path=path_of(state)).observe(duration)
    return {"status": status, "finalized": True}


def _model(agent: str) -> str:
    from adintel.llm.registry import get_registry

    reg = get_registry()
    return reg.tiers[reg.agents[agent].tier].model_id


def _index_report(db: Database, state: RunState) -> None:
    """Semantic memory: released reports become retrievable context for future runs."""
    try:
        from adintel.rag.indexer import index_document

        assert state.report is not None
        text = "\n\n".join(f"## {s.title}\n{s.body}" for s in state.report.sections)
        index_document(db, state.tenant_id, doc_id=f"report:{state.brand_id}:{state.period_end}",
                       title=state.report.title, text=text, doc_type="report", brand_id=state.brand_id,
                       doc_date=state.period_end, source=f"run:{state.run_id}")
    except Exception:  # noqa: BLE001 - indexing is best-effort
        log.exception("report_index_failed")
