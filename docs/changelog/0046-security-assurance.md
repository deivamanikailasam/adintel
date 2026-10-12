# 0046 — Getting attacked on purpose, by experts and by machines

**In one sentence:** there is now a plan for an independent penetration test before go-live and every year,
an automated attack scan on every change, and the API gives away less about itself.

## What changed

- `docs/04-security/penetration-testing.md` — owner decision (external test before go-live, annually and
  after major changes), tester selection, scope (staging, two synthetic tenants, sandbox ad accounts),
  six pass/fail objectives (isolation, money-moving, injection, tokens, audit, secrets), rules of
  engagement, deliverables and fix times.
- CI `dast` job — OWASP ZAP API scan driven by the OpenAPI spec against a running API; `make dast` locally;
  `.zap/rules.tsv` documents the three intentionally ignored rules.
- API hardening found while preparing the scan: no `server: uvicorn` banner (`--no-server-header`), HSTS in
  staging as well as production, `Permissions-Policy`, `Cross-Origin-Opener-Policy`,
  `Cross-Origin-Resource-Policy`; Swagger/ReDoc/OpenAPI **off in staging and production** unless
  `ADINTEL_API_DOCS=true`. Test: `tests/api/test_api.py::test_hardened_headers_and_docs_hidden_in_production`.

## Why it matters (layman's terms)

You don't know a lock is good until a locksmith has tried to pick it. The machine scan rattles the door on
every change; the professional locksmith comes before opening day and once a year. And we took the sign
off the door saying which brand of lock it is, and stopped handing out the building's floor plan to anyone
who asks.
