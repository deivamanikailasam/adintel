# Fine-tuning the Report model (LoRA on mlx-lm)

> **Fine-tune for *how it says things*, not what it knows or how well it thinks.** Only the Report agent is
> fine-tuned: narrow (findings JSON in, prose out), high-volume (700+ reports a quarter), style-dependent
> (brand voice), with labelled data (approved past reports).

## Recipe (`finetune/lora_config.yaml`)

| Setting | Value | Why |
|---------|-------|-----|
| Base | `mlx-community/Qwen3.6-35B-A3B-4bit` (the report tier's model) | One base, swappable adapters per tone cluster |
| Method | LoRA on the 4-bit base (QLoRA) | Tens of MB per adapter instead of a model copy per tone |
| Rank / alpha / dropout | 16 / 32 (mlx `scale` = 2.0) / 0.05 | Reference recipe |
| Epochs | 3 (`train.sh` computes iterations) | 2 underfits tone, 4+ overfits |
| Learning rate | 2e-4, cosine decay, 20 warm-up steps | |
| Sequence length | 4,096 | Findings + report fit |
| Loss | **masked on the prompt** (`mask_prompt: true`) | Learn the report, not the JSON |
| Data | 150–340 examples per tone cluster, 15% held out | Collected from approved reports |

## Steps

```bash
# 1. Build the dataset (production: approved, well-rated, grounded reports for brands in the cluster)
python finetune/prepare_dataset.py --tone warm --from-db
#    (smoke-test the pipeline only: --seed-data)

# 2. Train and sign (prints the SHA-256 to pin)
finetune/train.sh warm v1

# 3. Serve the adapter on a third port and compare base vs fine-tuned vs frontier
MLX_ADAPTER=finetune/adapters/report-warm-v1 scripts/mlx/serve_small.sh mlx-community/Qwen3.6-35B-A3B-4bit 8082
python finetune/evaluate_adapter.py --adapter-url http://127.0.0.1:8082/v1

# 4. Blind human preference test: give finetune/blind_test.jsonl to account managers (key kept separately)

# 5. Promote: pin path + sha256 (env or config/models.yaml), canary 5% for 48 h, then full
ADINTEL_REPORT_ADAPTER_PATH=finetune/adapters/report-warm-v1
ADINTEL_REPORT_ADAPTER_SHA256=<printed by sign_adapter.py>
```

The training examples use **exactly the message shape the Report agent sends at inference** (system prompt
+ schema + `/no_think`, then `<context>{findings}</context>`), so training and serving match.

## What to compare (reference results from the original deployment)

| Metric | Base 8B | Fine-tuned 8B | Frontier |
|--------|---------|---------------|----------|
| Tone match (1–5) | 2.8 | 4.3 | 4.4 |
| Structure compliance | 71% | 99% | 97% |
| Numeric grounding | 88% | 98% | 99% |
| Blind human preference | 18% | **47%** | 35% |
| Latency p95 | 5.1 s | 5.4 s | 16.8 s |
| Cost per report | $0.0019 | $0.0021 | $0.0340 |

The fine-tuned model won the blind test because account managers value consistency of voice over eloquence.
Your numbers on the Qwen base will differ — that is why `evaluate_adapter.py` exists.

## Governance

- Adapters are **signed** (`finetune/sign_adapter.py`) and **hash-pinned**; the model registry refuses to
  start with a mismatching adapter (threat T10).
- Retrain **quarterly**, or when frontier fallbacks exceed 8% over two weeks
  (`adintel_llm_fallbacks_total{from_tier="report"}`).
- Rollback is changing the adapter pointer — seconds.

## Memory guidance (Apple Silicon)

LoRA on the 35B-A3B 4-bit base needs roughly 40–55 GB of unified memory with `batch_size: 2`,
`grad_checkpoint: true`. On smaller machines reduce `num_layers` (e.g. 8) and `max_seq_length` (2,048).
