# 0018 — The approval gate and the executor

**In one sentence:** a recommendation can only change a client's account after the right person,
with a high enough limit, types the exact dollar amount to approve it — and the component that then
makes the change has no AI in it at all.

## What changed

- `approvals/matrix.py` — who may approve what (by daily exposure and risk), plus each person's limit.
- `approvals/service.py` — the **seven checks, in order** (pending & not expired, typed exposure
  matches, authority, four-eyes above $2,000 or for high risk, blackout, constraints still pass *now*,
  live ad set unchanged). Approvals are **signed**; rejections need a reason category; reductions are
  allowed and recorded as "gold" feedback; stale recommendations expire.
- `queueing/` — work queues with at-least-once delivery, visibility timeouts and dead-letter queues:
  in-memory, Redis (local) and SQS (production). Executions use a FIFO queue.
- `executor/` — verifies the signature, re-reads live state, applies the change (decrease first,
  retry at most once, never after a partial apply), records the execution once, audits and notifies.
  `executor/reconciliation.py` checks every executed change against the approval nightly.
- The API process now has *read-only* credentials for the live-state re-check at approval time.
- `docs/03-governance/` — governance (autonomy levels, matrix, checks, artefacts, principles), RACI
  and the client-disclosure template.

## Why it matters (layman's terms)

If I could keep only one control, it would be this separation. Even if an attacker fully controlled
the AI side of the system, they could not spend a client's money: they don't have the keys, and the
part that has the keys only acts on a properly signed approval from a named human.
