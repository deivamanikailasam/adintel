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
