#!/usr/bin/env bash
# Small / report / safety tier: Qwen3.6-35B-A3B-4bit (mixture-of-experts, ~3B active params → fast).
# Usage: scripts/mlx/serve_small.sh [model] [port]
#   MLX_ADAPTER=finetune/adapters/report-warm-v1 scripts/mlx/serve_small.sh   # serve with the report LoRA adapter
set -euo pipefail
MODEL="${1:-${ADINTEL_MODEL_SMALL_ID:-mlx-community/Qwen3.6-35B-A3B-4bit}}"
PORT="${2:-8080}"
ARGS=(--model "$MODEL" --host 127.0.0.1 --port "$PORT" --log-level INFO)
if [[ -n "${MLX_ADAPTER:-}" ]]; then
  echo "verifying adapter hash before serving: $MLX_ADAPTER"
  python finetune/sign_adapter.py verify "$MLX_ADAPTER"
  ARGS+=(--adapter-path "$MLX_ADAPTER")
fi
# Extra flags for your mlx-lm version (see `mlx_lm.server --help`), e.g. MLX_EXTRA_ARGS="--prompt-cache-size 8"
# shellcheck disable=SC2086
exec mlx_lm.server "${ARGS[@]}" ${MLX_EXTRA_ARGS:-}
