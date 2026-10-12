# 0010 — Ingestion and Data Quality agents

**In one sentence:** the first two agents fetch 180 days of data from every platform in parallel, and
then decide — with seven rule-based checks, not an AI guess — whether that data can be trusted.

## What changed

- `agents/base.py` — the `AgentContext` every agent receives: tenant-scoped data access, the LLM
  gateway, the budget meter and a cancellation token. **No raw database handle.**
- `analytics/frames.py` — loads metrics into pandas and computes totals, ratios (CPA, ROAS, CTR, CPC),
  period-over-period changes and campaign-level daily series. These are the only numbers reports may use.
- `agents/ingestion.py` — fetches all platforms in parallel, each with its own 25-second limit,
  circuit breaker and one retry; normalises to USD; stores rows idempotently. A platform outage becomes
  a disclosed degradation; all platforms down fails the run. Unknown fields trigger a *proposed*
  mapping for engineers — never applied automatically.
- `agents/data_quality.py` — seven deterministic checks: completeness, freshness, **conversion
  tracking**, value sanity, duplicates, currency consistency and spend reconciliation. Verdict:
  trustworthy, degraded (Optimizer blocked) or untrustworthy (run stops, account manager and tech lead
  paged, dashboard shows "Reporting paused"). The small model only writes the two-sentence summary.

## Why it matters (layman's terms)

NorthPeak's API calls all "worked" — they just returned zero sales for six days while clicks were
normal. That is broken tracking, not a collapse in performance. A pipeline would have told the client
their return on ad spend fell 100% and advised pausing their best campaigns. AdIntel's Data Quality
agent catches it and **refuses to produce a deliverable**, which is the most valuable thing it can do
that night.
