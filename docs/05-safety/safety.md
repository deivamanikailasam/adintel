# Safety principles — each one mapped to code and a test

| # | Principle | Enforced by | Proven by |
|---|-----------|-------------|-----------|
| 1 | **No autonomous spending. Ever.** | Optimizer has no execution tool; executor requires a signed human approval; IAM denies model access to the executor | `test_approvals_executor.py`, `test_architecture.py` |
| 2 | **Fail closed on safety checks.** | Guardrail: zero retries, no fallback, timeout = block; approval infra down = nothing executes | `test_guardrail.py`, `test_chaos.py::test_guardrail_hang...` |
| 3 | **Refuse rather than fabricate:** no analysis on untrustworthy data | Data Quality verdict gate in the graph | `test_ingestion_dq.py::test_broken_tracking...`, e2e abort path |
| 4 | **Every number traceable to source data** | Facts from `metrics_daily`; numeric grounding blocks ungrounded prose; template fallback | `test_report.py`, `test_rag.py::test_numeric_grounding` |
| 5 | **Every recommendation traceable to cited evidence** | Optimizer must cite retrieved chunks; constraint check rejects unknown citations | `test_optimizer.py` |
| 6 | **Tenant isolation never degrades** | Three layers; no degradation path relaxes filters | `test_storage.py`, `test_api.py::test_cross_tenant...` |
| 7 | **Every action attributable** to a named human or an identified agent and model version | Audit entries name `user_id` or `agent:<name>@<model_id>` | `test_audit.py`, audit entries in e2e |

## Guardrail design

Deterministic checks first (cannot be bypassed): PII, other-client names, unsafe claims ("guaranteed"),
echoed injection markers, autonomy claims ("we have increased your budget"), numeric re-check. Then a
safety classifier (small model, Llama-Guard-style taxonomy S1–S6) for the semantic tail. Blocked output is
**held for review** and recommendations are **quarantined** — the guardrail blocks, it never edits.

Chat streams through an incremental guard with a hold-back buffer, so a forbidden name can't be
half-emitted before it's recognised.

## Responsible-AI notes

- **Transparency:** every report footer names the system version and states that a human approves every
  change; client disclosure template in `docs/03-governance/client-disclosure.md`.
- **Human agency:** the approval gate is fast and evidence-rich to avoid rubber-stamping; rejections ask
  *why* so the system learns the right lesson.
- **Contestability:** any report can be traced to its inputs (`/runs/{id}/trace`).
- **No silent learning:** procedural rules are proposed, then approved by a senior person.
