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
