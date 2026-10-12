# API versioning and deprecation policy

| Path | Audience | Stability |
|------|----------|-----------|
| `/v1/...` | **Integrators** (agency BI tools, scripts, partner systems, the MCP server via HTTP) | Contract: no breaking change within v1 |
| unversioned (`/brands`, `/runs`, …) | The AdIntel web app | May change with each web-app release |
| `/scim/v2`, `/verify/...`, `/.well-known/...`, `/internal/...` | IdPs, clients, infrastructure | Governed by their own standards / docs |

Every response carries `X-AdIntel-API-Version: 1`.

## What counts as breaking (needs `/v2`)

Removing a path or method, removing a response code, adding a **required** parameter or body field,
changing a field's type or meaning, tightening validation on existing input. **Additive** changes — new
paths, optional parameters, new response fields — are allowed in v1; clients must ignore unknown fields.

Enforced in CI: `contract/openapi-v1.json` is the committed contract and `tests/api/test_api_contract.py`
fails on any breaking difference, and on new v1 operations not yet recorded (run
`.venv/bin/python scripts/update_api_contract.py` and commit the file — CODEOWNERS review applies).

## Deprecation

1. Announce in the changelog and to customers' technical contacts **at least 6 months** ahead.
2. Add the path to `DEPRECATED` in `api/app.py`; responses then carry `Deprecation: true`,
   `Sunset: <HTTP-date>` and a `Link` to this policy.
3. Watch usage (`adintel_http_requests_total{route=...}`) and contact remaining callers.
4. Remove after the sunset date — in the next major version for v1 paths.
