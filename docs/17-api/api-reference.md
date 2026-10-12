# API reference (api-service)

> Integrators: use the `/v1` prefix (e.g. `/v1/brands`) — a stable contract; see [versioning.md](versioning.md).
> AI agents: see the read-only [MCP server](mcp.md).

Interactive OpenAPI docs: `http://localhost:8000/docs` when the API is running. All endpoints except
`/health`, `/ready`, `/metrics` and `/auth/dev-login` require `Authorization: Bearer <JWT>`. The tenant
always comes from the token; brand access is checked on every brand-scoped call.

| Method | Path | Roles | Purpose |
|--------|------|-------|---------|
| POST | `/auth/dev-login` | — (local/test only) | Log in as a seeded user by email; returns a JWT |
| GET | `/me` | any | The current principal |
| GET | `/brands` | staff | Brands in scope with last-run status |
| GET | `/brands/{brand_id}/summary` | staff | Runs, open anomalies, latest report, rules |
| POST | `/runs` | AM+ | Start a run (idempotent; 202 + `run_id`); 423 if a kill switch is on, 429 if over quota |
| GET | `/runs`, `/runs/{id}` | staff | Run records |
| GET | `/runs/{id}/events` | staff | **SSE** progress stream (supports `Last-Event-ID`) |
| GET | `/runs/{id}/trace` | staff | **Explainability**: decisions, steps, every model call with its archived prompt and response, retrieved sources, audit entries |
| POST | `/runs/{id}/replay` | AM+ | Resume an unfinished run from its last checkpoint |
| GET | `/reports/{id}` | staff | A report (sections, facts, grounding result, footer) |
| POST | `/reports/{id}/rating` | AM+ | 1–5 rating (flywheel signal) |
| GET | `/recommendations` | staff | Filter by `status`, `brand_id` |
| GET | `/recommendations/{id}` | staff | Recommendation + anomaly + root cause + approval requirement + audit |
| POST | `/recommendations/{id}/approve` | AM+ | `{typed_exposure_usd, modified_amount_usd_per_day?}`; 409 names the failed check |
| POST | `/recommendations/{id}/reject` | AM+ | `{category, note}` |
| GET | `/meta/rejection-categories` | — | Rejection and dismissal reason lists |
| GET | `/anomalies` | staff | Open anomalies |
| POST | `/anomalies/{id}/dismiss` | AM+ | `{reason, note}` — may create a rule proposal |
| GET | `/rule-proposals` | staff | Learned-rule proposals awaiting a decision |
| POST | `/rule-proposals/{id}/decision` | Senior AM / Head | `{approve}` |
| POST | `/chat` | staff | **SSE** chat stream: `meta`, `token`*, `done` / `blocked` / `error` |
| POST | `/kb/documents` | AM+ | Upload a document (sanitised, injection-flagged, audited) |
| GET | `/kb/documents` | staff | Indexed documents |
| GET/POST | `/admin/kill-switches` | Admin (POST), Senior (GET) | Kill switches (tenant/brand scoped to the caller's tenant) |
| GET | `/admin/audit`, `/admin/audit/verify` | Admin / Senior | Audit entries; verify the hash chain |
| GET | `/admin/cost` | Admin / Senior | Notional cost by brand and agent for a day |
| GET | `/admin/models` | Admin / Senior | Model registry + live health of each mlx-lm tier |
| GET | `/admin/notifications` | AM+ | Alerts and notices |
| GET | `/admin/queues` | Admin | Queue and DLQ depths |
| GET | `/health`, `/ready`, `/metrics` | — | Liveness, readiness (DB ping), Prometheus metrics |
| GET | `/auth/config` | — | Which sign-in methods are on, discovered OIDC endpoints, session idle timeout |
| GET | `/status` | staff | Plain-English system status for the banner: database, model tiers, kill switches, host |
| GET/POST | `/admin/flags` | Admin (POST), Senior (GET) | Feature flags: defaults, effective values (optionally per brand), overrides; changes audited, refused under break-glass |
| GET | `/admin/triage` | Admin / Senior | Weekly triage page with suggested actions (`days` 1–90) |
| GET | `/admin/outcomes` | Admin / Senior | 14-day actual-vs-predicted grades of executed changes |
| GET | `/admin/shadow` | Admin / Senior | Shadow-mode report: challenger vs champion per agent, with a ready verdict |
| GET | `/admin/platform-alerts` | Admin | Infrastructure alerts received from Alertmanager (firing / resolved) |
| GET | `/admin/privacy/users/{user_id}/export` | Admin | Data-subject access export (audited) |
| POST | `/admin/privacy/users/{user_id}/erase` | Admin | Pseudonymise a user (never yourself; refused under break-glass) |
| POST | `/admin/break-glass/requests` | staff | Request time-boxed elevation `{scopes, reason, ticket, minutes, emergency}` |
| GET | `/admin/break-glass` | Admin | Elevation requests and grants |
| POST | `/admin/break-glass/{grant_id}/approve` | Admin (not the requester, not elevated) | Activate a requested grant until it expires |
| POST | `/admin/break-glass/{grant_id}/revoke` | holder or Admin | End a grant early |
| GET | `/verify/reports/{report_id}` | — (public) | Is this report genuine and unchanged since signing? Validity only, no content |
| GET | `/.well-known/adintel-report-key` | — (public) | Ed25519 public key for offline report verification |
| POST | `/internal/alerts/alertmanager` | Bearer `ADINTEL_ALERT_WEBHOOK_TOKEN` | Alertmanager webhook (not exposed through the HTTPS edge) |
| GET | `/scim/v2/ServiceProviderConfig` | — | SCIM capabilities |
| GET/POST | `/scim/v2/Users` | SCIM bearer token (per tenant) | List (filters `userName eq`, `externalId eq`) / provision users |
| GET/PUT/PATCH/DELETE | `/scim/v2/Users/{user_id}` | SCIM bearer token | Read / replace / patch / deactivate a user — see [user-provisioning](../04-security/user-provisioning.md) |

All business routes above are also served under **`/v1/...`** (the versioned integrator contract — see
[versioning.md](versioning.md)); responses carry `X-AdIntel-API-Version`.

## Error contract

| Code | Meaning |
|------|---------|
| 401 | Missing/invalid token |
| 403 | Role or brand scope insufficient |
| 404 | Not found **or not in your tenant** (deliberately indistinguishable) |
| 409 | Approval check failed — body `{"detail": {"check": "...", "message": "..."}}` |
| 423 | Kill switch engaged |
| 411 / 413 | Chunked body without length / body larger than `ADINTEL_MAX_REQUEST_BYTES` |
| 429 | Tenant rate limit / daily cost cap |

## Security headers

Every response carries `Content-Security-Policy: default-src 'none'; frame-ancestors 'none'`,
`X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: no-referrer`,
`Cache-Control: no-store` (except SSE), `Permissions-Policy`, `Cross-Origin-Opener-Policy`,
`Cross-Origin-Resource-Policy` and, in staging and production, HSTS. No `Server` banner. CORS is limited to
`ADINTEL_CORS_ORIGINS` (default `http://localhost:4200`).
