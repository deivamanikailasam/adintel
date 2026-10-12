# D-04: Frontier tier for Orchestrator, Analyst and Optimizer

- **Status:** accepted
- **Owner:** Tech lead
- **Date:** 2026-10-12

## Context

These three share ambiguous input, multi-step reasoning and a high cost of being wrong. A slightly worse judgement from a small model is a wrong financial recommendation with a client's name on it. Volume is low (single-digit calls per brand per day).

## Decision

Use the frontier tier (locally Qwen3.8-27B-8bit; Bedrock Claude Sonnet-class in production) for these three agents at temperature 0. Everything else uses the small tier or no model.

## Consequences

Frontier is ~15% of calls and ~70% of model cost; affordable exactly where it matters.

## Alternatives rejected

Frontier by default (15–20× cost where evals show no difference); small model everywhere (unacceptable error rate on money decisions).

## Revisit when

Quarterly, as small models improve — re-run the agent evals with the small tier.
