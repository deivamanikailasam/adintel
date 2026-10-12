# Threat model (STRIDE-informed catalogue — the 15 threats to know)

| # | Threat | Mitigation | Verified by |
|---|--------|------------|-------------|
| T1 | **Injection via campaign name** (ad-platform free text) | Untrusted fencing, schema output, constraint post-checks, guardrail, typed-exposure human approval, no execution tool | `injection.jsonl`, `test_optimizer.py` |
| T2 | **Poisoned uploaded document** (persistent via RAG) | Sanitise and flag on upload; fence at retrieval; uploads authenticated and audit-logged; soft delete | `test_api.py::test_kb_upload_flags_injection` |
| T3 | **Cross-tenant data request in chat** ("show me all clients' CPAs") | Tenant filter enforced in the *query*, so the model never receives other tenants' data; guardrail name scan; leakage eval gate | `test_storage.py`, `rag.jsonl` leakage probes, `test_chat_memory.py` |
| T4 | **Code-execution escape from the Analyst sandbox** | AST allow-list (no imports, dunders, I/O), separate process, CPU/memory/file limits, network-isolated container, read-only tenant-scoped data | `test_sandbox.py` (12 escapes) |
| T5 | **Credential theft** | Agents never hold credentials; connectors fetch at the boundary; process-role scopes; IAM deny on write secrets for worker/api | `test_connectors.py::test_secret_scopes_follow_process_role`, `iam.tf` |
| T6 | **PII sent to a model provider** | Redaction in the validation wrapper before any call; PII scan on output | `test_llm_gateway.py::test_pii_is_redacted...` |
| T7 | **Denial of wallet** | Per-tenant rate limits and daily caps, per-run budget guard, cost anomaly alert, kill switches | `test_harness.py`, `test_chaos.py::test_budget_exhaustion...` |
| T8 | **Forged or replayed approval** | JWT, approval limits, typed exposure, idempotency (one execution per recommendation), HMAC-signed approval record, snapshot re-check, hash-chained audit | `test_approvals_executor.py` |
| T9 | **XSS from model output in the UI** | Angular interpolation only (escaped), strict CSP, no `innerHTML`/`bypassSecurityTrust*` | `frontend/` code review rule, CSP header |
| T10 | **Compromised fine-tune adapter** | Adapters signed and hash-verified at load; versioned storage with MFA delete; deploy only via CI | `test_llm_gateway.py::test_registry_rejects...`, `finetune/sign_adapter.py` |
| T11 | **Insider viewing a competitor client** | Tenant scope per JWT, brand scope per user, all access audit-logged, anomalous-access alerts | `test_api.py::test_auth_required_and_rbac` |
| T12 | **Compromised agent worker** | Cannot spend money: write credentials and executor role are disjoint; execution needs a signed approval and a snapshot match | `test_approvals_executor.py::test_worker_role_cannot_execute` |
| T13 | **Tampering with history** (covering tracks) | Append-only code path, hash chain verified daily, Object Lock copy in prod | `test_audit.py` |
| T14 | **Data exfiltration through a configured endpoint** (rogue model URL, webhook, tracing backend) | Egress allowlist / offline mode checked at start-up and connect time | `test_egress_weights.py` |
| T15 | **Swapped or corrupted base-model weights** | Weight-file SHA-256 lock, `adintel weights verify` | `test_egress_weights.py` |

**If you could keep only one control, keep the separation in T12.** An attacker inside the agent worker can
call models (cost alerts catch that) but cannot spend money.

## Residual risks (accepted, monitored)

| Risk | Why accepted | Monitor |
|------|--------------|---------|
| A subtle, plausible but wrong recommendation that passes all checks | Human approval is the control; evidence is shown | Approval/rejection rates, 14-day predicted-vs-actual |
| Local sandbox lacks kernel-level network isolation in `subprocess` mode | AST policy blocks network-capable calls; use `ADINTEL_SANDBOX=docker` for full isolation | Sandbox policy tests |
| Local safety classifier (Qwen) is weaker than Llama Guard | Deterministic checks carry the hard guarantees; 100% recall gate | Guardrail eval |
