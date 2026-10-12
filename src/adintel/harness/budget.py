"""Budget guard: a hard gate in code, not a request to the model.

Checked before every dispatch (by the engine) and before every model call (by the gateway). Every
attempt is charged — failures, timeouts and repair turns included — so a repair loop cannot silently
double spend and the dashboards match the invoice.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass

from adintel.core.clock import utcnow
from adintel.core.errors import BudgetExceeded
from adintel.domain.state import BudgetLimits, BudgetUsage


@dataclass
class Charge:
    tokens_in: int
    tokens_out: int
    cost_usd: float


class UsageMeter:
    """Live usage for one run, shared by the engine and every model call inside a node."""

    def __init__(self, limits: BudgetLimits, usage: BudgetUsage) -> None:
        self.limits = limits
        self.usage = usage.model_copy()
        self._lock = threading.Lock()

    def exhausted_reason(self, *, extra_tokens: int = 0, extra_cost: float = 0.0, extra_steps: int = 0) -> str | None:
        u, lim = self.usage, self.limits
        if u.steps + extra_steps > lim.max_steps:
            return "steps"
        if u.tokens + extra_tokens > lim.max_tokens:
            return "tokens"
        if u.cost_usd + extra_cost > lim.max_cost_usd:
            return "cost"
        if (utcnow() - u.started_at).total_seconds() > lim.max_wall_seconds:
            return "wall_clock"
        return None

    reserve_mode = False  # the guardrail always runs: it draws on a reserve, never blocked by the budget

    def precheck(self, *, tokens: int = 0, cost: float = 0.0) -> None:
        if self.reserve_mode:
            return
        with self._lock:
            reason = self.exhausted_reason(extra_tokens=tokens, extra_cost=cost)
        if reason:
            raise BudgetExceeded(reason)

    def charge(self, tokens_in: int, tokens_out: int, cost_usd: float) -> None:
        with self._lock:
            self.usage.tokens_in += tokens_in
            self.usage.tokens_out += tokens_out
            self.usage.cost_usd = round(self.usage.cost_usd + cost_usd, 6)

    def step(self) -> None:
        with self._lock:
            self.usage.steps += 1

    def remaining_fraction(self) -> float:
        u, lim = self.usage, self.limits
        return max(
            0.0,
            min(
                1 - u.steps / lim.max_steps,
                1 - u.tokens / lim.max_tokens,
                1 - u.cost_usd / lim.max_cost_usd,
                1 - (utcnow() - u.started_at).total_seconds() / lim.max_wall_seconds,
            ),
        )


class UnlimitedMeter(UsageMeter):
    """For chat and evals outside a run: still records usage, never blocks."""

    def __init__(self) -> None:
        super().__init__(
            BudgetLimits(max_steps=10**9, max_tokens=10**12, max_cost_usd=10**9, max_wall_seconds=10**12), BudgetUsage()
        )
