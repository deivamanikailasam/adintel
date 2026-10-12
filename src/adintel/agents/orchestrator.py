"""Orchestrator (supervisor): decides what happens next and when the run is done.

Deterministic rules pre-empt the model on common paths (~70% of hops make no model call). The frontier
model is consulted only for a real judgement — "is this anomaly worth an investigation?" — and its answer
must be one of the actions allowed *right now*, otherwise a fallback rule decides. Loop protection is in
code: hard budgets, a no-repeat rule, and skipping the model when < 25% of the budget remains.
"""

from __future__ import annotations

import logging
from typing import Any, Literal

from pydantic import BaseModel, Field

from adintel.agents.base import AgentContext
from adintel.core.errors import AdIntelError
from adintel.domain.enums import AgentName, DegradationCode, DQVerdict, NextAction, Severity
from adintel.domain.models import OrchestratorDecision
from adintel.domain.state import RunState
from adintel.harness.degradation import degrade
from adintel.observability.metrics import ORCH_DECISIONS

log = logging.getLogger(__name__)

MAX_VISITS = {"anomaly": 1, "analyst": 1, "optimizer": 1, "report": 1, "guardrail": 1}
LOW_BUDGET_FRACTION = 0.25
IMMATERIAL_SPEND_AT_RISK = 250.0
MIN_RC_CONFIDENCE = 0.6


class OrchestratorOutput(BaseModel):
    next_action: Literal["analyst", "optimizer", "report", "guardrail"]
    reasoning: str = Field(max_length=600)


def rule_decision(state: RunState, remaining: float) -> tuple[NextAction, str, str] | None:
    """Return (action, rule_name, reasoning) or None if the model must decide."""
    if state.budget_exhausted:
        return (
            NextAction.GUARDRAIL if state.report else NextAction.REPORT,
            "budget_exhausted",
            "Budget exhausted: best-effort deterministic finalize.",
        )
    if state.report is not None:
        return NextAction.GUARDRAIL, "report_done", "A report exists; the run is complete."
    if not state.anomaly_pass_done:
        return NextAction.ANOMALY, "anomaly_first", "No anomaly pass yet."
    material = state.material_anomalies()
    if not material:
        return NextAction.REPORT, "no_material_anomalies", "Nothing above low severity: straight to report."
    if not state.frontier_available:
        return NextAction.REPORT, "frontier_down", "Frontier unavailable: skip Analyst and Optimizer."
    if remaining < LOW_BUDGET_FRACTION:
        return NextAction.REPORT, "low_budget", f"Only {remaining:.0%} of the budget remains."
    trustworthy = state.dq is not None and state.dq.verdict == DQVerdict.TRUSTWORTHY
    ready = [rc for rc in state.root_causes if rc.confidence >= MIN_RC_CONFIDENCE and not rc.injection_suspected]
    if ready and not state.optimizer_done and trustworthy:
        return NextAction.OPTIMIZER, "root_cause_ready", "Confident root cause on trustworthy data: propose a fix."
    if state.root_causes or state.analyst_done:
        return NextAction.REPORT, "analysis_complete", "Analysis is complete (or blocked): write the report."
    if state.visit_count("analyst") >= MAX_VISITS["analyst"]:
        return NextAction.REPORT, "no_repeat", "Analyst already ran once."
    top = material[0]
    if top.severity == Severity.MEDIUM and top.spend_at_risk_weekly < IMMATERIAL_SPEND_AT_RISK:
        return NextAction.REPORT, "immaterial", "Medium severity with little money at risk."
    return None


def fallback_rule(state: RunState) -> NextAction:
    top = state.material_anomalies()[0]
    return NextAction.ANALYST if top.severity.rank >= Severity.HIGH.rank else NextAction.REPORT


def run(state: RunState, ctx: AgentContext) -> dict[str, Any]:
    step = state.usage.steps
    remaining = ctx.meter.remaining_fraction()
    rule = rule_decision(state, remaining)
    update: dict[str, Any] = {}
    if rule:
        action, name, why = rule
        decided_by = f"rule:{name}"
    else:
        allowed = {NextAction.ANALYST, NextAction.REPORT}
        context = {
            "data_quality": str(state.dq.verdict) if state.dq else None,
            "anomalies": [
                {
                    "metric": str(a.metric),
                    "severity": str(a.severity),
                    "deviation_pct": a.deviation_pct,
                    "days": a.days,
                    "spend_at_risk_weekly": a.spend_at_risk_weekly,
                    "iforest_confirmed": a.iforest_confirmed,
                }
                for a in state.material_anomalies()[:5]
            ],
            "root_cause_exists": bool(state.root_causes),
            "recommendations": len(state.recommendations),
            "visits": state.visits,
            "remaining_budget_fraction": round(remaining, 2),
            "allowed_actions": sorted(str(a) for a in allowed),
        }
        try:
            r = ctx.llm.structured(
                agent="orchestrator",
                prompt_id="orchestrator",
                schema=OrchestratorOutput,
                context=context,
                allow_fallback=False,
            )
            action = NextAction(r.value.next_action)
            why = r.value.reasoning
            decided_by = "model"
            if action not in allowed:
                raise ValueError(f"model chose disallowed action {action}")
        except (AdIntelError, ValueError) as exc:
            action = fallback_rule(state)
            why = f"Model decision unavailable ({type(exc).__name__}); fallback rule."
            decided_by = "fallback_rule"
            update["degradations"] = [
                degrade(DegradationCode.ORCHESTRATOR_RULE_FALLBACK, AgentName.ORCHESTRATOR, str(exc)[:120])
            ]
    ORCH_DECISIONS.labels(decided_by=decided_by.split(":")[0], action=str(action)).inc()
    log.info("orchestrator_decision", extra={"next_action": str(action), "decided_by": decided_by})
    update["next_action"] = str(action)
    update["decisions"] = [OrchestratorDecision(step=step, next_action=action, decided_by=decided_by, reasoning=why)]
    return update
