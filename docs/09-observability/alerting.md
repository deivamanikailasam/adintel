# Alerting

| Severity | Examples | Route (local) | Route (production) |
|----------|----------|---------------|--------------------|
| **P1, page now** | Cross-tenant violation; guardrail model down; all platforms failing; execution reconciliation mismatch; audit hash-chain break; injection suspected | Alertmanager `page-now` + `notifications` + `ADINTEL_ALERT_WEBHOOK_URL` | PagerDuty 24/7 |
| **P2, business hours** | Report SLO at risk; frontier outage; > 3 step-limit hits/hour; DLQ depth > 0; API 5xx > 1% | `page-business-hours` | PagerDuty business hours |
| **P3** | One platform degraded; a single failed run; cost > 2× daily baseline; cache hit drop > 20%; chat p95 first token > 2.5 s | `slack-or-log` | Slack |
| **P4** | Single validation failures or fallbacks | dashboard only | dashboard only |

Rules: `deploy/prometheus/alerts.yml`. Routing: `deploy/alertmanager/alertmanager.yml`. In-process alerts
(`observability/alerts.py`) also write to the `notifications` collection (visible in the Governance page).

Every alert links to a runbook in `docs/12-operations/runbooks.md`.

On-call rota, response times, escalation and the local Alertmanager → API webhook: [on-call.md](../12-operations/on-call.md).
