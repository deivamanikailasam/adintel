# L-08: Local safety classifier instead of Llama Guard 3

- **Status:** accepted
- **Owner:** Tech lead
- **Date:** 2026-10-12

## Context

Llama Guard 3 is not one of the available local models. The guardrail must still fail closed and reach 100% recall on the adversarial set.

## Decision

Deterministic checks first (PII, other-tenant names, banned claims, injection markers, numeric re-check), then the small model with a Llama-Guard-style taxonomy prompt and a strict schema. No retries; timeout = block.

## Consequences

Classifier quality depends on the small model; the deterministic layer carries the hard guarantees.

## Alternatives rejected

No classifier (misses the semantic tail); frontier self-critique (~20× cost, weaker than a trained classifier).

## Revisit when

A local Llama Guard / ShieldGemma becomes available — swap it in via config/models.yaml.
