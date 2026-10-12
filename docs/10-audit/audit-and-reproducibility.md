# Audit, determinism and reproducibility

> Full determinism is impossible with LLMs. What AdIntel guarantees is that **every decision can be
> reconstructed exactly**, which is what matters when a client disputes a report.
>
> *"I can't promise identical wording on a re-run, but I can show you exactly what the model saw,
> what it said, and why every number is true."*

## What is made fully deterministic

| Component | How | Code |
|-----------|-----|------|
| Common routing paths | Rules pre-empt the model; ~70% of orchestration hops make no model call | `agents/orchestrator.py` |
| Anomaly detection | STL + Isolation Forest with fixed settings, fixed seed, pinned libraries | `agents/anomaly.py` |
| Data-quality verdict | Pure rules | `agents/data_quality.py` |
| Brand constraints | Pure code, applied after the model | `approvals/constraints.py` |
| Numeric grounding | Pure code: every figure in prose checked against the data | `rag/grounding.py` |
| Retrieval | Pinned embedder and reranker, fixed k, ties broken by chunk ID | `rag/retriever.py` |
| Report structure | Schema-enforced sections; only the prose inside varies | `agents/report.py` |

## What is made reproducible instead

Every LLM call writes an `llm_calls` record: pinned model ID, adapter hash, prompt hash and the full
prompt archived in `prompt_archive` (13 months), response hash and archive, temperature, seed, the IDs
and content hashes of retrieved documents, tokens, notional cost, latency, attempt number and
validation failures. **Given a run ID you can show exactly what the model saw and said**, even if a
re-run would word it differently (`GET /runs/{run_id}/trace`).

Seeds: where a provider supports it, the seed is derived from the run ID, agent and step, so
re-running the same run follows the same path. It is best-effort; nothing depends on it.

## The audit trail

- **Immutable, hash-chained audit log** (`src/adintel/audit/chain.py`). One chain per tenant. Each
  entry includes the hash of the previous one, and its own hash covers every field. Editing an entry,
  deleting one, or editing and re-hashing one all break verification — proven by
  `tests/unit/test_audit.py`.
- **No update or delete path in code.** `AuditLog` exposes only `append` and reads.
- **Daily verification** — `make verify-audit` (or the scheduled job) walks every tenant's chain;
  a break is a **P1** alert ("audit hash chain break").
- **Soft deletes for evidence.** A chunk cited in a March report is still retrievable in September.
- **Trace-to-explanation path.** From any report or recommendation you can walk back to the run,
  every agent step, every model call record and every retrieved source.

## What gets audited

Every run start/finish, every Orchestrator decision (with `decided_by` = rule name or model), every
agent step, every recommendation created/approved/rejected/expired/quarantined, every denied approval
attempt (with the failing check), every execution attempt and result, reconciliation mismatches,
guardrail blocks, kill-switch changes, rule proposals and approvals, anomaly dismissals and security
incidents. The `actor_id` always names a person (`user_id`) or an agent **and its model version**
(`agent:optimizer@mlx-community/Qwen3.8-27B-8bit`) — safety principle 7.

## Production hardening

| Control | Local | Production |
|---------|-------|-----------|
| Append-only | No update/delete in code | + Mongo role with `insert`/`find` only on `audit_log` |
| Tamper evidence | Hash chain + daily verify | + daily export to S3 with Object Lock (compliance mode, 7 years) |
| Retention | 7 years (catalogue) | Same; legal hold supported by Object Lock |
