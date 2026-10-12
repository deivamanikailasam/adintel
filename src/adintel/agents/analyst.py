"""Analyst agent: explains WHY a metric changed (frontier model + sandboxed pandas).

Pre-computed, deterministic facts come first — in particular a **mix vs rate decomposition** that says
how much of a CPA change is explained by budget moving between ad sets versus ad sets getting worse.
The model then tests hypotheses, may request up to 3 pandas queries per round (2 rounds max) that run in
the sandbox, and returns a calibrated root cause. It checks for cancellation between tool steps.
"""

from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Any

import pandas as pd
from pydantic import BaseModel, Field

from adintel.agents.base import AgentContext
from adintel.analytics.frames import load_frame
from adintel.core.errors import LLMUnavailable, LLMValidationError, SandboxTimeout
from adintel.domain.enums import AgentName, DegradationCode, Metric
from adintel.domain.models import Anomaly, Hypothesis, RootCause
from adintel.domain.state import RunState
from adintel.harness.degradation import degrade
from adintel.observability.alerts import Severity, raise_alert
from adintel.observability.metrics import INJECTION_FLAGS
from adintel.rag.retriever import RetrievalUnavailable
from adintel.sandbox import get_sandbox

log = logging.getLogger(__name__)
MAX_ROUNDS = 2
MAX_QUERIES = 3
BASELINE_DAYS = 28


class AnalystOutput(BaseModel):
    hypotheses: list[Hypothesis] = Field(default_factory=list)
    queries: list[str] = Field(default_factory=list, max_length=MAX_QUERIES)
    root_cause_summary: str = ""
    confidence: float = Field(0.0, ge=0.0, le=1.0)
    injection_suspected: bool = False
    injection_detail: str = ""


def _window(df: pd.DataFrame, start: date, end: date) -> pd.DataFrame:
    return df[(df["date"] >= start) & (df["date"] <= end)]


def entity_facts(df: pd.DataFrame, anomaly: Anomaly, end: date) -> dict[str, Any]:
    """Per-entity before/after economics and a mix-vs-rate decomposition of the CPA change."""
    camp = df[(df["campaign_id"] == anomaly.campaign_id) & (df["platform"] == str(anomaly.platform))]
    k = anomaly.days
    after = _window(camp, end - timedelta(days=k - 1), end)
    before = _window(camp, end - timedelta(days=k + BASELINE_DAYS - 1), end - timedelta(days=k))

    def econ(w: pd.DataFrame) -> dict[str, dict[str, Any]]:
        out: dict[str, dict[str, Any]] = {}
        total = float(w["spend"].sum()) or 1.0
        for eid, g in w.groupby("entity_id"):
            s, c, cl, im = (float(g["spend"].sum()), float(g["conversions"].sum()), float(g["clicks"].sum()),
                            float(g["impressions"].sum()))
            days = max(1, g["date"].nunique())
            out[str(eid)] = {"entity_name": str(g["entity_name"].iloc[0]), "spend_per_day": round(s / days, 2),
                             "spend_share_pct": round(100 * s / total, 1),
                             "cpa": round(s / c, 2) if c else None, "ctr_pct": round(100 * cl / im, 3) if im else None,
                             "cpc": round(s / cl, 2) if cl else None, "cvr_pct": round(100 * c / cl, 2) if cl else None,
                             "daily_budget": float(g["daily_budget"].dropna().iloc[-1])
                             if g["daily_budget"].notna().any() else None}
        return out

    b, a = econ(before), econ(after)
    cpa_b = float(before["spend"].sum()) / max(float(before["conversions"].sum()), 1e-9)
    cpa_a = float(after["spend"].sum()) / max(float(after["conversions"].sum()), 1e-9)
    # counterfactual: today's per-entity CPAs with yesterday's spend shares
    cf_conv_per_dollar = 0.0
    for eid, e in b.items():
        cpa_now = (a.get(eid) or {}).get("cpa") or e["cpa"]
        if cpa_now:
            cf_conv_per_dollar += (e["spend_share_pct"] / 100) / cpa_now
    cpa_cf = 1 / cf_conv_per_dollar if cf_conv_per_dollar else cpa_a
    total_change = cpa_a - cpa_b
    rate_effect = cpa_cf - cpa_b
    mix_effect = total_change - rate_effect
    return {"campaign_id": anomaly.campaign_id, "anomaly_days": k, "baseline_days": BASELINE_DAYS,
            "campaign_cpa_before": round(cpa_b, 2), "campaign_cpa_after": round(cpa_a, 2),
            "entities_before": b, "entities_after": a,
            "decomposition": {"total_cpa_change": round(total_change, 2), "mix_effect": round(mix_effect, 2),
                              "rate_effect": round(rate_effect, 2),
                              "mix_share_pct": round(100 * mix_effect / total_change, 1) if total_change else None}}


def _target(state: RunState) -> Anomaly | None:
    explained = {rc.anomaly_id for rc in state.root_causes}
    for a in state.material_anomalies():
        if a.anomaly_id not in explained and a.metric in (Metric.CPA, Metric.ROAS, Metric.CONVERSIONS, Metric.SPEND):
            return a
    return None


def run(state: RunState, ctx: AgentContext) -> dict[str, Any]:
    target = _target(state)
    update: dict[str, Any] = {"analyst_done": True}
    if target is None:
        return update
    ref = state.metrics_ref or {}
    df = load_frame(ctx.repo("metrics_daily"), ctx.brand_id, state.period_end - timedelta(days=60), state.period_end,
                    ref.get("platforms"))
    facts = entity_facts(df, target, state.period_end)
    brand = ctx.repo("brands").find_one({"brand_id": ctx.brand_id}) or {}
    evidence: list[dict[str, Any]] = []
    chunk_ids: list[str] = []
    try:
        res = ctx.retriever().search(
            f"{target.metric} {target.direction} {target.platform} {target.entity_name} budget spend shift diagnosis",
            brand_id=ctx.brand_id, vertical=(brand.get("profile") or {}).get("vertical"),
            doc_types=["incident", "playbook", "report"], k=5)
        evidence = [c.as_evidence() for c in res.chunks]
        chunk_ids = res.ids
    except RetrievalUnavailable:
        log.warning("analyst_no_retrieval")
    camp_rows = df[df["campaign_id"] == target.campaign_id]
    rows = camp_rows.assign(date=camp_rows["date"].astype(str)).to_dict(orient="records")
    query_results: list[dict[str, Any]] = []
    out: AnalystOutput | None = None
    call_ids: list[str] = []
    for round_no in range(1, MAX_ROUNDS + 1):
        ctx.check_cancelled()
        context = {"anomaly": target.model_dump(mode="json"), "facts": facts, "round": round_no,
                   "max_rounds": MAX_ROUNDS, "dataframe_columns": list(camp_rows.columns)}
        try:
            r = ctx.llm.structured(agent="analyst", prompt_id="analyst", schema=AnalystOutput, context=context,
                                   untrusted={"retrieved_evidence": evidence, "query_results": query_results,
                                              "entity_names": sorted(set(camp_rows["entity_name"]))},
                                   retrieved_doc_ids=chunk_ids, allow_fallback=False)
        except LLMUnavailable as exc:
            log.warning("analyst_frontier_unavailable", extra={"reason": str(exc)[:200]})
            update["frontier_available"] = False
            update["degradations"] = [degrade(DegradationCode.FRONTIER_UNAVAILABLE, AgentName.ANALYST),
                                      degrade(DegradationCode.ANALYST_SKIPPED, AgentName.ANALYST, "frontier down")]
            return update
        except LLMValidationError as exc:
            update["degradations"] = [degrade(DegradationCode.ANALYST_SKIPPED, AgentName.ANALYST, str(exc)[:120])]
            return update
        out = r.value
        call_ids += r.call_ids
        if out.injection_suspected:
            break
        if not out.queries or round_no == MAX_ROUNDS:
            break
        sandbox = get_sandbox()
        for q in out.queries[:MAX_QUERIES]:
            ctx.check_cancelled()  # timeouts must really stop work
            try:
                query_results.append(sandbox.run(q, rows).as_context())
            except SandboxTimeout as exc:
                query_results.append({"query": q, "ok": False, "error": str(exc)})
    assert out is not None
    if out.injection_suspected:
        INJECTION_FLAGS.labels(agent="analyst").inc()
        raise_alert(Severity.P1, "Prompt injection suspected in ad-platform data", tenant_id=ctx.tenant_id,
                    brand_id=ctx.brand_id, details={"run_id": ctx.run_id, "detail": out.injection_detail[:300]},
                    audience="security")
        update["degradations"] = [degrade(DegradationCode.INJECTION_SUSPECTED, AgentName.ANALYST,
                                          out.injection_detail[:200])]
    update["root_causes"] = [*state.root_causes, RootCause(
        anomaly_id=target.anomaly_id, summary=out.root_cause_summary or "inconclusive", confidence=out.confidence,
        hypotheses=out.hypotheses, evidence_chunk_ids=chunk_ids, queries_run=[q["query"] for q in query_results],
        injection_suspected=out.injection_suspected)]
    update["metrics_summary"] = {**state.metrics_summary, "analyst_facts": facts}
    return update
