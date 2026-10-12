# 0062 — Integrations that don't break when we ship

**In one sentence:** systems that connect to AdIntel now use a versioned address (`/v1`) whose behaviour is
locked by an automated check, and anything we plan to retire is announced in the responses months ahead.

## What changed

- `api/app.py` — business routers mounted under `/v1` as well as unversioned (web app);
  `X-AdIntel-API-Version` header; `DEPRECATED` map adds `Deprecation`, `Sunset` and `Link` headers.
- `contract/openapi-v1.json` (46 operations) + `scripts/update_api_contract.py` — the committed contract:
  per operation, required parameters, required body fields and response codes.
- `tests/api/test_api_contract.py` — fails on removed operations or response codes and on new required
  inputs; also when a new v1 operation hasn't been recorded.
- Docs: `docs/17-api/versioning.md`, API reference pointer; CODEOWNERS covers `/contract/`.

## Why it matters (layman's terms)

A client's reporting tool built on AdIntel shouldn't stop working because we renamed something. Version 1
is now a promise checked by a machine; when something has to go, callers get a dated warning on every
response long before it does.
