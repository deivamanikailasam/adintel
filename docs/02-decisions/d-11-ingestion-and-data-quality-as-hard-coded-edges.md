# D-11: Ingestion and Data Quality as hard-coded edges

- **Status:** accepted
- **Owner:** Tech lead
- **Date:** 2026-10-12

## Context

There is exactly one correct first action. Paying a model to discover it adds cost and non-determinism.

## Decision

START → Ingestion → Data Quality is fixed; a conditional edge then continues to the Orchestrator or aborts to Finalize.

## Consequences

None significant.

## Alternatives rejected

Letting the Orchestrator choose the first step.

## Revisit when

Ingestion strategy becomes genuinely variable.
