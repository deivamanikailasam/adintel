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

## Error contract

| Code | Meaning |
|------|---------|
| 401 | Missing/invalid token |
| 403 | Role or brand scope insufficient |
| 404 | Not found **or not in your tenant** (deliberately indistinguishable) |
| 409 | Approval check failed — body `{"detail": {"check": "...", "message": "..."}}` |
| 423 | Kill switch engaged |
| 429 | Tenant rate limit / daily cost cap |

## Security headers

Every response carries `Content-Security-Policy: default-src 'none'; frame-ancestors 'none'`,
`X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: no-referrer`,
`Cache-Control: no-store` (except SSE) and, in production, HSTS. CORS is limited to
`ADINTEL_CORS_ORIGINS` (default `http://localhost:4200`).
