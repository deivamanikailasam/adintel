# 0008 — Harness controls

**In one sentence:** we built the safety rails around the agents — spending limits, emergency stop
buttons, protection against double-runs, save points, and a rulebook for what to do when something
breaks.

## What changed

- `harness/budget.py` — every run gets 25 steps, 400k tokens, $2.00 (notional) and 900 seconds.
- `harness/killswitch.py` — emergency stop buttons for everything, one client, one brand or one agent.
  Every flip is audited.
- `harness/idempotency.py` — the same nightly trigger delivered twice maps to the same run.
- `harness/checkpoint.py` — the case file is saved after every step with a fingerprint; a damaged
  save is detected and the run fails cleanly instead of continuing from garbage.
- `harness/timeouts.py` — nested time limits, tested so an outer limit is always longer than the
  inner ones.
- `harness/degradation.py` — the degradation matrix: for every kind of failure, what happens, the
  run status, and the honest sentence that appears in the client report.
- `harness/admission.py` — before a run starts: is the client active, any stop button pressed, too
  many runs this minute, daily cost cap reached?
- `docs/06-reliability/reliability.md`, `docs/06-reliability/slos.md`.

## Why it matters (layman's terms)

Agents are loops, and loops can run forever. The limits here are enforced by code, not by asking the
model nicely. When a limit is hit, the client still gets a report — clearly labelled as limited —
rather than nothing or, worse, something that looks complete but isn't.
