# Testing strategy

| Layer | What | Where | When |
|-------|------|-------|------|
| **Unit** | Normalisers for all 5 platforms, every DQ rule, constraint validators, an explicit test that querying another tenant raises, cost/budget, prompt-order (stable prefix), hashing/audit chain, sandbox policy (12 escape attempts), PII/fencing, approval checks | `tests/unit/` | every commit |
| **Architecture fitness** | Agents never touch the raw DB, provider SDKs or write credentials; the executor cannot import model code | `tests/unit/test_architecture.py`, `test_approvals_executor.py` | every commit |
| **API** | Full HTTP flow, RBAC, cross-tenant 404s, idempotency, kill switches, SSE, upload flagging | `tests/api/` | every commit |
| **End-to-end** | The three-brand night through the real engine (mock models) | `tests/e2e/` | every commit |
| **Chaos** | Kill a worker mid-run (must resume), 503 from a platform (must degrade), hang the guardrail (must fail closed), corrupt a checkpoint (must fail cleanly), exhaust the budget, flip a kill switch mid-run, crash an agent | `tests/chaos/` | every commit (monthly in prod against staging) |
| **Integration** | Real MongoDB Atlas Local + Redis | `tests/integration/` (`-m integration`) | every PR in CI with service containers |
| **Agent evals** | Per-agent golden sets | `evals/` | every PR (mock); before promotion (mlx / prod models) |
| **Load** | Monday 06:00–08:00 profile: 50 concurrent runs + 30 chat sessions | `tests/load/monday_peak.js` (k6) | before release |
| **Manual / red team** | Exploratory + injection, isolation, approval bypass, sandbox escape | `docs/04-security/red-team.md` | weekly / quarterly |

```bash
make test        # unit + api + e2e + chaos (no external services)
make test-cov    # same, with the 85% coverage gate on non-LLM code
pytest -m integration   # needs `make up` (Mongo Atlas Local + Redis)
pytest -m mlx           # needs both mlx-lm servers running
```

## Principles

- **Assert on structure, not prose.** No test compares generated sentences.
- **Determinism by construction:** seeded synthetic data, an injectable clock, deterministic mock
  models, ties broken by ID.
- **Every bug becomes a test** at the lowest layer that can catch it.
