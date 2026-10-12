# D-02: Supervisor pattern, no agent-to-agent calls

- **Status:** accepted
- **Owner:** Tech lead
- **Date:** 2026-10-12

## Context

A mesh where any agent can call any other is hard to debug, has unbounded cost (agents ping-pong) and gives no single place to enforce limits.

## Decision

Every specialist returns to the Orchestrator. The Orchestrator is the one place the budget guard, kill switches and no-repeat rules are enforced.

## Consequences

Slightly more hops than a mesh; independent agents can still be dispatched in parallel, so little parallelism is lost.

## Alternatives rejected

Agent mesh / handoffs between agents.

## Revisit when

Parallelism becomes the bottleneck.
