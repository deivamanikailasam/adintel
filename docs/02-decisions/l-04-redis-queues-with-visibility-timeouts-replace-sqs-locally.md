# L-04: Redis queues with visibility timeouts replace SQS locally

- **Status:** accepted
- **Owner:** Tech lead
- **Date:** 2026-10-12

## Context

The worker needs at-least-once delivery, a visibility timeout matching the run budget (900 s), DLQs and a FIFO executions queue.

## Decision

A Queue interface with Redis (list + in-flight sorted set + DLQ), in-memory and SQS implementations.

## Consequences

Redis is not durable by default; enable AOF in the compose file. Idempotency keys make redelivery harmless.

## Alternatives rejected

Celery (heavier, its own semantics); Mongo-backed queue (polling).

## Revisit when

Throughput or durability requirements exceed a single Redis.
