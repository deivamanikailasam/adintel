# Architecture decision records

Every significant decision is logged with its reason **and the condition that would justify revisiting it**, so the next engineer doesn't tear something out without knowing why it's there.

`D-xx` decisions come from the original AdIntel design. `L-xx` decisions are specific to this local-first implementation.

| ID | Decision | Status | Revisit when |
|----|----------|--------|--------------|
| [D-01](d-01-agentic-langgraph-over-a-fixed-workflow.md) | Agentic (LangGraph) over a fixed workflow | accepted | Six months of data show more than 90% of runs take one identical path — then collapse to a workflow. |
| [D-02](d-02-supervisor-pattern-no-agent-to-agent-calls.md) | Supervisor pattern, no agent-to-agent calls | accepted | Parallelism becomes the bottleneck. |
| [D-03](d-03-mongodb-for-operational-and-vector-data.md) | MongoDB for operational and vector data | accepted | Corpus exceeds ~10M vectors and Search Nodes can't absorb the contention. |
| [D-04](d-04-frontier-tier-for-orchestrator-analyst-and-optimizer.md) | Frontier tier for Orchestrator, Analyst and Optimizer | accepted | Quarterly, as small models improve — re-run the agent evals with the small tier. |
| [D-05](d-05-fine-tuned-small-model-for-reports.md) | Fine-tuned small model for reports | accepted | Quarterly, or on a base-model upgrade. |
| [D-06](d-06-no-llm-in-anomaly-detection.md) | No LLM in anomaly detection | accepted | Not expected to change. |
| [D-07](d-07-l2-autonomy-a-human-approves-all-execution.md) | L2 autonomy: a human approves all execution | accepted | Only with 12 months of calibration data and explicit client opt-in. |
| [D-08](d-08-shared-collections-with-a-tenant-discriminator.md) | Shared collections with a tenant discriminator | accepted | A client contractually requires physical isolation. |
| [D-09](d-09-self-hosted-langfuse-for-agent-traces.md) | Self-hosted Langfuse for agent traces | accepted | A compliant hosted option becomes acceptable. |
| [D-10](d-10-fargate-over-lambda-production.md) | Fargate over Lambda (production) | accepted | Runs become reliably short and small. |
| [D-11](d-11-ingestion-and-data-quality-as-hard-coded-edges.md) | Ingestion and Data Quality as hard-coded edges | accepted | Ingestion strategy becomes genuinely variable. |
| [D-12](d-12-report-temperature-0-2-not-0-0.md) | Report temperature 0.2, not 0.0 | accepted | Grounding failures correlate with temperature. |
| [L-01](l-01-one-openai-compatible-provider-for-local-models.md) | One OpenAI-compatible provider for local models | accepted | A provider needs features the OpenAI-compatible shape can't express. |
| [L-02](l-02-qwen3-8-27b-8bit-as-frontier-tier-qwen3-6-35b-a3b-4bit-as-small-t.md) | Qwen3.8-27B-8bit as frontier tier, Qwen3.6-35B-A3B-4bit as small tier | accepted | Agent evals show the small model within the tolerance band on Orchestrator/Analyst/Optimizer golden sets. |
| [L-03](l-03-mongodb-atlas-local-for-development.md) | MongoDB Atlas Local for development | accepted | Atlas Local diverges from Atlas behaviour. |
| [L-04](l-04-redis-queues-with-visibility-timeouts-replace-sqs-locally.md) | Redis queues with visibility timeouts replace SQS locally | accepted | Throughput or durability requirements exceed a single Redis. |
| [L-05](l-05-stl-robust-band-instead-of-prophet.md) | STL + robust band instead of Prophet | accepted | Anomaly F1 on the golden set falls below 0.90 or false positives exceed 5%. |
| [L-06](l-06-harness-owned-checkpointing-of-runstate.md) | Harness-owned checkpointing of RunState | accepted | We need mid-graph human interrupts. |
| [L-07](l-07-notional-pricing-for-free-local-models.md) | Notional pricing for free local models | accepted | Never — this is how cost controls stay tested. |
| [L-08](l-08-local-safety-classifier-instead-of-llama-guard-3.md) | Local safety classifier instead of Llama Guard 3 | accepted | A local Llama Guard / ShieldGemma becomes available — swap it in via config/models.yaml. |
| [L-09](l-09-fastembed-onnx-for-embeddings-and-reranking.md) | fastembed (ONNX) for embeddings and reranking | accepted | Retrieval evals regress against production embeddings. |
| [L-10](l-10-synthetic-ad-platform-connectors-with-real-field-shapes.md) | Synthetic ad-platform connectors with real field shapes | accepted | Nightly contract tests against real read-only sandbox accounts are wired up in production. |
| [L-11](l-11-signed-approval-records-between-api-service-and-executor.md) | Signed approval records between api-service and executor | accepted | Moving to KMS asymmetric signing in production (recommended). |
| [L-12](l-12-synchronous-agents-async-edges.md) | Synchronous agents, async edges | accepted | Interactive agent paths become latency-bound on I/O fan-out. |
| [L-13](l-13-forward-only-data-migrations.md) | Forward-only data migrations with expand/contract | accepted | A single migration takes > 10 min on production data. |
| [L-14](l-14-proprietary-licence-and-dependency-policy.md) | Proprietary licence, enforced dependency-licence policy | accepted | Strategy moves to open core, or a customer requires an OSS licence. |
| [L-15](l-15-model-provider-data-terms.md) | Model providers must not train on or retain customer data — enforced in code | accepted | A customer opts into a provider with retention, or regulation requires provider logging. |

## How to add a decision

Copy [template.md](template.md), give it the next free ID, fill in every section — **especially "Revisit when"** — and link it here. A decision without a revisit trigger is an opinion.

