# On-call policy

**Owner decision.** P1 alerts page a human **24/7**; P2 during business hours; P3 goes to the team channel;
P4 stays on dashboards. The rotation is weekly with a primary and a secondary, and needs **at least four
trained people** to be sustainable. Until the team has four, the product owner is primary and a named
backup is secondary — acceptable because of a design property: *nothing can spend client money without a
human approval*, so an unanswered page at night delays reports or data, it does not move money.

## Severity, response and routing

| Severity | Examples | Acknowledge within | Route (local → production) |
|----------|----------|--------------------|----------------------------|
| P1 | Cross-tenant violation, audit chain or archive mismatch, execution ≠ approval, guardrail down, forged approval | 15 min, any time | Alertmanager → AdIntel webhook → Governance console → **PagerDuty 24/7** |
| P2 | Report SLO at risk, frontier outage, DLQ not empty, step-limit storm | 1 business hour | Same → PagerDuty business hours |
| P3 | One platform degraded, failed run, cost > 2×, cache hit drop | Next business day | Same → Slack channel |
| P4 | Single validation failure or fallback | — | Dashboard only |

First move for any P1 that might involve money or data: **engage the narrowest kill switch** (brand →
tenant → global) — it is safe, reversible and audited — then follow the runbook.

## Escalation

1. Primary on-call (page) → 2. secondary after 15 min unacknowledged → 3. product owner / engineering lead
after 30 min → 4. security lead for any P1 in the security audience (isolation, audit, forged approval).
Customer notification for incidents affecting their data follows the DPA (within 48 hours for a personal
data breach) and is the product owner's decision, informed by security.

## Every page must be actionable

- Every alert rule links a runbook (`docs/12-operations/runbooks.md`); an alert without one is not merged.
- Pages are reviewed weekly in the triage meeting: any page that needed no action is tuned or demoted.
- Target: fewer than **2 out-of-hours pages per week**; above that the next sprint fixes the causes first
  (same rule as the error budget in [SLOs](../06-reliability/slos.md)).

## Handover (weekly, 15 minutes)

Open incidents and their owners · kill switches currently engaged and why · feature flags changed this
week · pending migrations or releases · anything waiting on a customer.

## Fairness

Out-of-hours pages earn time off in lieu the next working day; nobody is on call two weeks in a row; new
engineers shadow one rotation before going primary and must have walked every P1 runbook in staging.

## Local setup

With Docker Compose running and `ADINTEL_ALERT_WEBHOOK_TOKEN` set, Prometheus → Alertmanager → the API's
`/internal/alerts/alertmanager` webhook; alerts appear under **Governance → Platform alerts** (firing and
resolved), and app-raised alerts appear in Notifications. Production replaces the webhook receivers with
`pagerduty_configs` (P1/P2) and `slack_configs` (P3); the token must be a random secret ≥ 32 characters
(startup refuses the local one).
