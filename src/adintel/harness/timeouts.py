"""Nested timeouts. Each inner timeout is strictly shorter than the one around it:

    run 900 s → per-step dispatch 300 s → agent 45–240 s → LLM call 30–90 s → HTTP read (call − 5 s) → TCP 5 s

Otherwise the outer layer gives up while the inner one is still working — and still being billed.
``tests/unit/test_harness.py::test_timeouts_strictly_nest`` asserts the ordering against the model
registry, so a config change can never invert it.
"""

from __future__ import annotations

from adintel.domain.enums import AgentName

RUN_SECONDS = 900.0
STEP_DISPATCH_SECONDS = 300.0
TCP_CONNECT_SECONDS = 5.0

AGENT_SECONDS: dict[AgentName, float] = {
    AgentName.INGESTION: 120.0,  # each platform fetch has its own 25 s timeout inside
    AgentName.DATA_QUALITY: 60.0,
    AgentName.ORCHESTRATOR: 120.0,
    AgentName.ANOMALY: 90.0,
    AgentName.ANALYST: 240.0,
    AgentName.OPTIMIZER: 180.0,
    AgentName.REPORT: 200.0,  # report tier (60 s) + frontier fallback (90 s) must fit
    AgentName.GUARDRAIL: 60.0,
    AgentName.FINALIZE: 60.0,
}

PLATFORM_FETCH_SECONDS = 25.0
SANDBOX_CPU_SECONDS = 10
SANDBOX_WALL_SECONDS = 20.0

# Which model tier(s) each agent may call in sequence (primary + fallback) — used by the nesting test.
AGENT_TIERS: dict[AgentName, tuple[str, ...]] = {
    AgentName.INGESTION: ("small",),
    AgentName.DATA_QUALITY: ("small",),
    AgentName.ORCHESTRATOR: ("frontier",),
    AgentName.ANALYST: ("frontier",),
    AgentName.OPTIMIZER: ("frontier",),
    AgentName.REPORT: ("report", "frontier"),
    AgentName.GUARDRAIL: ("safety",),
}
