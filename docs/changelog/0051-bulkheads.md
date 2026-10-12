# 0051 — Don't let everyone queue at the same model at once

**In one sentence:** each model tier now accepts only a set number of simultaneous requests from each
process; when it's full, callers fail over to the next tier quickly instead of all timing out together, and
oversized requests are refused at the door.

## What changed

- `llm/bulkhead.py` — a slot per (server, model) with `max_concurrency` and `queue_timeout_seconds` per tier
  in `config/models.yaml` (frontier 2 / 60 s, small 4 / 30 s, report 4 / 30 s, safety 4 / 10 s). A full tier
  raises `TierSaturated` (a kind of `LLMUnavailable`), so the validation wrapper falls back or degrades
  visibly; the safety tier still fails closed. Metrics: `adintel_llm_in_flight{tier}`,
  `adintel_llm_bulkhead_rejections_total{tier}`.
- API: request bodies over `ADINTEL_MAX_REQUEST_BYTES` (2 MB) → 413; chunked bodies without a length → 411.
- Tests: `tests/unit/test_bulkhead.py` (fast timeout, fallback to the small tier when the frontier is full,
  413).

## Why it matters (layman's terms)

A local model is like a single checkout lane. If twenty people join the queue at once, everyone waits until
they give up. Now only a couple of people queue at a time; the rest are sent straight to the next open lane,
or told honestly that it's busy.
