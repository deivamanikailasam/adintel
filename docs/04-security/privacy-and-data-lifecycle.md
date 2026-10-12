# Privacy and the data lifecycle

How data enters, how long it stays, and how it leaves — with the code that enforces each step.

## Retention is declared once, enforced daily

Every collection's retention is declared in `src/adintel/storage/collections.py` (see the
[data map](data-map.md)). `src/adintel/privacy/retention.py` turns those declarations into deletes:

| Step | Detail |
|------|--------|
| When | Scheduler, daily 02:30 UTC; by hand `adintel purge --dry-run` then `adintel purge` |
| Periods | Parsed generously ("25 months" = 775 days, "7 years" = 2,562 days) so nothing is deleted a day early |
| Time field | `created_at` by default; `date` for metrics, `day` for cost, `at` for events, `approved_at`/`executed_at`/`measured_at` for legal records |
| TTL collections | `expire_at` rows are also removed (MongoDB TTL does this in production; the memory backend has no TTL) |
| Never purged | `audit_log` — deleting entries would break the hash chain. It is archived to write-once storage and expires there |
| Legal hold | A tenant with `legal_hold: true` is skipped completely |
| Evidence | Each purge appends counts (never content) to the `_system` audit chain |

## Requests from people (agency staff)

AdIntel stores little personal data by design: metrics describe campaigns, not people, and PII is
redacted before any model call. What it holds about a *user* is their profile, decisions, notes, chat
sessions and the audit entries naming their id.

| Request | How | What happens |
|---------|-----|--------------|
| Access ("what do you hold about me?") | `adintel privacy-export --user u_x` or `GET /admin/privacy/users/{id}/export` (admin) | One JSON document: profile, approvals, rejections, feedback, chat sessions, audit entries. The export itself is audited |
| Erasure ("forget me") | `adintel privacy-erase --user u_x --reason ...` or `POST /admin/privacy/users/{id}/erase` (admin, never on yourself) | Email and name pseudonymised, roles and limits removed (the account can never act again), chats deleted, free-text notes blanked. Approvals, executions and audit entries keep the opaque `user_id` (legal obligation: who authorised spending client money). Audited |

Also disable the person in the identity provider (Keycloak locally, Cognito in production): AdIntel's
OIDC check refuses users whose AdIntel profile has no roles, but the IdP is where sign-in stops.

## When an agency leaves (tenant offboarding)

`adintel offboard --tenant <id> --confirm <id> --out offboarding/` (CLI only, deliberately not an API):

1. engages the tenant kill switch;
2. exports every tenant-scoped collection to `offboarding/<id>/` — one JSONL per collection plus
   `manifest.json` with SHA-256 per file (hand this to the agency; `verify_bundle` proves it is complete);
3. deletes every tenant document except the legal records (`approvals`, `executions`, `outcomes`,
   `audit_log`), kept for 7 years unless `--delete-legal-records` (contract-dependent, needs legal sign-off);
4. removes local platform credentials (`secrets/<id>/`). **Production:** delete the Secrets Manager
   entries and revoke the OAuth grant on every ad platform — see the runbook;
5. marks the tenant inactive and records the offboarding in the `_system` audit chain.

Re-running is safe. Another tenant's data is never touched (tested).

## Code and tests

`src/adintel/privacy/` · `src/adintel/ops/bundle.py` · `tests/unit/test_privacy.py` ·
`tests/api/test_api.py::test_admin_privacy_endpoints`
