#!/usr/bin/env bash
# Train a Report adapter for one tone cluster with mlx_lm.lora, then sign it.
#   finetune/train.sh warm            # expects finetune/data/warm/{train,valid,test}.jsonl
set -euo pipefail
TONE="${1:?tone cluster, e.g. warm}"
VERSION="${2:-v1}"
DATA="finetune/data/${TONE}"
OUT="finetune/adapters/report-${TONE}-${VERSION}"
N=$(wc -l < "${DATA}/train.jsonl")
ITERS=$(( (3 * N + 3) / 4 ))            # 3 epochs at effective batch 4
ITERS=$(( ITERS < 30 ? 30 : ITERS ))
echo "training ${OUT}: ${N} examples → ${ITERS} iterations"
mlx_lm.lora --config finetune/lora_config.yaml --data "${DATA}" --adapter-path "${OUT}" --iters "${ITERS}"
mlx_lm.lora --config finetune/lora_config.yaml --data "${DATA}" --adapter-path "${OUT}" --test --train false
python finetune/sign_adapter.py sign "${OUT}"
echo
echo "Register it: config/models.yaml → tiers.report.tone_adapters.${TONE} = { path: ${OUT}, sha256: <above> }"
echo "Next: evaluate before promotion (base vs adapter vs frontier):"
echo "  MLX_ADAPTER=${OUT} scripts/mlx/serve_small.sh mlx-community/Qwen3.6-35B-A3B-4bit 8082"
echo "  python finetune/evaluate_adapter.py --adapter-url http://127.0.0.1:8082/v1"
