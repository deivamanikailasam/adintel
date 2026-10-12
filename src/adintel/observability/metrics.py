"""Prometheus metrics, grouped by the four layers we watch: system, agent, model, quality."""

from __future__ import annotations

from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram, start_http_server

REGISTRY = CollectorRegistry(auto_describe=True)

# ---- system --------------------------------------------------------------------------------------
HTTP_REQUESTS = Counter("adintel_http_requests_total", "API requests", ["route", "method", "status"], registry=REGISTRY)
HTTP_LATENCY = Histogram(
    "adintel_http_request_seconds",
    "API latency",
    ["route"],
    registry=REGISTRY,
    buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10),
)
QUEUE_DEPTH = Gauge("adintel_queue_depth", "Messages waiting", ["queue"], registry=REGISTRY)
DLQ_DEPTH = Gauge("adintel_dlq_depth", "Messages in dead-letter queues", ["queue"], registry=REGISTRY)

# ---- agent ---------------------------------------------------------------------------------------
RUNS = Counter("adintel_runs_total", "Finished runs by status", ["status"], registry=REGISTRY)
RUN_STEPS = Histogram(
    "adintel_run_steps",
    "Steps per run (a growing tail = orchestration drift)",
    registry=REGISTRY,
    buckets=(1, 3, 5, 7, 9, 11, 13, 16, 20, 25),
)
RUN_DURATION = Histogram(
    "adintel_run_seconds",
    "Run wall-clock",
    ["path"],
    registry=REGISTRY,
    buckets=(5, 15, 30, 60, 90, 120, 180, 300, 600, 900),
)
AGENT_CALLS = Counter("adintel_agent_calls_total", "Agent invocations", ["agent", "status"], registry=REGISTRY)
ORCH_DECISIONS = Counter(
    "adintel_orchestrator_decisions_total", "Routing decisions", ["decided_by", "action"], registry=REGISTRY
)
DEGRADATIONS = Counter("adintel_degradations_total", "Degradations by cause", ["code"], registry=REGISTRY)
BUDGET_EXHAUSTED = Counter(
    "adintel_budget_exhausted_total", "Runs that hit a budget limit", ["limit"], registry=REGISTRY
)
TOOL_FAILURES = Counter("adintel_tool_failures_total", "Tool failures", ["tool"], registry=REGISTRY)
KILL_SWITCH_BLOCKS = Counter("adintel_kill_switch_blocks_total", "Dispatches blocked", ["scope"], registry=REGISTRY)

# ---- model ---------------------------------------------------------------------------------------
LLM_TOKENS = Counter("adintel_llm_tokens_total", "Tokens", ["agent", "model", "tenant", "direction"], registry=REGISTRY)
LLM_COST = Counter(
    "adintel_llm_cost_usd_total", "Notional model cost (USD)", ["agent", "model", "tenant"], registry=REGISTRY
)
LLM_LATENCY = Histogram(
    "adintel_llm_call_seconds",
    "Model call latency",
    ["agent", "model"],
    registry=REGISTRY,
    buckets=(0.25, 0.5, 1, 2, 4, 8, 16, 32, 64, 90),
)
LLM_TTFT = Histogram(
    "adintel_llm_first_token_seconds",
    "Time to first token (chat)",
    ["model"],
    registry=REGISTRY,
    buckets=(0.1, 0.25, 0.5, 1, 1.5, 2, 2.5, 4, 8),
)
LLM_VALIDATION_FAILURES = Counter(
    "adintel_llm_validation_failures_total", "Schema validation failures", ["schema"], registry=REGISTRY
)
LLM_REPAIRS = Counter("adintel_llm_repairs_total", "Repair turns", ["schema", "attempt"], registry=REGISTRY)
LLM_FALLBACKS = Counter(
    "adintel_llm_fallbacks_total", "Fallback-chain hops", ["from_tier", "to_tier"], registry=REGISTRY
)
LLM_ERRORS = Counter("adintel_llm_errors_total", "Model call errors", ["tier", "kind"], registry=REGISTRY)
CACHE = Counter("adintel_cache_lookups_total", "Cache lookups", ["cache", "result"], registry=REGISTRY)

# ---- quality -------------------------------------------------------------------------------------
RECOMMENDATION_DECISIONS = Counter(
    "adintel_recommendation_decisions_total", "Approve/reject/modify/expire", ["decision"], registry=REGISTRY
)
REJECTION_REASONS = Counter("adintel_rejection_reasons_total", "Why humans rejected", ["category"], registry=REGISTRY)
ANOMALY_DISMISSALS = Counter("adintel_anomaly_dismissals_total", "Dismissed anomalies", ["reason"], registry=REGISTRY)
GUARDRAIL_BLOCKS = Counter("adintel_guardrail_blocks_total", "Guardrail blocks", ["check"], registry=REGISTRY)
GROUNDING_FAILURES = Counter(
    "adintel_grounding_failures_total", "Ungrounded numbers in prose", ["agent"], registry=REGISTRY
)
REPORT_RATINGS = Histogram(
    "adintel_report_rating", "Account-manager report ratings (1-5)", registry=REGISTRY, buckets=(1, 2, 3, 4, 5)
)

# ---- security ------------------------------------------------------------------------------------
TENANT_VIOLATIONS = Counter(
    "adintel_tenant_isolation_violations_total", "Cross-tenant attempts", ["collection"], registry=REGISTRY
)
INJECTION_FLAGS = Counter("adintel_injection_suspected_total", "Model-flagged injection", ["agent"], registry=REGISTRY)
AUDIT_CHAIN_BROKEN = Gauge(
    "adintel_audit_chain_broken", "1 if the tenant's audit chain fails verification", ["tenant"], registry=REGISTRY
)
EXECUTION_MISMATCHES = Counter(
    "adintel_execution_reconciliation_mismatches_total", "Executed change != approved change", registry=REGISTRY
)

_server_started = False


def serve_metrics(port: int) -> None:
    """Expose /metrics for worker processes (the API mounts its own endpoint)."""
    global _server_started
    if not _server_started:
        start_http_server(port, registry=REGISTRY)
        _server_started = True
