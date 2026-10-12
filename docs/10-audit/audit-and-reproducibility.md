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
| Tamper evidence | Hash chain + daily verify + nightly write-once archive (read-only files, and MinIO with Object Lock in Compose) | Same code → S3 with Object Lock (compliance mode, 7 years) |
| Retention | 7 years (catalogue); the purge job never deletes audit entries | Same; legal hold supported by Object Lock |

## The write-once archive (`src/adintel/audit/archive.py`)

A hash chain proves entries weren't edited *one at a time*. Someone with database write access could
still rewrite an entry and recompute every hash after it — the chain would verify. The archive closes that
gap: every night at 03:45 UTC new entries are copied as a segment (`<tenant>/000144-000150.jsonl` +
`.sha256`) that is made read-only and, when `ADINTEL_AUDIT_ARCHIVE_S3_BUCKET` is set, uploaded with Object
Lock retention. The same job then compares database and archive and pages security (P1) on any
difference. Test: `tests/unit/test_archive_backup.py::test_archive_detects_a_consistently_rewritten_database`.

| | Local (bare) | Local (Compose) | Production |
|-|--------------|-----------------|-----------|
| Where | `var/audit-archive/` (0444 files) | + MinIO bucket `adintel-audit`, Object Lock GOVERNANCE 30 days | S3 bucket from `infra/terraform/modules/adintel/data.tf`, COMPLIANCE, 2,557 days |
| Commands | `adintel audit-archive` · `adintel audit-archive --verify` | same | same (scheduler) |
| Settings | `ADINTEL_AUDIT_ARCHIVE_DIR` | `ADINTEL_AUDIT_ARCHIVE_S3_BUCKET`, `_S3_ENDPOINT`, `_LOCK_MODE`, `_LOCK_DAYS` | endpoint unset (AWS), `LOCK_MODE=COMPLIANCE`, `LOCK_DAYS=2557`, task-role IAM instead of keys |

## Report provenance (`src/adintel/audit/provenance.py`)

Every **released** report is signed when it is finalised: SHA-256 of its canonical content (title, sections,
facts, model tier, adapter hash, system version, AI-assistance disclosure) and an **Ed25519** signature of
that hash. Because the signature is asymmetric, clients and auditors verify a report **offline** with the
public key from `GET /.well-known/adintel-report-key` (`adintel verify-report report.json --public-key key.pem`),
or online, without logging in, at `GET /verify/reports/{report_id}` — which recomputes the hash from the
stored report and so also detects an edit made in the database. The endpoint returns validity only, never
content. Held reports are not signed. Key: `ADINTEL_REPORT_SIGNING_KEY` (required in staging/production;
generated in `var/keys` locally). Tests: `tests/unit/test_provenance.py`.
