"""The supervisor graph.

    START ─(resume?)─► Orchestrator
      └─► Ingestion ─► Data Quality ─(trustworthy/degraded)─► Orchestrator ◄──► Anomaly | Analyst | Optimizer | Report
                         └─(untrustworthy / failed)─► Finalize            └─(complete)─► Guardrail ─► Finalize ─► END

Specialists never call each other; each one returns to the Orchestrator.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from langgraph.graph import END, START, StateGraph

from adintel.agents.base import AgentContext
from adintel.domain.enums import AgentName, DQVerdict, NextAction
from adintel.domain.state import RunState
from adintel.graph.finalize import finalize
from adintel.graph.nodes import TERMINAL_FOR_ROUTING, make_node
from adintel.storage.base import Database

SPECIALISTS = (AgentName.ANOMALY, AgentName.ANALYST, AgentName.OPTIMIZER, AgentName.REPORT)


def _entry(state: RunState) -> str:
    return "orchestrator" if state.dq is not None else "ingestion"


def _after_ingestion(state: RunState) -> str:
    return "finalize" if state.status in TERMINAL_FOR_ROUTING else "data_quality"


def _after_dq(state: RunState) -> str:
    if state.status in TERMINAL_FOR_ROUTING or state.dq is None or state.dq.verdict == DQVerdict.UNTRUSTWORTHY:
        return "finalize"
    return "orchestrator"


def _route(state: RunState) -> str:
    if state.status in TERMINAL_FOR_ROUTING:
        return "finalize"
    action = state.next_action or str(NextAction.REPORT)
    return action if action in {str(a) for a in NextAction} else "report"


def build_graph(db: Database, ctx_factory: Callable[[], AgentContext]) -> Any:
    g: StateGraph[RunState] = StateGraph(RunState)
    for agent in (AgentName.INGESTION, AgentName.DATA_QUALITY, AgentName.ORCHESTRATOR, *SPECIALISTS,
                  AgentName.GUARDRAIL):
        g.add_node(str(agent), make_node(agent, ctx_factory))
    g.add_node("finalize", lambda s: finalize(db, s))
    g.add_conditional_edges(START, _entry, {"ingestion": "ingestion", "orchestrator": "orchestrator"})
    g.add_conditional_edges("ingestion", _after_ingestion, {"data_quality": "data_quality", "finalize": "finalize"})
    g.add_conditional_edges("data_quality", _after_dq, {"orchestrator": "orchestrator", "finalize": "finalize"})
    g.add_conditional_edges("orchestrator", _route, {**{str(a): str(a) for a in SPECIALISTS},
                                                     "guardrail": "guardrail", "finalize": "finalize"})
    for a in SPECIALISTS:
        g.add_edge(str(a), "orchestrator")
    g.add_edge("guardrail", "finalize")
    g.add_edge("finalize", END)
    return g.compile()
