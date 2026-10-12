# D-10: Fargate over Lambda (production)

- **Status:** accepted
- **Owner:** Tech lead
- **Date:** 2026-10-12

## Context

Runs can exceed Lambda's 15-minute ceiling under retries, cold starts hurt chat and an 8 GB pandas working set is awkward on Lambda. EKS adds operational overhead this scale doesn't justify.

## Decision

ECS Fargate services: api-service, agent-worker, executor-service. Locally these are three processes.

## Consequences

Pay for idle capacity; mitigated by autoscaling on queue depth.

## Alternatives rejected

Lambda; EKS.

## Revisit when

Runs become reliably short and small.
