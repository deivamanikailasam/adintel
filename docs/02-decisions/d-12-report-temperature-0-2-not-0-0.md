# D-12: Report temperature 0.2, not 0.0

- **Status:** accepted
- **Owner:** Tech lead
- **Date:** 2026-10-12

## Context

Greedy decoding makes small-model prose stilted.

## Decision

Temperature 0.2 for the Report agent only; numeric grounding makes light sampling safe because every figure is checked against the database.

## Consequences

Wording varies between re-runs; reproducibility comes from the archived prompt/response, not identical regeneration.

## Alternatives rejected

Temperature 0.0.

## Revisit when

Grounding failures correlate with temperature.
