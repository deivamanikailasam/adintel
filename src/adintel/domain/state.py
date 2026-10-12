"""RunState — the single typed object that flows through the LangGraph graph.

Rules (enforced by the harness, see ``graph/engine.py``):

* ``tenant_id`` and ``brand_id`` are identity and are **frozen**: no node may update them.
* Large data is held **by reference** (``metrics_ref``); state carries only compact summaries.
* List fields that several agents may append to use ``operator.add`` reducers.
* Agents are stateless functions of this object and return partial updates.
"""

from __future__ import annotations

import operator
from datetime import date, datetime
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field

from adintel.core.clock import utcnow
from adintel.domain.enums import AgentName, RunStatus
from adintel.domain.models import (
    Anomaly,
    Degradation,
    DQResult,
    GuardrailVerdict,
    OrchestratorDecision,
    PlatformFetch,
    Recommendation,
    Report,
    RootCause,
    TraceEvent,
)

FROZEN_FIELDS = frozenset({"run_id", "tenant_id", "brand_id"})


class BudgetLimits(BaseModel):
    model_config = ConfigDict(extra="forbid")
    max_steps: int = 25
    max_tokens: int = 400_000
    max_cost_usd: float = 2.00
    max_wall_seconds: float = 900.0


class BudgetUsage(BaseModel):
    model_config = ConfigDict(extra="forbid")
    steps: int = 0
    tokens_in: int = 0
    tokens_out: int = 0
    cost_usd: float = 0.0
    started_at: datetime = Field(default_factory=utcnow)

    @property
    def tokens(self) -> int:
        return self.tokens_in + self.tokens_out


class RunState(BaseModel):
    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=False)

    # ---- identity (frozen) ----
    run_id: str
    tenant_id: str
    brand_id: str

    # ---- request ----
    brand_name: str = ""
    period_start: date
    period_end: date
    goal: str = "weekly_report"
    trigger: str = "schedule"  # schedule | api | chat | replay
    requested_by: str | None = None
    platforms: list[str] = Field(default_factory=list)

    # ---- control ----
    status: RunStatus = RunStatus.RUNNING
    limits: BudgetLimits = Field(default_factory=BudgetLimits)
    usage: BudgetUsage = Field(default_factory=BudgetUsage)
    next_action: str | None = None
    visits: dict[str, int] = Field(default_factory=dict)
    budget_exhausted: bool = False
    abort_reason: str | None = None
    frontier_available: bool = True

    # ---- data (by reference) ----
    metrics_ref: dict[str, Any] | None = None
    fetches: list[PlatformFetch] = Field(default_factory=list)
    metrics_summary: dict[str, Any] = Field(default_factory=dict)

    # ---- agent outputs ----
    dq: DQResult | None = None
    anomaly_pass_done: bool = False
    anomalies: list[Anomaly] = Field(default_factory=list)
    root_causes: list[RootCause] = Field(default_factory=list)
    analyst_done: bool = False
    optimizer_done: bool = False
    recommendations: list[Recommendation] = Field(default_factory=list)
    report: Report | None = None
    guardrail: GuardrailVerdict | None = None
    finalized: bool = False

    # ---- append-only (reducers) ----
    decisions: Annotated[list[OrchestratorDecision], operator.add] = Field(default_factory=list)
    degradations: Annotated[list[Degradation], operator.add] = Field(default_factory=list)
    traces: Annotated[list[TraceEvent], operator.add] = Field(default_factory=list)

    # ---- helpers ----
    def has_degradation(self, code: str) -> bool:
        return any(d.code == code for d in self.degradations)

    def visit_count(self, agent: AgentName | str) -> int:
        return self.visits.get(str(agent), 0)

    def material_anomalies(self) -> list[Anomaly]:
        """Anomalies above low severity, most severe first (ties broken by id for determinism)."""
        items = [a for a in self.anomalies if a.severity.rank >= 1]
        return sorted(items, key=lambda a: (-a.severity.rank, -a.spend_at_risk_weekly, a.anomaly_id))

    def remaining_budget_fraction(self) -> float:
        lim, use = self.limits, self.usage
        fractions = [
            1 - use.steps / lim.max_steps,
            1 - use.tokens / lim.max_tokens,
            1 - use.cost_usd / lim.max_cost_usd,
            1 - (utcnow() - use.started_at).total_seconds() / lim.max_wall_seconds,
        ]
        return max(0.0, min(fractions))
