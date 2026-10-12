# 0061 — Know the disk is filling before the database stops

**In one sentence:** AdIntel now watches the machine it runs on and warns on-call before the disk or memory
runs out, and users see a plain-English banner when part of the system is running in a reduced mode.

## What changed

- `observability/host.py` — free disk on the data volume, available memory (Linux `/proc/meminfo`, macOS
  `vm_stat`), load per CPU; Prometheus gauges; scheduler job every minute with P2/P1 thresholds; matching
  Prometheus alert rules.
- `GET /status` (any signed-in user) — overall `ok | degraded | down` and messages for database, model tiers
  (cached 30 s), engaged kill switches and host problems; no internals exposed.
- Web app: polls `/status` every minute and shows an accessible (`role="status"`, `aria-live`) banner.
- Docs: observability. Tests: `tests/unit/test_host_status.py`.

## Why it matters (layman's terms)

In the cloud someone else watches the servers. On your own machine, nobody does — so now AdIntel checks its
own fuel gauge and rings the on-call phone early, and tells users "running on the spare tyre" instead of
leaving them guessing why things are slow.
