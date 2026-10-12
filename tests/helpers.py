"""Test helpers: contexts and states for agents without running the whole graph."""

from __future__ import annotations

from datetime import date

from adintel.agents.base import AgentContext
from adintel.connectors.scenarios import world_for
from adintel.domain.state import BudgetLimits, BudgetUsage, RunState
from adintel.harness.budget import UsageMeter
from adintel.llm.gateway import CallContext, LLMGateway

PERIOD_START = date(2026, 10, 5)
PERIOD_END = date(2026, 10, 11)


def make_state(brand_id: str, tenant_id: str = "brightwave", run_id: str = "run_test") -> RunState:
    return RunState(run_id=run_id, tenant_id=tenant_id, brand_id=brand_id, brand_name=brand_id,
                    period_start=PERIOD_START, period_end=PERIOD_END,
                    platforms=[str(p) for p in world_for(brand_id).entities])


def make_ctx(db, state: RunState) -> AgentContext:
    meter = UsageMeter(BudgetLimits(), BudgetUsage())
    gw = LLMGateway(db, CallContext(tenant_id=state.tenant_id, run_id=state.run_id, brand_id=state.brand_id),
                    meter=meter)
    return AgentContext(db, state.tenant_id, state.brand_id, state.run_id, gw, meter)


def apply(state: RunState, update: dict) -> RunState:
    data = state.model_dump()
    for k, v in update.items():
        if k in ("degradations", "traces", "decisions"):
            data[k] = data[k] + [x.model_dump() if hasattr(x, "model_dump") else x for x in v]
        else:
            data[k] = v.model_dump() if hasattr(v, "model_dump") else (
                [x.model_dump() if hasattr(x, "model_dump") else x for x in v] if isinstance(v, list) else v)
    return RunState.model_validate(data)


def ingest(db, brand_id: str, tenant_id: str = "brightwave") -> RunState:
    from adintel.agents import ingestion

    s = make_state(brand_id, tenant_id)
    return apply(s, ingestion.run(s, make_ctx(db, s)))
