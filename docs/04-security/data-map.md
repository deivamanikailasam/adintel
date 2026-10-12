# Data map

What personal data exists and who can read it. The complete list of collections, with retention and how each
is purged, is the generated [data inventory](data-inventory.md).

| Data | Source | Where (local / prod) | Contains PII? | Retention | Who can read |
|------|--------|----------------------|---------------|-----------|--------------|
| Daily metrics | Ad platforms (read API) | `metrics_daily` (Mongo) | No (aggregates) | 25 months | Tenant users in brand scope; agents via tenant repo |
| Campaign/entity names | Ad platforms | `metrics_daily` | Unlikely; treated as untrusted | 25 months | As above |
| Platform credentials | Agency onboarding | `secrets/` / Secrets Manager | Secret | Rotated 90 days | Read: worker, api, executor; **Write: executor only** |
| Run state & checkpoints | AdIntel | `runs`, `run_checkpoints` | No | Checkpoints 30 days; runs 24 months | Tenant users; engine |
| Prompts and responses | AdIntel | `prompt_archive` / S3 | Redacted before sending | 13 months | Tenant seniors, auditors |
| LLM call records | AdIntel | `llm_calls` | No | 13 months | Tenant seniors, ML lead |
| Reports | AdIntel | `reports` | No | 24 months | Tenant users in brand scope |
| Recommendations, approvals, executions | AdIntel + humans | Mongo | Approver user IDs | 7 years (approvals/executions) | Tenant users; auditors |
| Audit log | AdIntel | `audit_log` + S3 Object Lock | User IDs | 7 years | Admins, auditors |
| Knowledge base | Agency uploads, playbooks, past reports | `kb_chunks` | Possible in uploads → flagged | Indefinite, versioned, soft delete | Tenant (anonymised cross-brand) |
| Chat sessions | Account managers | `chat_sessions` | Possibly | 90 days | The user, tenant admins |
| Feedback | Account managers | `feedback` | User IDs | 24 months | ML lead (flywheel) |
| Users | Agency | `users` / Cognito | Name, email | Account lifetime | Tenant admins |
| Break-glass grants | Staff requests | `access_grants` | User ids, reason, ticket | 7 years | Admins, security |
| SCIM tokens | Admin (CLI) | `scim_tokens` | No (SHA-256 of token only) | Until revoked | System |
| Feature flags | Admins | `feature_flags` | Actor user id | Indefinite | Admins, seniors |
| Outcomes | AdIntel (14-day grading) | `outcomes` | No | 7 years | Admins, seniors |
| Shadow results | Challenger model outputs | `shadow_results` | Redacted model output | 90 days | Admins, seniors, ML lead |
| Signed reports | AdIntel | `reports.provenance` | No | With the report | Public: validity only |

**Models:** locally, all inference runs on your machine (mlx-lm); nothing leaves it. In production, Bedrock
is used with data retention disabled and no training on inputs; self-hosted models run inside the VPC.

**Deletion requests (GDPR/CCPA):** the user's profile in `users` is pseudonymised, their `chat_sessions`
are deleted and free-text notes in `feedback`/`recommendations` are blanked; approvals and audit entries
keep the user ID as a pseudonymous reference (legal basis: legitimate interest / legal obligation).
Retention periods above are enforced daily by `adintel purge`. Details, commands and offboarding:
[privacy-and-data-lifecycle.md](privacy-and-data-lifecycle.md).
