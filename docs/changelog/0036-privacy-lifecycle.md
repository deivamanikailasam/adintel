# 0036 — Retention, "forget me" and agency offboarding

**In one sentence:** the retention periods that were written in the data catalogue are now actually
enforced every night, and there are tested, audited procedures for "show me my data", "delete my data" and
"we are leaving — give us our data and delete it".

## What changed

- `privacy/retention.py` — daily purge (02:30 UTC, `adintel purge [--dry-run]`) driven by the catalogue;
  generous rounding; legal hold per tenant; never touches the audit log; counts go to the `_system` audit
  chain.
- `privacy/subjects.py` — `export_user` (access request) and `erase_user` (pseudonymise profile, delete
  chats, blank notes, keep opaque ids on legal records). Admin API `GET /admin/privacy/users/{id}/export`,
  `POST /admin/privacy/users/{id}/erase`; CLI `privacy-export`, `privacy-erase`.
- `privacy/offboarding.py` — kill switch → export bundle → delete (legal records kept by default) → remove
  local credentials → mark inactive → audit. CLI only: `adintel offboard --tenant t --confirm t`.
- `ops/bundle.py` — JSONL-per-collection bundles with a SHA-256 manifest and `verify_bundle`.
- New audit actions: `retention.purge`, `privacy.export`, `privacy.erasure`, `tenant.offboarded`.
- Docs: `docs/04-security/privacy-and-data-lifecycle.md`, data map, runbook.
- Tests: `tests/unit/test_privacy.py` (dry run, legal hold, chain still verifies, other tenants untouched,
  wrong confirmation does nothing, tampered bundle detected) and API tests.

## Why it matters (layman's terms)

Writing "we keep chat logs for 90 days" in a policy is easy; actually deleting them on day 91 is what an
auditor checks. Now the system does it itself, and keeps a receipt. When someone leaves and asks to be
forgotten, their name and email disappear, but the record that "user 1234 approved this $200 change"
stays, because the agency is legally required to keep it. When a whole agency leaves, it gets a sealed
box of its data (with a checksum on every file) and then its data is removed.
