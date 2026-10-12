# 0021 — Scheduler, operational jobs and the `adintel` command

**In one sentence:** AdIntel now wakes itself up every Monday night for each brand in that brand's own
timezone, runs its daily housekeeping checks, and can be driven from one simple command.

## What changed

- `scheduler/__main__.py` — the local replacement for EventBridge Scheduler: one weekly job per brand
  at 02:00 *brand-local* time plus a deterministic 0–89 minute stagger (no thundering herd), a 06:00
  retry, and the daily jobs below.
- `scheduler/jobs.py` — audit-chain verification (P1 on a break), execution reconciliation (P1 on a
  mismatch), nightly campaign narratives for RAG, hourly expiry of stale recommendations, a DLQ check
  every 5 minutes (P2 if anything is stuck) and a daily cost-jump check (P3 on > 2×).
- `cli.py` — `adintel seed | demo | run | verify-audit | reconcile | expire | models | token`.
  `adintel demo` replays the canonical night end to end in one process:

```
=== Urban Roast Coffee: awaiting_approval  (12 steps)   → budget_shift $200.00/day pending approval
=== Fitely Activewear: completed  (8 steps)             → straight to report
=== NorthPeak Outdoor: aborted_data_quality  (2 steps)  ✋ conversions exactly 0 for 6 days ...
```

## Why it matters (layman's terms)

The goal was "every brand gets a data-complete report by 8 AM Monday without human help". That needs
a reliable alarm clock per brand, and quiet background checks that shout only when something is wrong.
