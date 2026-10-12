# AWS production ↔ local implementation mapping

AdIntel was designed for AWS. This repository runs the **same architecture** on one machine, swapping
each managed service for a local equivalent behind an interface. The interface is what makes
promotion to production a configuration change rather than a rewrite.

> **In plain words:** every AWS service is a socket. Locally we plug in a household appliance;
> in production we plug in the industrial one. The wiring (our code) does not change.

| Concern | AWS production (design) | Local (this repo) | Interface in code | Switch |
|---------|-------------------------|-------------------|-------------------|--------|
| Frontier model (Orchestrator, Analyst, Optimizer, complex chat, judge) | Claude Sonnet-class on Amazon Bedrock | **Qwen3.8-27B-8bit** on `mlx_lm.server` :8081 | `adintel.llm.providers.LLMProvider` | `ADINTEL_LLM_PROVIDER=openai_compat` / `bedrock` |
| Small model (field mapping, DQ summary, chat lookups) | Llama 3.3 8B on Bedrock/SageMaker | **Qwen3.6-35B-A3B-4bit** on `mlx_lm.server` :8080 (MoE, ~3B active → fast) | same | same |
| Fine-tuned report model | Llama 3.3 8B + QLoRA adapters on SageMaker | Qwen3.6-35B-A3B-4bit + **mlx-lm LoRA adapter** (`--adapter-path`) | same + adapter hash pinning | `config/models.yaml` |
| Safety classifier | Llama Guard 3 + Bedrock Guardrails | Deterministic checks + small model with a Llama-Guard-style taxonomy prompt (fails closed) | `adintel.agents.guardrail` | `config/models.yaml` |
| Embeddings | voyage-3-class, 1,024 dims | `fastembed` BGE (`BAAI/bge-small-en-v1.5`, 384 dims) or a deterministic hashing embedder (tests) | `adintel.rag.embeddings.Embedder` | `ADINTEL_EMBEDDER` |
| Reranker | Self-hosted BGE cross-encoder (SageMaker) | `fastembed` `BAAI/bge-reranker-base` or lexical reranker (tests) | `adintel.rag.rerank.Reranker` | `ADINTEL_RERANKER` |
| Operational DB + vector search | MongoDB Atlas M30 + Atlas Vector Search | **MongoDB Atlas Local** (`mongodb/mongodb-atlas-local` image; supports `$vectorSearch`) or in-memory backend | `adintel.storage.Database` | `ADINTEL_STORAGE=mongo` / `memory` |
| Time series | Mongo time-series collection | Same (Atlas Local) | `metrics_daily` | — |
| Run queue | SQS `agent-runs` (visibility 900 s) + DLQ | Redis list + in-flight sorted set with visibility timeout + DLQ, or in-memory | `adintel.queueing.Queue` | `ADINTEL_QUEUE=redis` / `memory` / `sqs` |
| Execution queue | SQS `executions` **FIFO** + DLQ | Redis FIFO queue (single consumer group) | same | same |
| Scheduler | EventBridge Scheduler, one schedule per brand in its timezone, 90-min stagger | APScheduler, one job per brand in its timezone, same stagger | `adintel.scheduler` | — |
| Secrets | Secrets Manager, per tenant & platform, 90-day rotation; readable only by ingestion/executor roles | File-based secret store under `secrets/` with **per-process scope** (`read` vs `write` credentials) | `adintel.security.secrets.SecretStore` | `ADINTEL_SECRETS=file` / `aws` |
| Identity | Cognito user pool (JWT) | Local JWT issuer (`/auth/dev-login`, disabled outside `local`) | `adintel.security.auth` | `ADINTEL_AUTH_*` |
| Tracing & evals | Self-hosted Langfuse in the VPC | Langfuse (Docker) via its public ingestion API — optional | `adintel.observability.langfuse` | `ADINTEL_LANGFUSE_*` |
| Distributed traces | X-Ray + OpenTelemetry | OpenTelemetry → Jaeger (Docker) | `adintel.observability.tracing` | `OTEL_EXPORTER_OTLP_ENDPOINT` |
| Logs | CloudWatch Logs, structured JSON | Structured JSON to stdout (`trace_id`, `run_id`, `tenant_id` on every line) | `adintel.observability.logging` | — |
| Metrics & dashboards | CloudWatch + EMF + Grafana | Prometheus + Grafana (Docker), dashboards in `deploy/grafana/` | `adintel.observability.metrics` | — |
| Alerting | CloudWatch Alarms → PagerDuty/Slack | Prometheus alert rules → Alertmanager → webhook/Slack; `notifications` collection | `deploy/prometheus/alerts.yml` | — |
| Analyst code sandbox | Network-isolated container, cgroup limits | Subprocess with AST allow-list, rlimits, timeout; optional Docker `--network none` mode | `adintel.sandbox` | `ADINTEL_SANDBOX=subprocess` / `docker` |
| Compute | ECS Fargate: api, agent-worker, executor | Local processes or Docker Compose services | — | — |
| Static frontend | S3 + CloudFront + WAF | Angular dev server / `ng build` served by any static server | `frontend/` | — |
| IaC | Terraform | Docker Compose locally; Terraform skeleton in `infra/terraform/` | — | — |
| Ad platforms | Real Google/Meta/TikTok/LinkedIn/Amazon APIs | Deterministic synthetic connectors with the same raw field shapes, including the three canonical scenarios (cost spike, clean, broken tracking) | `adintel.connectors.PlatformConnector` | `ADINTEL_CONNECTORS=synthetic` / `live` |

## What is deliberately *not* different locally

These properties hold in every environment — they are code, not infrastructure:

1. Tenant isolation in the data-access layer (`TenantScopedRepo`).
2. The approval gate and its seven server-side checks.
3. Executor has no model access.
4. Budget guard, kill switches, idempotency, checkpointing.
5. The validation wrapper around every model call.
6. The hash-chained audit log.
7. Numeric grounding of every figure in a report.

## Cost accounting with free local models

Local inference has no per-token bill, but the budget guard and cost dashboards still need a number.
AdIntel charges every call at a **notional price** (`config/models.yaml → pricing`) that mirrors the
production model it stands in for. That keeps the `$2.00` per-run cap, per-tenant daily caps and the
"cost within ±15% of baseline" promotion gate meaningful before you ever pay a cloud bill.
