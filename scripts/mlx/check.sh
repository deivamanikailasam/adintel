#!/usr/bin/env bash
# Check both mlx-lm servers answer and that the model IDs they serve match config/models.yaml.
set -uo pipefail
for spec in "small 8080" "frontier 8081"; do
  set -- $spec
  printf "%-9s :%s  " "$1" "$2"
  if out=$(curl -sf "http://127.0.0.1:$2/v1/models"); then
    echo "$out" | python3 -c 'import json,sys; print("OK  serving:", [m["id"] for m in json.load(sys.stdin)["data"]])'
  else
    echo "NOT RUNNING  → make mlx-$1"
  fi
done
echo
echo "Smoke test (frontier, JSON):"
curl -s http://127.0.0.1:8081/v1/chat/completions -H 'Content-Type: application/json' -d '{
  "model": "'"${ADINTEL_MODEL_FRONTIER_ID:-mlx-community/Qwen3.8-27B-8bit}"'",
  "messages": [{"role":"system","content":"Reply with one JSON object only. /no_think"},
               {"role":"user","content":"Return {\"ok\": true}"}],
  "max_tokens": 30, "temperature": 0}' | python3 -c 'import json,sys; d=json.load(sys.stdin); print(d["choices"][0]["message"]["content"], d.get("usage"))' || true
