# 0033 — Rate limits and the chat cache shared across processes

**In one sentence:** when the API, worker and scheduler run as separate processes (or several API
copies), they now share one rate-limit counter and one chat cache instead of each keeping its own.

## What changed

- `ADINTEL_SHARED_STATE=memory|redis` (Compose sets `redis`).
- `harness/admission.py` — `RedisRateLimiter` (sliding window in a Redis sorted set per tenant) and
  `make_limiter()`; both the per-tenant run quota and the API rate limit use it.
- `llm/semantic_cache.py` — `RedisSemanticCache`: one Redis list per (tenant, brand) scope with the
  15-minute TTL, so the client boundary is still part of the key.
- Failure behaviour is explicit: a Redis outage makes the cache a miss and the limiter **fail open** (it's a
  capacity/cost control, already bounded by per-run budgets and daily caps — not a safety control).
- Tests with fakeredis prove the window is shared between "processes" and the cache never crosses
  tenants or brands.

## Why it matters (layman's terms)

With two API copies, a per-process limit of 30 runs a minute quietly becomes 60. Shared counters make
limits mean what they say.
