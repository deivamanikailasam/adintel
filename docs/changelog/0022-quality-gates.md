# 0022 — Quality gates green: lint, formatting, strict types

**In one sentence:** every line of Python now passes the same automated checks CI will enforce, so
code style and type mistakes can't creep in unnoticed.

## What changed

- `ruff format` applied to all code; `ruff check` clean with security rules (`S`) on. Line length is now
  owned by the formatter (120); en dashes/arrows in docs strings are allowed on purpose.
- `mypy --strict` clean across 130+ modules: providers now formally implement the `LLMProvider`
  interface, `Model.from_doc()` returns a typed object (and ignores workflow fields added by other
  services, e.g. `approval_id` on a recommendation), and a few annotations were added.
- Test isolation: security hooks are installed once (no double-counting metrics), the semantic cache is
  reset between tests, and the secrets test reflects the API's read-only credential.

## Why it matters (layman's terms)

"Production ready" starts with boring discipline. Strict type checking catches the most common class of
bug in agent systems — the wrong shape of data passed between steps — before anything runs.

## How to verify

```bash
make lint typecheck test
```
