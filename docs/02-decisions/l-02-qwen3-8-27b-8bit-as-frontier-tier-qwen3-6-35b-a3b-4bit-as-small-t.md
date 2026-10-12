# L-02: Qwen3.8-27B-8bit as frontier tier, Qwen3.6-35B-A3B-4bit as small tier

- **Status:** accepted
- **Owner:** Tech lead
- **Date:** 2026-10-12

## Context

Two local models are available. The dense 27B at 8-bit has more active parameters per token and less quantisation loss; the 35B MoE has ~3B active parameters per token, so it is several times faster.

## Decision

Frontier = dense 27B (judgement, low volume). Small = MoE A3B (volume, latency-sensitive chat lookups, report writing, safety classification).

## Consequences

The 27B is the slow model; chat routes ~half of queries to the small model to protect first-token latency.

## Alternatives rejected

Swapping the roles (faster judgement, weaker reasoning on money decisions).

## Revisit when

Agent evals show the small model within the tolerance band on Orchestrator/Analyst/Optimizer golden sets.
