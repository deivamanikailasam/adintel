#!/usr/bin/env bash
# Frontier / judgement tier: Qwen3.8-27B-8bit (dense 27B at 8-bit → best reasoning, slower).
# Usage: scripts/mlx/serve_frontier.sh [model] [port]
set -euo pipefail
MODEL="${1:-${ADINTEL_MODEL_FRONTIER_ID:-mlx-community/Qwen3.8-27B-8bit}}"
PORT="${2:-8081}"
# shellcheck disable=SC2086
exec mlx_lm.server --model "$MODEL" --host 127.0.0.1 --port "$PORT" --log-level INFO ${MLX_EXTRA_ARGS:-}
