# 0069 — Every setting, command, route and data store is documented — and kept that way

**In one sentence:** an audit of the documentation against the code found reference gaps; they are filled,
the reference pages are now generated from the code, and tests fail if documentation ever falls behind again.

## What the audit found

| Area | Before | After |
|------|--------|-------|
| Settings (`ADINTEL_*`) | 18 of 75 documented nowhere | All 75 in the generated configuration reference |
| CLI commands | `expire`, `reconcile` undocumented | All 28 in the generated CLI reference |
| Collections | 22 of 34 missing from the data map | All 34 in the generated data inventory; new PII-bearing stores added to the data map |
| API routes | 24 of 56 missing from the API reference | All 56 listed, plus `/v1`, headers and 411/413 errors |
| Changelog | Note 0068 lacked its plain-English section | Fixed |
| Links | 0 broken | Still 0 — now enforced |

## What changed

- `scripts/gen_reference_docs.py [--check]` → `docs/13-setup/configuration-reference.md`,
  `docs/13-setup/cli-reference.md`, `docs/04-security/data-inventory.md`. A new setting without a description
  fails the generator. (It immediately caught one of our own errors: the documented values for
  `ADINTEL_VECTOR_SEARCH` were wrong.)
- `cli.build_parser()` so the CLI can describe itself.
- `tests/unit/test_docs_in_sync.py` — generated references current; every API route in the API reference;
  changelog numbering contiguous and every note has a plain-English section; every relative link resolves.
- Docs index, `.env.example` (pointer + hardening settings), data map, CONTRIBUTING updated.

## Why it matters (layman's terms)

A manual that's out of date is worse than none, because people trust it. Now the reference pages are
printed from the machine itself, and the build refuses to pass if any page has fallen behind.
