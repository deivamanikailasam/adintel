# Tenant isolation (zero tolerance)

"Zero cross-tenant data leakage" is binary. It is enforced in three independent layers, so that a bug in
one is caught by the next, and **no failure ever relaxes filtering**.

1. **Data access** — `TenantScopedRepo` injects the tenant from the run/request context into every query
   and insert. A filter naming another tenant (even nested inside `$or`/`$and`) raises
   `TenantIsolationViolation`, increments `adintel_tenant_isolation_violations_total` and raises a **P1**.
   Agents never receive a raw collection (architecture test). Cross-tenant system jobs must use
   `SystemRepo` with a stated, logged purpose.
2. **Retrieval** — the vector-search pre-filter on `tenant_id` runs *inside* the query
   (`$vectorSearch.filter` on Atlas), and tenant + brand are part of every cache key (semantic cache, RAG
   cache). Cross-brand incidents within a tenant are anonymised at index time.
3. **Output** — the guardrail scans every report, recommendation and chat stream for other tenants' and
   other brands' names; cross-tenant leakage is a zero-tolerance eval gate on every deploy.

Plus: `tenant_id` and `brand_id` are frozen in `RunState` and never taken from model output; the API takes
the tenant only from the verified JWT; objects of other tenants return **404** (indistinguishable from
"doesn't exist").

## Runbook pointer

A violation is a security incident: see `docs/12-operations/runbooks.md#cross-tenant-alert`.
