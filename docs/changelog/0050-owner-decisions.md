# 0050 — Every owner decision made and written down

**In one sentence:** one page now lists every decision a production owner has to make — licence, data
protection, model-provider terms, AI oversight, penetration testing, branch protection, on-call, ad-platform
go-live, migrations — with the reason, the code that enforces it, and the few things only a person can
still do.

## What changed

- `docs/03-governance/owner-decisions.md` — the register (nine decisions).
- `docs/14-production/production-readiness-matrix.md` — no ⬜ (undecided) rows remain; each former gap is
  ✅ or 🟡 "decided, human action pending", with links.
- Docs index and README link the register. Evals and promotion gate re-run: PASS.

## Why it matters (layman's terms)

Code can't sign a contract, hire a penetration tester or press "apply" in GitHub settings. What it can do is
make every such decision explicit, explain it, enforce it wherever a machine can, and leave a short,
unambiguous to-do list for the humans.
