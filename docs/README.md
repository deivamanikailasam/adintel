# AdIntel documentation

Every document is written so that a non-engineer can follow the "why", and an engineer can find the code.
Plain-English notes for every change live in [changelog/](changelog/).

## Start here

| If you are… | Read |
|-------------|------|
| New to AdIntel | [What AdIntel is](00-overview/what-is-adintel.md) → [Glossary](00-overview/glossary.md) → [FAQ](00-overview/faq.md) |
| Setting it up on your Mac | [Local setup, step by step](13-setup/local-setup.md) |
| Taking it to production | [Promotion to production, step by step](14-production/promotion-to-production.md) |
| Reviewing the design | [Architecture](01-architecture/architecture.md) → [Decisions](02-decisions/README.md) |
| Approving it for use (risk, legal, security) | [Governance](03-governance/governance.md) → [Security](04-security/security.md) → [Safety](05-safety/safety.md) → [Data map](04-security/data-map.md) |
| Operating it | [Runbooks](12-operations/runbooks.md) → [Alerting](09-observability/alerting.md) → [Cadence](12-operations/operational-cadence.md) |

## All sections

| # | Section | Documents |
|---|---------|-----------|
| 00 | Overview | [What AdIntel is](00-overview/what-is-adintel.md) · [Glossary](00-overview/glossary.md) · [FAQ](00-overview/faq.md) |
| 01 | Architecture & system design | [Architecture](01-architecture/architecture.md) · [AWS ↔ local mapping](01-architecture/aws-to-local-mapping.md) · [Agent team](01-architecture/agent-team.md) · [Graph & harness](01-architecture/graph-and-harness.md) · [LLM gateway](01-architecture/llm-gateway.md) · [Model strategy](01-architecture/model-strategy.md) · [RAG & memory](01-architecture/rag-and-memory.md) · [Data model](01-architecture/data-model.md) |
| 02 | Decisions | [25 ADRs](02-decisions/README.md) · [Open questions](02-decisions/open-questions.md) · [ADR template](02-decisions/template.md) · [Anti-patterns avoided](anti-patterns.md) |
| 03 | Governance | [Governance & HITL](03-governance/governance.md) · [RACI](03-governance/raci.md) · [Client disclosure](03-governance/client-disclosure.md) |
| 04 | Security | [Security](04-security/security.md) · [Threat model](04-security/threat-model.md) · [Tenant isolation](04-security/tenant-isolation.md) · [Data map](04-security/data-map.md) · [Privacy & data lifecycle](04-security/privacy-and-data-lifecycle.md) · [Red team](04-security/red-team.md) |
| 05 | Safety | [Safety principles → code → tests](05-safety/safety.md) |
| 06 | Reliability | [Validation, timeouts & degradation](06-reliability/reliability.md) · [SLOs](06-reliability/slos.md) |
| 07 | Evaluation | [Evaluation](07-evaluation/evaluation.md) · [Flywheel](07-evaluation/flywheel.md) · [Promotion gate](07-evaluation/promotion-gate.md) |
| 08 | Testing | [Testing strategy](08-testing/testing-strategy.md) |
| 09 | Observability | [Observability](09-observability/observability.md) · [Alerting](09-observability/alerting.md) |
| 10 | Audit | [Audit, determinism & reproducibility](10-audit/audit-and-reproducibility.md) |
| 11 | Cost | [Cost, tokens & latency](11-cost/cost-model.md) |
| 12 | Operations | [Runbooks](12-operations/runbooks.md) · [Cadence](12-operations/operational-cadence.md) · [Disaster recovery](12-operations/disaster-recovery.md) · [Incident template](12-operations/incidents/TEMPLATE.md) |
| 13 | Setup | [Local setup](13-setup/local-setup.md) · [Model servers: mlx-lm, Ollama, LM Studio, llama.cpp, vLLM](13-setup/model-servers.md) |
| 14 | Production | [Promotion to production](14-production/promotion-to-production.md) · [Environments & CI/CD](14-production/environments-and-cicd.md) |
| 15 | Fine-tuning | [Report model LoRA](15-finetuning/finetuning.md) |
| 16 | Frontend | [Angular app](16-frontend/frontend.md) |
| 17 | API | [API reference](17-api/api-reference.md) |

## Repository map

```
src/adintel/
  agents/        the nine agents (ingestion, data_quality, orchestrator, anomaly, analyst, optimizer, report, guardrail, chat)
  graph/         LangGraph supervisor graph, harness node wrapper, finalize, run engine, progress events
  harness/       budget guard, kill switches, idempotency, checkpoints, timeouts, degradation matrix, admission
  llm/           validation wrapper (gateway), providers (mlx/OpenAI-compatible, Bedrock, mock), model & prompt registries, semantic cache
  rag/           chunking, embeddings, BM25, hybrid retriever, reranker, indexer, narratives, numeric grounding
  approvals/     brand constraints, approval authority matrix, approval service (7 checks, signing)
  executor/      the only component with write credentials — no model access; reconciliation
  storage/       tenant-scoped repository, memory + MongoDB backends, collection catalogue
  security/      PII, fencing, auth/JWT, process-scoped secrets
  audit/         hash-chained audit log
  observability/ logging, metrics, tracing, Langfuse, alerts
  memory/        conversational and procedural memory
  connectors/    5 ad platforms (synthetic worlds + live slot), normaliser
  sandbox/       Analyst code policy and runners
  api/ workers/ scheduler/ evals/ seed/ cli.py
prompts/         versioned, hash-pinned agent prompts
config/          model registry (models.yaml)
evals/           golden datasets, thresholds, baseline, reports
frontend/        Angular 18 app
deploy/          Docker Compose, Prometheus, Alertmanager, Grafana
infra/terraform/ AWS production
finetune/        LoRA pipeline for the Report model
scripts/         mlx-lm serving, prompt pinning
tests/           unit, api, e2e, chaos, integration, load
```
