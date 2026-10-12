# 0052 — Test-drive a new model on real work without letting it drive

**In one sentence:** before switching to a new model, AdIntel can quietly ask it the same questions the
current model answers on real traffic, compare the answers, and tell you when it's ready — without the new
model ever influencing a decision.

## What changed

- `llm/shadow.py` — after a champion tier returns a valid answer, a deterministic sample of calls is replayed
  (same redacted messages) against the challenger tier in a background thread, within its own bulkhead;
  output validated against the same schema and compared field by field; stored in `shadow_results`
  (90-day retention). Never charged to the run, never used, failures recorded as data. The safety tier is
  never shadowed.
- `config/models.yaml` — `shadow: { <champion>: { challenger, sample_rate } }` (empty by default); the
  registry validates it.
- `adintel shadow-report`, `GET /admin/shadow` — samples, validity, exact and field agreement, p50 latency
  per agent; verdict `collecting` / `not_ready` / `ready` (≥ 50 samples, ≥ 98 % valid, ≥ 85 % agreement).
- Promotion gate doc and message now point to this as the implementation of the "3-day shadow" step.
- Tests: `tests/unit/test_shadow.py`.

## Why it matters (layman's terms)

A new pilot flies alongside the captain for a while, making every decision in their head while the captain
actually flies. Only when their decisions match the captain's often enough do they get the controls.
