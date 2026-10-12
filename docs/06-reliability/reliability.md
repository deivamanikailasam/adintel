# Reliability: validation, timeouts and degradation

The governing principle: **degrade visibly, never fail silently, and never fabricate.** A partial
report with an honest gap is useful; a complete-looking report built on missing data is dangerous.

## Per-agent timeout policy (`harness/timeouts.py`)

| Agent | Timeout | On timeout | What the user gets |
|-------|---------|------------|--------------------|
| Ingestion | 120 s (25 s per platform) | Use the platforms that returned | Report on 4 of 5 platforms, gap disclosed |
| Data Quality | 60 s | **Fail the run** | Nothing; no trust verdict means no analysis |
| Anomaly | 90 s | Skip | Metrics without an anomaly section, disclosed |
| Analyst | 240 s | Skip | Anomaly without root cause, so no Optimizer |
| Optimizer | 180 s | Skip | Findings without recommendations |
| Report | 200 s | Fall back to frontier, then deterministic template | Slower, still delivered |
| Guardrail | 60 s | **Fail closed, release nothing** | Held for review |

Two details: ad-platform **writes** retry at most once, because a retry after a partly applied change
is worse than a failure. And the guardrail never retries: a slow safety check is a failed safety check.

**Timeouts must really stop work.** Cancelling a task doesn't stop an in-flight model request from
finishing and being billed. So every provider client has its own shorter timeout, the Analyst checks
for cancellation between tool steps, the code sandbox is a separate process killed on its hard limit,
and timed-out calls are still charged in cost tracking.

## The degradation matrix (`harness/degradation.py`)

Every row is code: `degrade(code, agent, detail)` records it in state, increments
`adintel_degradations_total{code}` and supplies the client caveat sentence.

| Failure | What happens | Status |
|---------|--------------|--------|
| One ad platform down | Continue with the rest; banner names the gap | degraded |
| All platforms down | Abort before analysis; retry at 06:00 | failed |
| Conversion tracking broken | Abort all analysis; page the account manager | aborted_data_quality |
| Data quality only has warnings | Anomaly + report allowed; **Optimizer blocked** | degraded |
| Less than 28 days of history | Skip anomaly detection; raw metrics only | degraded |
| Frontier model outage | Skip Analyst and Optimizer; small model writes a data summary | degraded |
| Fine-tuned report fails the number check | Rewrite with frontier | degraded |
| No model can write a grounded report | Deterministic template with exact figures | degraded |
| Vector search down | Optimizer needs ≥1 citation, so it produces nothing | degraded |
| Reranker down | Use raw retrieval order | degraded |
| Step limit hit (possible loop) | Best-effort finalize; **page** — it signals an orchestration bug | degraded |
| Approved execution fails at the platform | Mark failed, **never auto-retry**, notify the AM | — |
| Cross-tenant filter violation | **Halt immediately**, quarantine output, security incident | failed |
| Model flags prompt injection | Quarantine output, page security | held |

## Three things that never degrade

1. **Tenant isolation.** No failure relaxes filtering.
2. **The approval gate.** If approval infrastructure is down, nothing executes.
3. **Numeric grounding.** If numbers can't be verified, the report is held.

## Other mechanisms

- **Circuit breakers** per platform and per model tier: open after 5 failures in 60 s, half-open after
  30 s (`core/resilience.py`).
- **Bulkheads:** separate connection pools per platform and per model tier, so a Meta incident can't
  starve Google.
- **Dead-letter queues** on every queue, alarm on depth > 0.
- **Graceful shutdown:** workers checkpoint and exit within 120 s on SIGTERM; the message becomes
  visible again and another worker resumes from the checkpoint.
- **Kill switches** at global, tenant, brand and agent level, checked at admission and before every
  dispatch (`harness/killswitch.py`).
- **Admission control:** tenant active, 30 runs/minute per tenant, daily notional cost cap with a P3
  alert at 80% and a soft stop at 100% (`harness/admission.py`).
- **Schedule stagger:** 90 minutes, to avoid a thundering herd at 02:00.
