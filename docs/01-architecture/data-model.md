# Data model and multi-tenancy

All data lives in MongoDB in **shared collections**. Every document carries `tenant_id`, and
application code **physically cannot** run a query without the tenant filter.

## Key collections

| Collection | What it holds | Note |
|------------|---------------|------|
| `tenants`, `brands`, `users` | Agencies, their client brands, people and approval limits | `brands.profile` holds tone cluster, timezone, vertical |
| `metrics_daily` | Normalised daily performance rows | Time-series collection in production; index `(tenant_id, brand_id, date)` |
| `runs` | Run records | Unique `idempotency_key` |
| `run_checkpoints` | RunState snapshot after every step, with content hash | Expire after 30 days (TTL) |
| `anomalies` | Detected anomalies and their lifecycle (open, dismissed, resolved) | Dismissal reasons feed procedural memory |
| `recommendations` | Proposed actions and approval state | `expires_at`; snapshot hash of the live entity |
| `approvals` | Signed approval records (who, when, typed exposure, second approver) | Verified by the executor |
| `executions` | Platform writes actually made | **Unique per recommendation** |
| `reports` | Generated reports with sections, facts table and grounding result | Footer names system version and approver |
| `audit_log` | Every decision, approval and execution | **Append-only, hash-chained, verified daily** |
| `llm_calls` | One record per model call (model, prompt hash, response hash, tokens, cost, latency, attempt) | Kept 13 months |
| `cost_events` | Cost per tenant, brand and agent | Drives daily caps and the cost dashboard |
| `brand_rules` | Brand constraints + procedural memory | Human-approved |
| `rule_proposals` | Suppression rules proposed after repeated dismissals | Await human approval |
| `platform_connections` | Ad-account links | **Secret references only, never raw credentials** |
| `kb_chunks` | RAG knowledge base | Vector + text; soft delete |
| `chat_sessions` | Conversational memory | 90-day TTL |
| `kill_switches` | Global / tenant / brand / agent switches | Checked before every dispatch |
| `notifications` | Alerts and approval-queue notices | Local stand-in for Slack/email |
| `feedback` | Report ratings, rejection reasons, modifications | The evaluation flywheel's input |
| `eval_datasets` | Golden scenarios (production copy of `evals/datasets/`) | Versioned |

## How isolation is enforced (three layers)

1. **In the data access layer.** Every query goes through `TenantScopedRepo`
   (`src/adintel/storage/tenant_repo.py`), which injects the tenant from the run context. The raw
   collection handle is never exposed to agents. If a filter names a different tenant, it raises
   `TenantIsolationViolation`, increments a metric and **pages on-call**, because that means a bug or
   an attack.
2. **In retrieval.** The vector-search pre-filter on `tenant_id` runs inside the query, and tenant
   and brand are part of every cache key.
3. **On output.** The guardrail scans for other tenants' and other brands' names, and cross-tenant
   leakage is a zero-tolerance eval gate on every deploy.

Plus: `tenant_id` and `brand_id` are frozen in `RunState` and never taken from model output, and
every index leads with `tenant_id`.

## Why not a database per tenant?

At 12–50 brands under one agency that means 50 connection pools, 50 sets of indexes, 50 vector
indexes to keep warm, and the cross-client analytics the agency actually wants becomes a fan-out
nightmare. The shared model with enforced scoping gives isolation with one operational surface. If a
client contractually demands physical isolation, the repository abstraction keeps that change
contained (ADR D-08).
