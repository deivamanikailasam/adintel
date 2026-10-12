# D-05: Fine-tuned small model for reports

- **Status:** accepted
- **Owner:** Tech lead
- **Date:** 2026-10-12

## Context

Report writing is narrow (JSON findings in, prose out), high-volume (700+ a quarter), style-dependent (brand voice prompting costs ~800 tokens per call and still drifts) and has labelled data (50–100 approved past reports per tone cluster).

## Decision

LoRA adapters (QLoRA on the 4-bit base) per tone cluster, trained with mlx_lm.lora locally, served by mlx_lm.server --adapter-path; adapters are hash-pinned and signed.

## Consequences

Quarterly retraining; adapter registry and signature verification to operate.

## Alternatives rejected

Full fine-tuning (10–20× compute, a full model copy per tone); few-shot prompting (~1,500 tokens per call, drifts); frontier with a style guide (15–20× cost, 3–5× latency, evals within noise).

## Revisit when

Quarterly, or on a base-model upgrade.
