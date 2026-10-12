# L-06: Harness-owned checkpointing of RunState

- **Status:** accepted
- **Owner:** Tech lead
- **Date:** 2026-10-12

## Context

We need checkpoints that are (a) the typed RunState, (b) content-hashed so corruption is detected, (c) stored in the same tenant-scoped database and (d) resumable at the Orchestrator.

## Decision

The engine wraps each node and writes a hashed RunState snapshot to run_checkpoints after every step; resume enters the graph at the Orchestrator.

## Consequences

We don't use LangGraph's interrupt/time-travel features; human approval happens after the run, not mid-graph, so they aren't needed.

## Alternatives rejected

LangGraph's MongoDBSaver (opaque blobs, no content hash, separate retention).

## Revisit when

We need mid-graph human interrupts.
