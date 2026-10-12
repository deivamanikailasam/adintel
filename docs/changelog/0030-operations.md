# 0030 — Running AdIntel day to day

**In one sentence:** the people who operate AdIntel now have written procedures for every serious
failure, a calendar of routine checks, a disaster-recovery plan and an honest cost model.

## What changed

- `docs/12-operations/runbooks.md` — report not delivered by 08:00 (resume from checkpoint), cross-tenant
  alert (global kill switch, quarantine, legal within an hour, don't re-enable until a regression test is
  green), guardrail down (fail closed; release held output *through* the guardrail), schema drift, cost
  spike over 2× (the four usual causes in order), frontier outage, failed execution / reconciliation
  mismatch, audit chain break — and the rule that handover is proven, not asserted.
- `docs/12-operations/operational-cadence.md` — daily, weekly, fortnightly, monthly, quarterly, annual.
- `docs/12-operations/disaster-recovery.md` — RTO/RPO per scenario, local backup/restore.
- `docs/12-operations/incidents/TEMPLATE.md` — postmortem template; every P1/P2 produces a new eval case
  or rule.
- `docs/11-cost/cost-model.md` — cost per run type, monthly bill at 12 brands, scaling to 1,000 brands, the
  honest gap against the $0.60/brand/day target, cost controls, token discipline, latency strategies, and
  what "notional" cost means locally.

## Why it matters (layman's terms)

The agents are about 30% of the work. Knowing exactly what to do at 3 AM when something goes wrong is a
large part of the other 70%.
