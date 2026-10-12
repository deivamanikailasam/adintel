## What and why

<!-- One logical change. What problem does it solve? -->

## In plain English

<!-- Two or three sentences a non-engineer can follow (this also goes in docs/changelog/NNNN-*.md). -->

## Checklist

- [ ] One logical change; commit message explains *why*
- [ ] Tests added or updated (`make lint typecheck test-cov`)
- [ ] `CHANGELOG.md` row and `docs/changelog/NNNN-*.md` note (with a layman's-terms section)
- [ ] Docs updated where behaviour changed; ADR added/updated if a design decision changed
- [ ] Prompts or models changed → version bumped, `make evals gate` run, results attached
- [ ] Data shape changed → migration added (`storage/migrations/versions.py`), expand/contract respected

## Safety and security impact

- [ ] Executor still has no model access; agent worker still has no write credentials
- [ ] Every data access goes through `TenantScopedRepo` (or a `SystemRepo` with a stated purpose)
- [ ] No number in a client report can come from model output
- [ ] Guardrail still fails closed; nothing new can spend money without a signed approval
- [ ] No secrets, PII or client data in code, fixtures, logs or this PR

<!-- If any box above cannot be ticked, explain why here and request a security review. -->
