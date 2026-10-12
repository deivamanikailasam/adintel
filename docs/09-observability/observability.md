# Observability

Observability must answer three questions:

1. **Is it healthy now?** (system metrics, SLOs, alerts)
2. **Why did this run behave this way?** (traces, the decision log, `llm_calls`)
3. **Is quality changing over time?** (approval rate, rejection reasons, dismissals, grounding failures)

Most teams build the first, some the second, and almost nobody the third — which is where agentic
systems actually degrade.

## The stack

| Concern | Local (this repo) | Production | Code |
|---------|-------------------|-----------|------|
| Agent traces | Langfuse (Docker, self-hosted), optional | Langfuse self-hosted in the VPC | `observability/langfuse.py` |
| Distributed traces | OpenTelemetry → Jaeger (`http://localhost:16686`) | OpenTelemetry → X-Ray | `observability/tracing.py` |
| Logs | Structured JSON to stdout | CloudWatch Logs | `observability/logging.py` |
| Metrics | Prometheus (`/metrics` on api :8000, workers :9464+) | CloudWatch EMF / AMP | `observability/metrics.py` |
| Dashboards | Grafana (`http://localhost:3001`) | Grafana | `deploy/grafana/dashboards/` |
| Alerting | Prometheus rules → Alertmanager → webhook; `notifications` collection | CloudWatch Alarms → PagerDuty/Slack | `observability/alerts.py`, `deploy/prometheus/alerts.yml` |

Every log line carries `trace_id`, `run_id`, `tenant_id` and `brand_id` (bound with
`observability.context.bind(...)`), so one grep reconstructs a run.

## What is watched, by layer

| Layer | Metrics | What a change means |
|-------|---------|---------------------|
| **System** | `adintel_http_requests_total`, `adintel_http_request_seconds`, `adintel_queue_depth`, `adintel_dlq_depth` | Saturation, errors, latency |
| **Agent** | `adintel_runs_total{status}`, `adintel_run_steps` (a growing tail = orchestration drift), `adintel_agent_calls_total{agent}` (Analyst on 80% of runs = accounts degraded or threshold drift), `adintel_degradations_total{code}`, `adintel_budget_exhausted_total`, `adintel_tool_failures_total`, `adintel_orchestrator_decisions_total{decided_by}` | Routing and harness health |
| **Model** | `adintel_llm_tokens_total`, `adintel_llm_cost_usd_total` (by agent, model, tenant), `adintel_llm_validation_failures_total{schema}` (a spike = a prompt or model change broke output), `adintel_llm_repairs_total`, `adintel_llm_fallbacks_total`, `adintel_cache_lookups_total` (**alarm on a drop**: a silent cache miss is a silent cost increase), `adintel_llm_first_token_seconds` | Cost, reliability, latency |
| **Quality** | `adintel_recommendation_decisions_total` (**approval rate**), `adintel_rejection_reasons_total`, `adintel_anomaly_dismissals_total` (rising = drift towards noise), `adintel_grounding_failures_total`, `adintel_guardrail_blocks_total`, `adintel_report_rating` | The third question |
| **Security** | `adintel_tenant_isolation_violations_total`, `adintel_injection_suspected_total`, `adintel_audit_chain_broken`, `adintel_execution_reconciliation_mismatches_total` | Always P1 |

## Explainability is a product feature

One click from a recommendation in the UI opens its run trace: the anomaly with its prediction
interval plotted, the root-cause analysis with the actual pandas code run, the retrieved evidence and
source documents, the exact prompt sent to the Optimizer and the raw model response
(`GET /runs/{run_id}/trace`). This is what makes account managers willing to approve instead of
second-guessing.
