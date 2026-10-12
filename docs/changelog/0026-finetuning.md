# 0026 — Fine-tuning the Report model

**In one sentence:** you can now teach the fast model to write reports in a brand's voice using past
approved reports, then prove it's better before switching it on.

## What changed

- `finetune/prepare_dataset.py` — builds training data from **released, well-rated, grounded** reports
  for brands in one tone cluster (or seed data, to smoke-test the pipeline), in exactly the message shape
  the Report agent uses at inference; 85/7.5/7.5 split.
- `finetune/lora_config.yaml` + `finetune/train.sh` — LoRA on the 4-bit Qwen3.6-35B-A3B base with
  `mlx_lm.lora`: rank 16, alpha 32, dropout 0.05, 3 epochs, lr 2e-4, 4,096 tokens, loss masked on the prompt.
- `finetune/sign_adapter.py` — fingerprints and signs an adapter; the model registry refuses to start with
  an adapter whose fingerprint doesn't match the pinned one (the manifest file itself is excluded from the
  fingerprint).
- `finetune/evaluate_adapter.py` — base vs fine-tuned vs frontier: tone (judge), structure, grounding,
  latency p95, cost per report, plus a shuffled blind-test file for human raters.
- `docs/15-finetuning/finetuning.md`.

## Why it matters (layman's terms)

Prompting a model with a style guide costs tokens on every call and still drifts. A small style add-on
learned from the agency's own approved reports is consistent — and cheap to swap back if it's worse.
