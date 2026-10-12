# Model strategy (local mlx-lm edition)

> **Rule:** use the cheapest model that reliably does the job, and prove "reliably" with an eval,
> not intuition.

## Your two local models

| Tier | Model | Served by | Port | Why this model for this tier |
|------|-------|-----------|------|------------------------------|
| **Frontier** (judgement) | `Qwen3.8-27B-8bit` | `mlx_lm.server` | 8081 | Dense 27B at 8-bit keeps nearly full precision: the strongest reasoning you have. Used where being wrong is expensive. |
| **Small** (volume) | `Qwen3.6-35B-A3B-4bit` | `mlx_lm.server` | 8080 | Mixture-of-experts with ~3B active parameters per token: fast and cheap per call, good at narrow, checkable tasks. |
| **Report** (fine-tuned) | `Qwen3.6-35B-A3B-4bit` + LoRA adapter | `mlx_lm.server --adapter-path` | 8080 (or 8082) | Narrow, high-volume, style-dependent task with labelled examples. |
| **Safety classifier** | `Qwen3.6-35B-A3B-4bit` with a Llama-Guard-style taxonomy prompt | same | 8080 | Local replacement for Llama Guard 3; deterministic checks run first. |
| **Non-LLM ML** | STL, Isolation Forest, BGE embeddings, BGE reranker | in-process | — | Anomaly detection and retrieval must be deterministic. |

Both tiers are configured in `config/models.yaml`; the model IDs, base URLs, temperatures, token
budgets and notional prices are all there, pinned. If your weights live under different names
(e.g. `mlx-community/Qwen3.6-35B-A3B-4bit` or a local path), change them only in that file or via
`ADINTEL_MODEL_SMALL_ID` / `ADINTEL_MODEL_FRONTIER_ID`.

## Which agent uses which tier

| Agent | Tier | Temperature | Why |
|-------|------|-------------|-----|
| Orchestrator | frontier | 0.0 | Routing decisions must not vary |
| Analyst | frontier | 0.0 | Multi-step reasoning, high cost of being wrong |
| Optimizer | frontier | 0.0 | Money decisions must not vary |
| Ingestion mapping proposals | small | 0.0 | Narrow, checkable |
| Data-quality summary | small | 0.0 | Phrasing only; the verdict is code |
| Report | report (small + adapter) | 0.2 | Greedy decoding makes prose stilted; the number check makes light sampling safe |
| Chat — simple lookups | small | 0.3 | Low stakes, RAG-grounded |
| Chat — complex | frontier | 0.3 | Ambiguous, multi-hop |
| Guardrail classifier | small | 0.0 | A safety verdict must be reproducible |
| LLM-as-judge (evals) | frontier | 0.0, 3 runs, median | Variance band, not a single sample |

## Fallback chain

Every call goes through the validation wrapper (`llm/gateway.py`), which walks a fallback chain when
a model is down, times out or keeps failing validation:

- frontier → small (the run is marked `degraded: frontier_unavailable`; Analyst and Optimizer are
  skipped and the small model writes a data summary — see the degradation matrix)
- report → frontier (`degraded: report_fallback_frontier`)
- guardrail classifier → **no fallback: fail closed**

## Qwen3 "thinking" output

Qwen3-family models may emit `<think>…</think>` reasoning blocks. The gateway always strips them
before parsing, and by default appends Qwen's `/no_think` soft switch to system prompts for
structured calls (`ADINTEL_QWEN_NO_THINK=true`), which is faster and keeps JSON clean. Set it to
`false` for the Analyst if your evals show thinking improves root-cause accuracy.

## Version pinning

Every model reference is pinned to an exact model ID and (for adapters) a SHA-256 of the adapter
weights. Startup refuses `latest`, empty IDs or an adapter whose hash doesn't match. A report written
in March must be reproducible in September.

## Why fine-tune, and only the Report agent

Fine-tuning pays when a task is **narrow, high-volume, style-dependent and has labelled examples**.
Report writing scores 4/4. Method: LoRA on the 4-bit base (QLoRA) via `mlx_lm.lora` — rank 16,
scale 2.0 (alpha 32), dropout 0.05, 3 epochs, lr 2e-4, sequence length 4,096, loss masked on the
prompt. One base model with swappable adapters per tone cluster instead of N full models. See
`docs/15-finetuning/finetuning.md`.

## Promotion to production

In production the same tiers map to Bedrock (frontier), SageMaker/Bedrock (small), SageMaker with
LoRA adapters (report) and Llama Guard 3 (safety). Only `config/models.yaml` and the provider setting
change. Evals must be re-run against the production models before promotion — see
`docs/14-production/promotion-to-production.md`.
