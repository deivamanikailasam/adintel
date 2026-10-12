# Runbooks

Each runbook: **detect → contain → fix → verify → learn.** "Learn" always means a new eval case or a new
deterministic rule, never just a prompt tweak.

## Report not delivered by 08:00

1. **Detect:** SLO alert "report SLO at risk" (P2) or the brand shows no run for the week.
2. Check the run status (`GET /runs?brand_id=…`) and the DLQ (`GET /admin/queues`).
3. If the run is `running`/`pending` with a checkpoint: **resume** — `POST /runs/{id}/replay` (or
   `adintel run --brand … --period-end …` for a fresh run if none exists). The run resumes from the last
   checkpoint; nothing already done is repeated.
4. If `failed: all platforms unavailable`: the 06:00 retry will run; check platform status pages.
5. **Verify:** report `released`, notification sent. **Learn:** if a code path failed, add a chaos test.

## Cross-tenant alert (P1, security incident) {#cross-tenant-alert}

1. **Contain immediately:** engage the **global kill switch** (`POST /admin/kill-switches
   {"scope":"global","key":"*","engaged":true,"reason":"P1 cross-tenant"}`).
2. Quarantine output from affected runs (status `held`; recommendations `quarantined`).
3. Determine whether anything reached a user: audit log for `report.released` / API access logs for the
   affected objects. **If yes, escalate to Legal within one hour.**
4. Find the code path from the violation detail (collection, filter) and the trace.
5. **Do not re-enable** until a regression test for that exact path is green in CI.
6. Postmortem in `docs/12-operations/incidents/`.

## Guardrail endpoint down

1. Confirm it is **failing closed**: runs end `held`, `adintel_guardrail_blocks_total{check="classifier_unavailable"}` rising.
2. Restore the model server / endpoint from the **pinned artefact** (`config/models.yaml`); locally:
   `make mlx-small`.
3. Verify with the guardrail eval: `python -m adintel.evals.runner --provider mlx --suites guardrail,injection`.
4. Release held reports **through the guardrail, never around it**: re-run the affected runs.

## Ad-platform schema drift

1. **Detect:** `schema_drift` degradation; a `schema_mapping_proposal` notification for engineering.
2. Review the model-proposed mapping (it is never applied automatically).
3. Implement it deterministically in `connectors/normalize.py` with a fixture and a contract test.
4. Re-run the affected brands.

## Cost spike over 2×

Usual causes, in order — check each before changing anything:
1. **Lost prompt cache** from a prompt-order change (system prompt no longer a stable prefix) →
   `adintel_cache_lookups_total` drop; check the last prompt change.
2. **Repair-loop spike** after a schema change → `adintel_llm_repairs_total` by schema.
3. **Loops hitting step limits** → `adintel_budget_exhausted_total{limit="steps"}`.
4. **One tenant triggering many runs** → cost by tenant on the Models dashboard; rate limit/kill switch.

## Frontier model outage

Runs degrade automatically (Analyst/Optimizer skipped; data summary written; disclosed). Locally: restart
`make mlx-frontier`; check memory pressure. In production: Bedrock status; consider a provisioned
throughput fallback. No manual action is needed for safety.

## Execution failed / reconciliation mismatch (P1)

1. Executions are **never auto-retried**. Read the execution record (`executions`) and the audit entries.
2. If a partial apply happened (shift decreased the source but not the target), the AM restores manually
   in the platform UI and records it; then reconciliation must be green.
3. A reconciliation mismatch means the platform state differs from what was approved: freeze the brand
   (brand kill switch) until explained.

## Audit hash chain break (P1)

1. Identify the first broken `seq` (`GET /admin/audit/verify`).
2. Compare against the S3 Object Lock export (production) to find what changed.
3. Treat as a security incident; preserve evidence; rotate credentials of anyone with DB write access.

## Privacy request or agency offboarding

1. Verify the requester's identity and authority (privacy officer signs off in the ticket).
2. Access request: `adintel privacy-export --tenant <t> --user <u> > export.json`; send through the agreed
   secure channel.
3. Erasure: `adintel privacy-erase --tenant <t> --user <u> --reason "<ticket>"`, then disable the user in
   the identity provider.
4. Offboarding: confirm the contract's legal-record clause; run `adintel offboard --tenant <t> --confirm <t>
   --out offboarding/`; check `manifest.json`; deliver the bundle; revoke each ad platform's OAuth grant and
   delete the tenant's secrets (production: Secrets Manager); close the ticket with the `_system` audit
   entry's `seq`.

## Handover is proven, not asserted

The client's team must be able to: handle every P1 runbook, run the eval suite, add a new brand end to end,
roll back any component, and run the weekly triage — **without** the original engineers.
