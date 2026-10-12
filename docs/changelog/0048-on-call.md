# 0048 — Who gets woken up, how fast, and where they see it

**In one sentence:** there is now a written on-call policy, and locally the monitoring system's alerts land
in AdIntel's own Governance screen instead of nowhere.

## What changed

- `docs/12-operations/on-call.md` — owner decision: P1 pages 24/7 (acknowledge in 15 min), P2 business hours,
  P3 to the team channel; weekly primary/secondary rotation (≥ 4 trained people, owner + named backup until
  then, justified by "nothing spends money without approval"); escalation chain; "every page actionable"
  rules; weekly handover; time off in lieu.
- `api/routers/ops.py` — `POST /internal/alerts/alertmanager`: bearer-token protected (404 when not
  configured), stores platform alerts under tenant `_system`, one row per fingerprint, resolved alerts
  update the open row. `GET /admin/platform-alerts` (admin only).
- `deploy/alertmanager/alertmanager.yml` — receivers now post to that webhook (was a placeholder `/health`
  URL); Compose sets the local token; Alertmanager can reach the host on Linux too.
- Production startup refuses the local or a short alert token.
- Governance page: **Platform alerts** panel (firing / resolved).
- Tests: webhook auth, dedupe, resolve, role check; weak-token refusal.

## Why it matters (layman's terms)

A fire alarm that rings in an empty room isn't a fire alarm. Now every alarm has a named person, a response
time and a next person to call, and on a laptop the alarms show up on the screen the team already uses.
