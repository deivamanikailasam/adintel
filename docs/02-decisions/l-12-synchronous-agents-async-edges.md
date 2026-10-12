# L-12: Synchronous agents, async edges

- **Status:** accepted
- **Owner:** Tech lead
- **Date:** 2026-10-12

## Context

LangGraph nodes, pandas, statsmodels and the sandbox are synchronous; the API needs streaming.

## Decision

Agents and the engine are synchronous and run in the worker; the FastAPI layer streams progress and chat tokens over SSE. Cancellation is cooperative (checked between tool steps) and every provider call has its own shorter timeout.

## Consequences

A timed-out thread can't be force-killed, which is why every inner call has its own timeout and the sandbox is a separate killable process.

## Alternatives rejected

Fully async agents (no benefit for CPU-bound steps, more complexity).

## Revisit when

Interactive agent paths become latency-bound on I/O fan-out.
