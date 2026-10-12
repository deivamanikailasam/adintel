# Changelog

Every change to AdIntel is recorded twice:

1. **Here**, as a one-line summary per step, newest last.
2. **In [`docs/changelog/`](docs/changelog/)**, as a short plain-English note that explains
   *what changed, why it matters and what it means for someone who is not an engineer*.

The two always move together: a commit that changes behaviour adds a line here and a note there.

| Step | Change | Plain-English note |
|------|--------|--------------------|
| 0001 | Project foundation: packaging, tooling, conventions | [0001](docs/changelog/0001-project-foundation.md) |
| 0002 | Architecture, system design and decision records | [0002](docs/changelog/0002-architecture-and-decisions.md) |
| 0003 | Core building blocks, configuration and the domain model (RunState) | [0003](docs/changelog/0003-core-config-domain.md) |
| 0004 | Storage layer with tenant isolation built in (memory + MongoDB backends) | [0004](docs/changelog/0004-storage-and-tenant-isolation.md) |
| 0005 | Immutable hash-chained audit log with tamper detection | [0005](docs/changelog/0005-audit-log.md) |
| 0006 | Observability foundation: JSON logs, metrics, traces, Langfuse, alert routing | [0006](docs/changelog/0006-observability-foundation.md) |
| 0007 | LLM gateway: mlx-lm provider, model & prompt registries, validation wrapper | [0007](docs/changelog/0007-llm-gateway.md) |
| 0008 | Harness controls: budgets, kill switches, idempotency, checkpoints, timeouts, degradation | [0008](docs/changelog/0008-harness-controls.md) |
| 0009 | Ad-platform connectors (5 platforms, synthetic worlds), normaliser, scoped secrets | [0009](docs/changelog/0009-connectors-and-secrets.md) |
| 0010 | Ingestion and Data Quality agents (seven deterministic checks) | [0010](docs/changelog/0010-ingestion-and-data-quality.md) |
| 0011 | Anomaly Detection agent: STL seasonal band + Isolation Forest, no LLM | [0011](docs/changelog/0011-anomaly-detection.md) |
| 0012 | RAG: semantic chunking, hybrid search with tenant pre-filter, reranking, numeric grounding | [0012](docs/changelog/0012-rag.md) |
| 0013 | Analyst agent with mix-vs-rate decomposition and a code sandbox | [0013](docs/changelog/0013-analyst-and-sandbox.md) |
| 0014 | Optimizer agent (proposes only) and pure-code brand constraints | [0014](docs/changelog/0014-optimizer-and-constraints.md) |
| 0015 | Report agent with a grounding fallback ladder and code-enforced caveats | [0015](docs/changelog/0015-report-agent.md) |
| 0016 | Guardrail agent: deterministic checks + fail-closed safety classifier | [0016](docs/changelog/0016-guardrail.md) |
| 0017 | Orchestrator, LangGraph supervisor graph, run engine, finalize, seed data; e2e + chaos tests | [0017](docs/changelog/0017-orchestrator-graph-engine.md) |
| 0018 | Approval gate (matrix + 7 checks + signing), queues, executor (no LLM), reconciliation | [0018](docs/changelog/0018-approvals-executor.md) |
| 0019 | Chat agent (routing, semantic cache, streaming output guard) and conversational + procedural memory | [0019](docs/changelog/0019-chat-and-memory.md) |
| 0020 | API service (FastAPI): JWT + RBAC, SSE streams, approvals, explainability trace, admin; agent worker | [0020](docs/changelog/0020-api-and-worker.md) |
| 0021 | Scheduler (per-brand timezone + stagger), operational jobs, `adintel` CLI with a one-night demo | [0021](docs/changelog/0021-scheduler-cli.md) |
| 0022 | Quality gates: ruff format/lint clean, mypy --strict clean, test isolation fixes | [0022](docs/changelog/0022-quality-gates.md) |
| 0023 | Angular 18 frontend: live run timeline, explainability trace, approval screen, chat, governance | [0023](docs/changelog/0023-frontend.md) |
| 0024 | Local infrastructure: Docker image, Compose stack (Atlas Local, Redis, Langfuse, Jaeger, Prometheus, Alertmanager, Grafana), alert rules, dashboards | [0024](docs/changelog/0024-local-infrastructure.md) |
| 0025 | mlx-lm serving scripts for the two Qwen models and the step-by-step local setup guide | [0025](docs/changelog/0025-mlx-and-local-setup.md) |
| 0026 | LoRA fine-tuning pipeline for the Report model (mlx_lm.lora), adapter signing, base-vs-adapter-vs-frontier evaluation | [0026](docs/changelog/0026-finetuning.md) |
| 0027 | CI/CD: GitHub Actions for every PR (lint, types, tests + coverage, integration, evals + gate, security scans, frontend, Terraform) and release (staging gates, manual prod, blue/green); k6 load test | [0027](docs/changelog/0027-cicd.md) |
| 0028 | Terraform for AWS production and the step-by-step promotion-to-production guide | [0028](docs/changelog/0028-terraform-and-promotion.md) |
| 0029 | Security & safety documentation: trust boundaries, 13-threat model, tenant isolation, data map, red team, safety principles mapped to code and tests | [0029](docs/changelog/0029-security-safety-docs.md) |
| 0030 | Operations: runbooks, operating cadence, disaster recovery, incident template, cost model | [0030](docs/changelog/0030-operations.md) |
| 0031 | Evaluation harness (10 suites, ~1,100 golden cases, LLM-judge, promotion gate, baseline) — and the fixes it found in retrieval, anomaly detection and the memory backend | [0031](docs/changelog/0031-evaluation-harness.md) |
| 0032 | Documentation front door: README, full docs index and repository map, glossary, FAQ | [0032](docs/changelog/0032-docs-front-door.md) |
| 0033 | Shared state across processes: Redis-backed rate limiter and semantic cache | [0033](docs/changelog/0033-shared-state.md) |
| 0034 | Enterprise single sign-on: OIDC token verification against JWKS, Keycloak as the local identity provider, PKCE login in the UI | [0034](docs/changelog/0034-oidc-sso.md) |
| 0035 | Feedback loop: 14-day outcome tracking (actual vs predicted), per-tenant/brand feature flags, weekly triage report | [0035](docs/changelog/0035-feedback-loop.md) |
| 0036 | Privacy and data lifecycle: retention purge with legal hold, data-subject export and erasure, tenant offboarding with verifiable export bundles | [0036](docs/changelog/0036-privacy-lifecycle.md) |
| 0037 | Write-once audit archive (local files + MinIO Object Lock, S3 in prod) with database comparison; backup, restore and restore-drill tooling | [0037](docs/changelog/0037-audit-archive-backup.md) |
| 0038 | Schema/data migration runner: ordered, locked, recorded, forward-only with expand/contract (ADR L-13); release pipeline runs it as a one-off task | [0038](docs/changelog/0038-migrations.md) |
| 0039 | Bring-your-own-data CSV connector with manual execution through an outbox; template, worked example and docs | [0039](docs/changelog/0039-csv-connector.md) |
| 0040 | Alternative local model servers (Ollama, LM Studio, llama.cpp, vLLM) as one-setting profiles; per-tone report adapters as hash-pinned `report:<tone>` tiers | [0040](docs/changelog/0040-model-servers-tone-adapters.md) |
| 0041 | Repository governance: SECURITY.md, CODEOWNERS, PR and issue templates, pre-commit guard rails, Dependabot, secret scanning and SBOMs in CI | [0041](docs/changelog/0041-repo-governance.md) |
| 0042 | Production-readiness matrix (capability → local implementation → alternatives → production → evidence → status) and README refresh | [0042](docs/changelog/0042-readiness-matrix.md) |
| 0043 | Governance console screens for the learning loop (triage, outcomes, feature flags) and privacy requests; unused Angular scaffold removed | [0043](docs/changelog/0043-learning-privacy-screens.md) |
| 0044 | Owner decision — licence: proprietary LICENSE, enforced dependency-licence policy in CI, third-party notices, model-weights licence recorded per tier (ADR L-14) | [0044](docs/changelog/0044-licence.md) |
| 0045 | Owner decisions — data protection and AI transparency: DPA template, sub-processor register, records of processing, DPIA, AI system card; model providers must not train on or retain data, enforced by the registry (ADR L-15) | [0045](docs/changelog/0045-legal-privacy-pack.md) |
| 0046 | Owner decision — security assurance: external pentest plan (scope, objectives, rules of engagement), OWASP ZAP API scan in CI and `make dast`, API hardening (no server banner, HSTS in staging, Permissions/COOP/CORP headers, API docs off outside local) | [0046](docs/changelog/0046-security-assurance.md) |
| 0047 | Owner decision — branch protection as code: rulesets for the default branch and release tags, an idempotent apply script, and a test that keeps required checks in sync with CI | [0047](docs/changelog/0047-branch-protection.md) |
| 0048 | Owner decision — on-call: 24/7 P1 paging policy, escalation and handover; Alertmanager → API webhook (local PagerDuty/Slack stand-in) with dedupe and resolve; platform alerts in the Governance console | [0048](docs/changelog/0048-on-call.md) |
| 0049 | Owner decision — ad-platform access: platform-by-platform go-live (CSV first, live as approvals arrive, writes after four clean read cycles), per-platform connector modes, production refuses synthetic data, application checklist and tracker | [0049](docs/changelog/0049-ad-platform-access.md) |
| 0050 | Owner decisions register (nine decisions, reasons, enforcement, remaining human actions) and readiness matrix updated — no undecided items left | [0050](docs/changelog/0050-owner-decisions.md) |
| 0051 | Bulkheads: per-tier concurrency caps with fast, visible saturation (fallback instead of pile-up on local model servers); request body size limit (413/411) | [0051](docs/changelog/0051-bulkheads.md) |
| 0052 | Shadow mode (champion/challenger): a candidate model answers a deterministic sample of live calls, is validated and compared field by field, never used; `adintel shadow-report` gives the promotion verdict | [0052](docs/changelog/0052-shadow-mode.md) |
| 0053 | Egress control and offline (air-gapped) mode enforced at start-up and connect time; base-model weight pinning (`adintel weights lock/verify`) for HF-cache and any-server files; threat model T14–T15 | [0053](docs/changelog/0053-egress-offline-weights.md) |
| 0054 | Local credentials encrypted at rest (AES-256-GCM, location-bound, one key per scope so only the executor can decrypt write credentials); `adintel secrets keygen/put/encrypt`; backups exclude keys | [0054](docs/changelog/0054-encrypted-secrets.md) |
| 0055 | SCIM 2.0 user provisioning (joiners, movers, leavers) with per-tenant hashed tokens; approval limits never set by the IdP; deactivated or demoted users lose access on the next request, whatever token they hold | [0055](docs/changelog/0055-scim.md) |
| 0056 | Always-on single-machine deployment: launchd/systemd service generator (restart on failure, hardened units, separate executor OS user, systemd credentials for the write key) and a Caddy HTTPS edge for the office network that hides internal endpoints | [0056](docs/changelog/0056-services-edge.md) |
| 0057 | Readiness matrix and README updated for the second gap review (bulkheads, shadow mode, egress/offline, weight pinning, encrypted secrets, SCIM, supervised services + HTTPS edge); ~300 tests, 89% coverage, gate PASS | [0057](docs/changelog/0057-gap-review-2.md) |
| 0058 | AdIntel as a read-only MCP server for other AI agents: same identity and scope as the web app, GET-only tools, outputs fenced as untrusted data, stdio JSON-RPC transport | [0058](docs/changelog/0058-mcp-server.md) |
| 0059 | Report provenance: released reports carry a signed AI-assistance disclosure and an Ed25519 signature, verifiable offline with the public key or online without login; DB edits detected; threat T16 | [0059](docs/changelog/0059-report-provenance.md) |
| 0060 | Break-glass: time-boxed elevation (all brands / admin) with two-person approval or a paged emergency path, automatic expiry, full audit; never grants money authority; destructive actions refused while elevated | [0060](docs/changelog/0060-break-glass.md) |
| 0061 | Host health (disk, memory, load) metrics with P2/P1 alerts before a single machine runs out; `GET /status` and a plain-English degradation banner in the web app | [0061](docs/changelog/0061-host-health-status.md) |
| 0062 | Versioned integrator API (`/v1`), committed OpenAPI contract with a CI test that fails on breaking changes, `Deprecation`/`Sunset` headers and a 6-month deprecation policy | [0062](docs/changelog/0062-api-versioning.md) |
| 0063 | Web app: idle sign-out, token expiry handling with SSO refresh (refresh token in memory only), IdP logout; accessibility pass (labels, skip link, live regions, focus styles, reduced motion) | [0063](docs/changelog/0063-sessions-accessibility.md) |
| 0064 | Readiness matrix and README updated for the third gap review (MCP server, report provenance, break-glass, host health + status banner, versioned API contract, sessions + accessibility); ~320 tests, gate PASS | [0064](docs/changelog/0064-gap-review-3.md) |
| 0065 | OIDC discovery for every identity provider (authorization, token, JWKS, logout endpoints from the provider's discovery document, with overrides and a Keycloak fallback); Cognito logout style; frontend no longer assumes Keycloak URLs | [0065](docs/changelog/0065-oidc-discovery.md) |
| 0066 | MCP conformance verified with the official MCP Python SDK clients (1.30 and 2.3) over real stdio; CI job `mcp-compat`; `mcp` test extra | [0066](docs/changelog/0066-mcp-conformance.md) |
| 0067 | Accessibility audit: axe-core WCAG 2.1 A/AA scan of all 12 screens in every build (0 violations after fixing contrast, in-text links, page titles, idle-timeout warning and error announcements); full WCAG 2.1 conformance report | [0067](docs/changelog/0067-accessibility-audit.md) |
| 0068 | Readiness matrix: open items closed — OIDC discovery for all identity providers, MCP verified with official SDK clients, accessibility audited (only the manual screen-reader walkthrough remains); ~325 tests, 88% coverage | [0068](docs/changelog/0068-open-items-closed.md) |
