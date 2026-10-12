# 0004 — Storage layer with tenant isolation built in

**In one sentence:** we built the filing cabinet, and made it physically impossible to open another
client's drawer by accident.

## What changed

- `src/adintel/storage/base.py` — a small, backend-neutral database interface (a subset of MongoDB).
- `src/adintel/storage/memory.py` + `matching.py` — an in-memory database with real MongoDB query
  and update semantics, unique indexes and vector search. It powers the tests and a demo that needs
  no Docker at all. Unsupported operators **raise** rather than silently behaving differently from Mongo.
- `src/adintel/storage/mongo.py` — the MongoDB backend. With MongoDB Atlas Local (Docker) it uses
  real `$vectorSearch` with a pre-filter; otherwise it falls back to exact cosine search over the
  already tenant-filtered documents.
- `src/adintel/storage/collections.py` — the catalogue of every collection: purpose, retention and
  indexes (every index starts with `tenant_id`; TTLs for checkpoints, LLM call logs, chat sessions).
- `src/adintel/storage/tenant_repo.py` — **`TenantScopedRepo`**, the only door to tenant data, and
  `SystemRepo`, the explicit, logged door for system jobs that must look across tenants.

## Why it matters (layman's terms)

The success criterion "zero cross-tenant leakage" is binary: one leak is a failure. So we don't rely
on every developer remembering to add a filter. The repository adds the client's ID to **every**
query automatically. If any code — or a model that has been tricked — asks for a different client's
data, the request is refused, counted, and treated as a security incident that pages on-call.

Vector search (the "find similar past incidents" feature) applies the same client filter *inside*
the search, not afterwards. That matters twice: filtering afterwards silently loses results, and it
leaves a moment where another client's text exists in memory.

## How to verify

```bash
make test   # tests/unit/test_storage.py — includes "querying another tenant raises and pages"
```
