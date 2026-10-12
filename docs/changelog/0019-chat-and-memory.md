# 0019 — Chat agent and memory

**In one sentence:** account managers can ask questions about one brand and get fast, data-backed,
streamed answers — and the system "learns" brand habits only when a senior person approves it.

## What changed

- `agents/chat.py` — the Chat agent:
  - **routing**: simple metric questions are recognised by rules and answered from the database with
    the fast model; harder questions go through a small router; diagnostic questions use the frontier
    model plus retrieval;
  - **streaming** answers token by token (the biggest single latency win), through an **output guard**
    that holds back a few characters so a forbidden name can never be half-sent before it is caught;
  - the brand and client come from the session, never from the question; chat cannot change anything.
- `llm/semantic_cache.py` — near-duplicate questions (similarity ≥ 0.97, 15 minutes) are answered
  from cache. **Client and brand are part of the cache key.**
- `memory/conversational.py` — the last 20 turns verbatim plus a running summary; 90-day retention.
- `memory/procedural.py` — dismissing an anomaly records the reason; after three similar dismissals
  (e.g. "planned promo") the system **proposes** a suppression rule; only a senior account manager or
  Head of Performance can approve it, and only then does anomaly detection use it.

## Why it matters (layman's terms)

A system that silently learns to ignore things will eventually ignore something important. AdIntel
proposes what it has noticed and lets a person decide — so it gets smarter without getting sloppier.
