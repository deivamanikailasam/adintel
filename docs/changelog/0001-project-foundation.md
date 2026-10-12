# 0001 — Project foundation

**In one sentence:** we laid the foundations of the building — the plot, the plumbing plan and the
house rules — before putting up any walls.

## What changed

- `pyproject.toml` declares AdIntel as a Python 3.12 project and lists every library it uses.
  Optional "extras" keep heavy pieces out of the way until you need them:
  `ml` (real embedding and re-ranking models) and `aws` (production adapters).
- `Makefile` gives every common task a short, memorable command: `make test`, `make up`,
  `make run-api`, `make evals`, `make gate` and so on. `make help` lists them.
- `.gitignore` makes sure secrets (`.env`, `secrets/`), local data, trained model adapters and
  build output can never be committed by accident.
- `.editorconfig` keeps formatting consistent across editors.
- `CHANGELOG.md` and `docs/changelog/` set up the rule that **every change is explained in plain words**.
- `CONTRIBUTING.md` writes down how we work: one change per commit, tests with every change,
  documentation with every change.

## Why it matters (layman's terms)

A system that moves client money has to be boring and predictable to work on. Deciding the rules up
front — how code is checked, how secrets are kept out of the repository, how every change is
explained — is cheaper than fixing bad habits later.

## Quality gates set up from day one

| Gate | Tool | Why |
|------|------|-----|
| Lint | ruff | Catches bugs and unsafe patterns early (includes security rules) |
| Types | mypy --strict | Wrong data shapes are the most common bug in agent systems |
| Tests | pytest + 85% coverage on non-LLM code | Deterministic code must be proven, not trusted |
| Security | bandit | Flags risky code such as shell injection |
