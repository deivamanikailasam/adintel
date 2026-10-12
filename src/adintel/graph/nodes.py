"""Harness node wrapper: everything that happens around every agent dispatch.

Before: kill switches (global/tenant/brand/agent), budget guard, step limit.
During: the agent runs in a worker thread with its own timeout; on timeout the cancellation token is
set and the agent's timeout policy applies (skip / fail / template / fail closed).
After: frozen identity enforced, usage merged, visits counted, a trace event recorded.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from typing import Any

from adintel.agents import (analyst, anomaly, data_quality, guardrail, ingestion, optimizer, orchestrator,
                            report)
from adintel.agents.base import AgentContext
from adintel.core.clock import utcnow
from adintel.core.errors import AdIntelError, BudgetExceeded, TenantIsolationViolation
from adintel.domain.enums import AgentName, DegradationCode, RunStatus
from adintel.domain.models import GuardrailFinding, GuardrailVerdict, TraceEvent
from adintel.domain.state import FROZEN_FIELDS, RunState
from adintel.harness.degradation import degrade
from adintel.harness.killswitch import KillSwitches
from adintel.harness.timeouts import AGENT_SECONDS
from adintel.observability import metrics
from adintel.observability.alerts import Severity, raise_alert
from adintel.observability.tracing import span

log = logging.getLogger(__name__)

AgentFn = Callable[[RunState, AgentContext], dict[str, Any]]

AGENTS: dict[AgentName, AgentFn] = {
    AgentName.INGESTION: ingestion.run, AgentName.DATA_QUALITY: data_quality.run,
    AgentName.ORCHESTRATOR: orchestrator.run, AgentName.ANOMALY: anomaly.run, AgentName.ANALYST: analyst.run,
    AgentName.OPTIMIZER: optimizer.run, AgentName.REPORT: report.run, AgentName.GUARDRAIL: guardrail.run,
}

TERMINAL_FOR_ROUTING = (RunStatus.FAILED, RunStatus.ABORTED_DATA_QUALITY, RunStatus.KILLED)
BUDGET_EXEMPT = (AgentName.REPORT, AgentName.GUARDRAIL, AgentName.ORCHESTRATOR)


def timeout_policy(agent: AgentName, state: RunState, ctx: AgentContext, reason: str) -> dict[str, Any]:
    """What the user gets when an agent times out or fails unexpectedly (degradation matrix)."""
    if agent == AgentName.INGESTION:
        return {"status": RunStatus.FAILED, "abort_reason": f"ingestion failed: {reason}",
                "degradations": [degrade(DegradationCode.ALL_PLATFORMS_UNAVAILABLE, agent, reason)]}
    if agent == AgentName.DATA_QUALITY:
        return {"status": RunStatus.FAILED, "abort_reason": f"no data-quality verdict ({reason}); no analysis"}
    if agent == AgentName.ANOMALY:
        return {"anomaly_pass_done": True, "degradations": [degrade(DegradationCode.ANOMALY_SKIPPED, agent, reason)]}
    if agent == AgentName.ANALYST:
        return {"analyst_done": True, "degradations": [degrade(DegradationCode.ANALYST_SKIPPED, agent, reason)]}
    if agent == AgentName.OPTIMIZER:
        return {"optimizer_done": True,
                "degradations": [degrade(DegradationCode.OPTIMIZER_SKIPPED, agent, reason)]}
    if agent == AgentName.REPORT:
        return report.run(state.model_copy(update={"budget_exhausted": True}), ctx)  # deterministic template
    if agent == AgentName.GUARDRAIL:
        return {"guardrail": GuardrailVerdict(passed=False, classifier_used=False, findings=[GuardrailFinding(
            check="guardrail_timeout", severity="block", detail=f"fail closed: {reason}")])}
    if agent == AgentName.ORCHESTRATOR:
        return {"next_action": "report", "degradations": [degrade(DegradationCode.ORCHESTRATOR_RULE_FALLBACK,
                                                                  agent, reason)]}
    raise ValueError(agent)


def make_node(agent: AgentName, ctx_factory: Callable[[], AgentContext]) -> Callable[[RunState], dict[str, Any]]:
    fn = AGENTS[agent]

    def node(state: RunState) -> dict[str, Any]:
        ctx = ctx_factory()
        meter = ctx.meter
        started = utcnow()
        t0 = time.perf_counter()
        before = meter.usage.model_copy()
        status = "ok"
        update: dict[str, Any]
        # ---- before: kill switches, budget, step limit -----------------------------------------------
        scope = KillSwitches(ctx._db).engaged(tenant_id=state.tenant_id, brand_id=state.brand_id, agent=str(agent))
        if scope:
            return {"status": RunStatus.KILLED, "abort_reason": f"kill switch {scope}"}
        meter.step()
        extra: dict[str, Any] = {}
        reason = meter.exhausted_reason()
        if reason and agent not in BUDGET_EXEMPT and not state.budget_exhausted:
            metrics.BUDGET_EXHAUSTED.labels(limit=reason).inc()
            code = DegradationCode.STEP_LIMIT if reason == "steps" else DegradationCode.BUDGET_EXHAUSTED
            if code == DegradationCode.STEP_LIMIT:
                raise_alert(Severity.P2, "Run hit its step limit (possible orchestration loop)",
                            tenant_id=state.tenant_id, brand_id=state.brand_id, details={"run_id": state.run_id})
            return {"budget_exhausted": True, "degradations": [degrade(code, agent, reason)],
                    "usage": meter.usage.model_copy(), "next_action": None}
        if reason and agent in BUDGET_EXEMPT and not state.budget_exhausted:
            extra = {"budget_exhausted": True,
                     "degradations": [degrade(DegradationCode.BUDGET_EXHAUSTED, agent, reason)]}
            state = state.model_copy(update={"budget_exhausted": True})
        if agent == AgentName.GUARDRAIL:
            meter.reserve_mode = True
        # ---- during: run with a timeout ------------------------------------------------------------
        pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix=f"agent-{agent}")
        with span(f"agent.{agent}", agent=str(agent), step=meter.usage.steps):
            fut = pool.submit(fn, state, ctx)
            try:
                update = fut.result(timeout=AGENT_SECONDS[agent])
            except FutureTimeout:
                ctx.cancel.set()
                status = "timeout"
                log.error("agent_timeout", extra={"agent": str(agent), "timeout_s": AGENT_SECONDS[agent]})
                update = timeout_policy(agent, state, ctx, f"timeout after {AGENT_SECONDS[agent]:.0f}s")
            except BudgetExceeded as exc:
                status = "degraded"
                metrics.BUDGET_EXHAUSTED.labels(limit=str(exc)).inc()
                update = timeout_policy(agent, state.model_copy(update={"budget_exhausted": True}), ctx,
                                        f"budget exhausted ({exc})")
                update = {**update, "budget_exhausted": True, "degradations": [
                    degrade(DegradationCode.BUDGET_EXHAUSTED, agent, str(exc)), *update.get("degradations", [])]}
            except TenantIsolationViolation as exc:
                status = "failed"
                update = {"status": RunStatus.FAILED, "abort_reason": f"tenant isolation violation: {exc}"}
            except AdIntelError as exc:
                status = "failed"
                log.exception("agent_failed", extra={"agent": str(agent)})
                update = timeout_policy(agent, state, ctx, f"{type(exc).__name__}: {str(exc)[:160]}")
            except Exception as exc:  # noqa: BLE001 - an unexpected bug degrades, it does not crash the run
                status = "failed"
                log.exception("agent_crashed", extra={"agent": str(agent)})
                update = timeout_policy(agent, state, ctx, f"{type(exc).__name__}: {str(exc)[:160]}")
            finally:
                pool.shutdown(wait=False)
                meter.reserve_mode = False
        # ---- after: identity, usage, trace ---------------------------------------------------------
        bad = FROZEN_FIELDS & set(update)
        if bad:
            raise TenantIsolationViolation(f"agent {agent} tried to update frozen fields {sorted(bad)}")
        if extra:
            update = {**extra, **update, "degradations": [*extra["degradations"], *update.get("degradations", [])]}
        if any(d.code for d in update.get("degradations", [])) and status == "ok":
            status = "degraded"
        visits = dict(state.visits)
        visits[str(agent)] = visits.get(str(agent), 0) + 1
        after = meter.usage
        calls = [c["call_id"] for c in ctx.llm.call_log]
        trace = TraceEvent(step=after.steps, agent=agent, status=status,
                           summary=_summarise(agent, update), started_at=started,
                           duration_ms=round((time.perf_counter() - t0) * 1000, 1),
                           tokens_in=after.tokens_in - before.tokens_in, tokens_out=after.tokens_out - before.tokens_out,
                           cost_usd=round(after.cost_usd - before.cost_usd, 6), llm_call_ids=calls)
        metrics.AGENT_CALLS.labels(agent=str(agent), status=status).inc()
        return {**update, "usage": after.model_copy(), "visits": visits, "traces": [*update.get("traces", []), trace]}

    node.__name__ = f"node_{agent}"
    return node


def _summarise(agent: AgentName, u: dict[str, Any]) -> str:
    if agent == AgentName.INGESTION:
        return f"{sum(1 for f in u.get('fetches', []) if f.ok)}/{len(u.get('fetches', []))} platforms fetched"
    if agent == AgentName.DATA_QUALITY and u.get("dq"):
        return f"verdict {u['dq'].verdict}"
    if agent == AgentName.ORCHESTRATOR and u.get("decisions"):
        d = u["decisions"][-1]
        return f"next: {d.next_action} ({d.decided_by})"
    if agent == AgentName.ANOMALY:
        return f"{len([a for a in u.get('anomalies', []) if a.severity.rank >= 1])} material anomalies"
    if agent == AgentName.ANALYST and u.get("root_causes"):
        rc = u["root_causes"][-1]
        return f"root cause (confidence {rc.confidence:.2f})"
    if agent == AgentName.OPTIMIZER:
        return f"{len(u.get('recommendations', []))} recommendation(s)"
    if agent == AgentName.REPORT and u.get("report"):
        return f"report via {u['report'].model_tier}"
    if agent == AgentName.GUARDRAIL and u.get("guardrail"):
        return "passed" if u["guardrail"].passed else "blocked"
    return "done"
