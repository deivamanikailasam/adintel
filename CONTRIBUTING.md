# Contributing to AdIntel

## The three rules

1. **One logical change per commit.** A reviewer should be able to read one commit and understand
   one idea. Commit messages explain *why*, not just *what*.
2. **Every change ships with its tests.** Deterministic code (rules, constraints, connectors,
   isolation, cost) is unit-tested. LLM behaviour is covered by the eval suite
   (`make evals`), never by asserting exact prose.
3. **Every change ships with its documentation.** Add a line to `CHANGELOG.md` and a plain-English
   note in `docs/changelog/NNNN-short-name.md`. If the change alters a design decision, add or
   update an ADR in `docs/02-decisions/`.

## Once, after cloning

```bash
make pre-commit     # ruff, mypy, gitleaks and a hook that refuses secrets, client data and model weights
```

Pull requests use `.github/pull_request_template.md`; paths in `.github/CODEOWNERS` need their owner's
approval. Security issues go through [SECURITY.md](SECURITY.md), never a public issue.

## Before you push

```bash
make lint typecheck test-cov security evals gate
```

All six must be green. `make gate` is the same promotion gate CI runs — see
`docs/07-evaluation/promotion-gate.md`.

## Reference docs are generated

`docs/13-setup/configuration-reference.md`, `docs/13-setup/cli-reference.md` and
`docs/04-security/data-inventory.md` come from the code: after adding a setting (with its description in
`scripts/gen_reference_docs.py`), a CLI command or a collection, run `.venv/bin/python scripts/gen_reference_docs.py`.
`tests/unit/test_docs_in_sync.py` fails if they are stale, if an API route is missing from the API reference,
if a changelog note lacks its plain-English section, or if any doc link is broken.

## Non-negotiables (from the safety principles)

- Never add model access to the executor (`src/adintel/executor/`). A test enforces this.
- Never query MongoDB without going through `TenantScopedRepo`. A test enforces this.
- Never read `tenant_id` / `brand_id` from model output. They are frozen in `RunState`.
- Never make the guardrail retry or "fail open". It fails closed.
- Never let an LLM pick a number that goes into a client report. Numbers come from the database.

## Changing prompts or models

Prompts live in `prompts/` and are versioned. Changing a prompt means bumping its version in
`prompts/registry.yaml`, running `make evals` and recording the result. Models are pinned in
`config/models.yaml`; floating references like `latest` are rejected at startup.
