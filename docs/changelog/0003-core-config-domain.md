# 0003 — Core building blocks, configuration and the domain model

**In one sentence:** we defined the vocabulary of the system — what a brand, an anomaly, a
recommendation and a "run" are — and one place where every setting lives.

## What changed

- `src/adintel/config.py` — every setting, read from `ADINTEL_*` environment variables, with safe
  local defaults. **It refuses to start in staging/production with development secrets, the dev
  login, in-memory storage or the mock model.** `.env.example` documents every variable.
- `config/models.yaml` — the **model registry**: which model each tier uses (your two mlx-lm models),
  timeouts, token caps, temperatures per agent, fallback chain, owner, the production equivalent and
  a notional price used for budgets.
- `src/adintel/core/` — the error types the harness reacts to (e.g. `TenantIsolationViolation`,
  `BudgetExceeded`), canonical hashing and HMAC signing (used by the audit chain, idempotency and
  approvals), an injectable clock (so tests and replays are deterministic) and ID helpers.
- `src/adintel/domain/` — enums (run statuses, severities, actions, roles, degradation codes, audit
  actions), entities (tenants, brands, users, metric rows, anomalies, root causes, recommendations,
  reports, approvals, executions, brand rules) and **`RunState`**, the one object that flows through
  the agent graph.

## Why it matters (layman's terms)

`RunState` is the case file for one brand's nightly run. Everyone works from the same file, and some
fields are written in permanent ink: **which client the file belongs to can never be changed by an
agent**. That one rule is the first of three locks that stop one client's data reaching another.

The errors are typed on purpose: the system decides "degrade and disclose" vs "stop and page someone"
from the *kind* of failure, not by guessing from an error message.

## How to verify

```bash
make test   # tests/unit/test_core.py: hashing, HMAC tamper detection, prod config refusal, RunState
```
