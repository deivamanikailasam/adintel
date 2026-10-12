# Service level objectives

| SLO | Target | Measured by |
|-----|--------|-------------|
| Scheduled report delivered by 08:00 local | 99.0% of brand-weeks | `runs` with `trigger=schedule`, `finished_at` vs brand timezone |
| Run completes (any status except failed) | 99.5% | `adintel_runs_total{status!="failed"}` / total |
| High-severity anomaly surfaced within 24 h | 99.0% | anomaly `created_at` − first out-of-band date |
| Chat p95 first token | < 2.5 s | `adintel_llm_first_token_seconds` |
| API availability | 99.9% | `adintel_http_requests_total{status!~"5.."}` / total |
| Cross-tenant leakage | **0, zero error budget** | `adintel_tenant_isolation_violations_total`, leakage eval |
| Executed change matches the approved change | **100%** | nightly reconciliation job |

Error budgets are reviewed weekly. Burning more than half a monthly budget in a week freezes feature
work on that path until the cause is fixed. The two zero-budget SLOs are not traded against anything.

Local note: mlx-lm on a laptop will not meet the chat latency SLO under concurrent load; measure it
with `make load-test` against production-grade serving before promoting.
