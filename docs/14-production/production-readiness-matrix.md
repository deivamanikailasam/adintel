# Production-readiness matrix

What an enterprise-grade agentic AI system needs, how AdIntel provides it on one local machine, the
alternatives you can swap in, the production equivalent, and the evidence. Use it as the review checklist
before promotion ([promotion-to-production.md](promotion-to-production.md)) and as an honest list of what
remains a decision for the owner rather than code.

Legend: ✅ implemented and tested · 🟡 implemented or decided; a production step (configuration, signature, hiring) remains · ⬜ undecided

Every owner decision is now made — see [owner decisions](../03-governance/owner-decisions.md) for what was
decided, why, where it is enforced, and the human actions still needed.

## Agentic core

| Capability | Local implementation | Alternatives | Production | Evidence | Status |
|-----------|----------------------|--------------|-----------|----------|--------|
| Multi-agent orchestration | LangGraph supervisor, rules first, model for judgement | — | Same code on ECS | `tests/e2e`, ADRs L-01…L-12 | ✅ |
| Bounded autonomy (L2) | Agents propose; signed human approval; executor has no model | — | Same | `test_approvals_executor.py`, architecture tests | ✅ |
| Budgets, timeouts, kill switches | Per-run budget, nested timeouts, 4-level switches | — | Same | `test_harness.py`, chaos tests | ✅ |
| Feature flags / staged rollout | Per tenant and brand, audited, visible degradation | — | Same | `test_feedback_loop.py` | ✅ |
| Agent interoperability (MCP) | Read-only MCP server acting as the signed-in user, outputs fenced as data; verified with official SDK clients 1.30 and 2.3 ([mcp.md](../17-api/mcp.md)) | direct `/v1` API | Same | `test_mcp.py`, `tests/mcp/`, CI `mcp-compat` | ✅ |
| Degradation, never silent failure | 21-row matrix → report caveats + metrics | — | Same | `test_harness.py::matrix covers every code` | ✅ |
| Checkpoint & resume | State after every step | — | Atlas | chaos tests | ✅ |

## Models

| Capability | Local implementation | Alternatives | Production | Evidence | Status |
|-----------|----------------------|--------------|-----------|----------|--------|
| Two-tier models | Qwen3.8-27B-8bit (frontier), Qwen3.6-35B-A3B-4bit (volume) on mlx-lm | Ollama, LM Studio, llama.cpp, vLLM (`ADINTEL_MODEL_PROFILE`) | Bedrock / SageMaker | `test_model_profiles.py`, `adintel models` | ✅ |
| Validation wrapper | Schema, repair ×2, retry, fallback, PII redaction, fencing | — | Same | `test_llm_gateway.py` | ✅ |
| Model & prompt registry, pinning | `config/models.yaml`, `prompts/registry.yaml`, floating tags refused | — | Same | registry tests | ✅ |
| Fine-tuning per brand voice | `mlx_lm.lora`, signed adapters, `report:<tone>` tiers | vLLM LoRA modules, llama.cpp `--lora`, Ollama `ADAPTER` | SageMaker QLoRA | `test_model_profiles.py` | ✅ |
| Safety classifier, fails closed | Safety tier, no fallback | — | Llama Guard + Bedrock Guardrails | `test_guardrail.py`, injection evals (100% gate) | ✅ |
| Bulkheads / backpressure | Per-tier concurrency caps, fast `TierSaturated` → fallback; 2 MB body limit | — | Same + ALB limits | `test_bulkhead.py` | ✅ |
| Base-weight integrity | `adintel weights lock/verify` (HF cache or any file) | — | Provider-pinned model IDs | `test_egress_weights.py` | ✅ |

## Data and retrieval

| Capability | Local implementation | Alternatives | Production | Evidence | Status |
|-----------|----------------------|--------------|-----------|----------|--------|
| Ad-platform data | Synthetic worlds with real field shapes | **CSV exports + manual execution**; per-platform `ADINTEL_CONNECTOR_MODES` | Live APIs, platform by platform ([access plan](ad-platform-access.md)) | `test_connectors.py`, `test_csv_connector.py` | 🟡 decided; submit platform applications |
| Storage | Memory backend or MongoDB Atlas Local | — | Atlas over PrivateLink | integration job | ✅ |
| Hybrid RAG with tenant pre-filter | Vector + BM25, RRF, rerank | fastembed BGE | Atlas Vector Search | `test_rag.py`, RAG evals | ✅ |
| Migrations | Ordered, locked, recorded, forward-only | — | One-off ECS task in the release | `test_migrations.py`, ADR L-13 | ✅ |
| Shared state across processes | Redis rate limits + semantic cache | memory (single process) | ElastiCache | `test_shared_state.py` | ✅ |

## Security and identity

| Capability | Local implementation | Alternatives | Production | Evidence | Status |
|-----------|----------------------|--------------|-----------|----------|--------|
| Enterprise SSO | Keycloak OIDC, PKCE, JWKS verification; endpoints from OIDC discovery (Okta, Entra ID, Auth0, Cognito logout style) | dev login (local only) | Cognito / Entra ID / Okta | `test_oidc.py`, `test_oidc_discovery.py` | ✅ |
| Least privilege | IdP roles ∩ AdIntel roles; process-scoped secrets | — | + IAM task roles | `test_oidc.py`, secrets tests | ✅ |
| User lifecycle (SCIM 2.0) | `/scim/v2/Users`, per-tenant hashed tokens, deactivation effective on next request | admin-managed users | Okta / Entra ID provisioning | `test_scim.py` | ✅ |
| Emergency access (break-glass) | Two-person or paged emergency elevation, auto-expiry, no money authority ([break-glass.md](../04-security/break-glass.md)) | — | Same + IdP PIM | `test_break_glass.py` | ✅ |
| Web sessions & accessibility | Idle sign-out with warning, refresh, IdP logout; axe-core WCAG 2.1 A/AA audit of all 12 screens, 0 violations; [conformance report](../16-frontend/accessibility-conformance-report.md) | — | Same | `a11y.spec.ts`, `auth.service.spec.ts` | 🟡 automated audit done; manual screen-reader walkthrough (script ready) |
| Tenant isolation (3 layers) | Data access, retrieval pre-filter, output scan | — | Same | `test_storage.py`, cross-tenant evals (0 leakage gate) | ✅ |
| Sandboxed code execution | Subprocess with AST allow-list | Docker, network-isolated | Separate task / Firecracker | `test_sandbox.py` | ✅ |
| Secrets | File store with scope policy, AES-256-GCM at rest, one key per scope | plaintext (dev only) | Secrets Manager + KMS + IAM | `test_secret_crypto.py` | ✅ |
| Supply chain | Pinned models + adapter hashes, Dependabot, gitleaks, SBOMs, Trivy | — | Same + signed images | CI `security`, `supply-chain` | ✅ |
| Egress control / air-gapped | `ADINTEL_OFFLINE`, egress allowlist checked at start-up and connect time | unrestricted (dev) | VPC without internet route + allowlist | `test_egress_weights.py` | ✅ |
| Penetration test & DAST | ZAP API scan on every PR, `make dast` | — | External test before go-live and annually ([plan](../04-security/penetration-testing.md)) | CI `dast` | 🟡 decided; engage the firm |

## Governance, audit and privacy

| Capability | Local implementation | Alternatives | Production | Evidence | Status |
|-----------|----------------------|--------------|-----------|----------|--------|
| Approval matrix, four-eyes, signed approvals | 7 server-side checks, HMAC | — | Same + KMS key | `test_approvals_executor.py` | ✅ |
| Tamper-evident audit | Hash chain, daily verify | — | Same | `test_audit.py` | ✅ |
| Write-once audit archive | Read-only segments + MinIO Object Lock, compared with the DB nightly | files only (bare metal) | S3 Object Lock, compliance, 7 years | `test_archive_backup.py` | ✅ |
| Report provenance | Ed25519-signed reports with AI disclosure; public key + validity endpoint | — | KMS-held key | `test_provenance.py` | ✅ |
| Retention & legal hold | Catalogue-driven daily purge | — | Same + Mongo TTL | `test_privacy.py` | ✅ |
| Data-subject rights | Export and erasure (pseudonymisation) | — | Same | `test_privacy.py`, API tests | ✅ |
| Tenant offboarding | Kill switch → verifiable export → delete → revoke | — | + revoke platform OAuth grants | `test_privacy.py` | 🟡 OAuth revocation is a runbook step |
| Repository governance | CODEOWNERS, PR template, SECURITY.md, pre-commit, rulesets as code | — | Same | `.github/`, `test_repo_rules.py` | 🟡 decided; run `scripts/apply_repo_rules.sh` once |
| Contracts & privacy (DPA, sub-processors, RoPA, DPIA, AI system card) | Templates in `docs/03-governance/legal/`; provider data terms enforced at start-up (ADR L-15) | — | Signed per customer | `test_model_profiles.py::test_data_terms…` | 🟡 decided; counsel review + signatures |
| Licence | Proprietary `LICENSE`; dependency-licence gate; third-party notices (ADR L-14) | — | Same | CI `supply-chain` | ✅ |

## Quality, evaluation and learning

| Capability | Local implementation | Alternatives | Production | Evidence | Status |
|-----------|----------------------|--------------|-----------|----------|--------|
| Test pyramid | Unit, API, e2e, chaos, architecture, integration, k6 | — | Same in CI | 85% coverage gate | ✅ |
| Eval suites + promotion gate | 10 suites, ~1,100 cases, hard gates, cost ±15% | `make evals-mlx` on any profile | + shadow mode on live traffic (`llm/shadow.py`) | `make evals gate`, `test_shadow.py` | ✅ |
| Outcome tracking | 14-day actual vs predicted, graded in code | — | Same | `test_feedback_loop.py` | ✅ |
| Weekly triage | Auto-prepared page + suggested actions | — | Same | `test_feedback_loop.py` | ✅ |

## Operations

| Capability | Local implementation | Alternatives | Production | Evidence | Status |
|-----------|----------------------|--------------|-----------|----------|--------|
| Observability | Langfuse, Jaeger, Prometheus, Grafana, Alertmanager | — | + CloudWatch, X-Ray, PagerDuty | `test_observability.py`, dashboards | ✅ |
| Host health & status banner | Disk / memory / load alerts; `GET /status` banner | — | CloudWatch / ECS health | `test_host_status.py` | ✅ |
| Backups & restore drills | `adintel backup` (auto-drill), `scripts/backup.sh` | — | Atlas PITR + quarterly DR test | `test_archive_backup.py` | ✅ |
| Process supervision & TLS | launchd / hardened systemd units (separate executor user), Caddy HTTPS edge ([team access](../13-setup/team-access.md)) | terminals (dev) | ECS services + ALB/CloudFront | `scripts/install_services.sh --print` | ✅ |
| Runbooks, cadence & on-call | P1 runbooks; [on-call policy](../12-operations/on-call.md); Alertmanager → API webhook → Governance console | — | PagerDuty / Slack receivers | API tests | 🟡 decided; staff the rotation (≥ 4) |
| CI/CD | GitHub Actions: lint, types, tests, evals, security, SBOM | — | Blue/green with auto-rollback, migrations task | `.github/workflows` | 🟡 needs AWS accounts and secrets |
| API versioning & contract | `/v1`, committed contract, breaking-change test, Deprecation/Sunset headers ([policy](../17-api/versioning.md)) | — | Same | `test_api_contract.py` | ✅ |
| Capacity | k6 Monday-peak profile | — | Load test at real scale in staging | `tests/load` | 🟡 |

## Known limits of the local setup (by design)

- **Admin UI coverage:** feature flags, triage, outcomes and privacy requests have screens
  (`/admin/learning`, `/admin/privacy`); tenant offboarding, retention purge, backups and migrations stay
  CLI-only on purpose — they are rare, destructive operator actions that belong in a ticketed runbook.
- **Single machine:** availability targets in the [DR plan](../12-operations/disaster-recovery.md) assume
  multi-AZ production; locally a reboot means a restart (runs resume from checkpoints).
- **Model quality:** local models are evaluated with the same suites, but production promotion requires the
  gate to pass on the production models (`release.yml` staging job).
