# 0013 — Analyst agent and the code sandbox

**In one sentence:** when something important changes, the Analyst works out *why* — testing
hypotheses against the numbers and running small data queries in a locked box that can't touch
anything else.

## What changed

- `agents/analyst.py` — picks the most material unexplained anomaly and:
  1. computes deterministic facts first, including a **mix vs rate decomposition**: how much of the
     cost-per-sale change comes from budget moving between ad sets versus ad sets getting worse;
  2. retrieves up to 5 similar past incidents and playbooks (this agency only);
  3. asks the frontier model (Qwen3.8-27B) for hypotheses, letting it request up to 3 pandas queries
     per round, 2 rounds maximum;
  4. returns a root cause with a calibrated confidence and confirmed / ruled-out hypotheses.
  If the frontier model is down, the Analyst is **skipped** (not silently replaced by a weaker model)
  and the report discloses it. If the model flags prompt injection, security is paged.
- `sandbox/policy.py` — only a single pandas/numpy expression over `df`: no imports, no file or
  network functions, no `__dunder__` tricks. 12 escape attempts are tested and rejected.
- `sandbox/runner.py` — the expression runs in a **separate process** with CPU, memory and file
  limits, no credentials and a copy of just this campaign's data. `ADINTEL_SANDBOX=docker` runs it in a
  container with networking switched off.

## Why it matters (layman's terms)

For Urban Roast, the decomposition shows that over 70% of the cost increase came from Meta moving
money to an expensive ad set after a budget increase — the ad sets themselves were fine. That
distinction decides the fix: move budget back, rather than pause a healthy ad set.
