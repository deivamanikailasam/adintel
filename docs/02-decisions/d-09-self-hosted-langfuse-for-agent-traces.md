# D-09: Self-hosted Langfuse for agent traces

- **Status:** accepted
- **Owner:** Tech lead
- **Date:** 2026-10-12

## Context

Traces contain client ad data. A hosted tracing product is a harder conversation with clients' security teams.

## Decision

Langfuse self-hosted (Docker locally, inside the VPC in production), fed through its public ingestion API, optional and non-blocking.

## Consequences

One more service to run; tracing failure never fails a run.

## Alternatives rejected

LangSmith (hosted by default).

## Revisit when

A compliant hosted option becomes acceptable.
