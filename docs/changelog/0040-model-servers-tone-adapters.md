# 0040 — Any local model server, and a writing style per brand voice

**In one sentence:** AdIntel now runs on Ollama, LM Studio, llama.cpp or vLLM as well as mlx-lm by changing
one setting, and each brand's reports can be written by a fine-tuned adapter for its own tone of voice.

## What changed

- `config/model-profiles.yaml` + `ADINTEL_MODEL_PROFILE=mlx|ollama|lmstudio|llamacpp|vllm` — per-tier URL and
  pinned model id per server; `small` also feeds the report and safety tiers; env overrides still win;
  unknown profiles and floating tags are refused. `adintel models` shows the active profile.
- `tiers.report.tone_adapters` in `config/models.yaml` — each entry becomes a tier `report:<tone>` with its
  own SHA-256 pin (mismatch refuses startup), fallback to frontier, and per-request adapter selection
  (`"adapters"` field for mlx-lm; `model_id`/`base_url`/`extra_body` for vLLM, llama.cpp, Ollama).
- Report agent: picks the brand's tone tier (`ModelRegistry.report_tier`), records the tier and adapter hash
  on the report; degradation logic unchanged.
- Docs: new `docs/13-setup/model-servers.md` (setup, trade-offs, "changing server is a model change",
  per-tone adapters by server); local setup, model strategy, `.env.example`, `finetune/train.sh` hint.
- Tests: `tests/unit/test_model_profiles.py` — every profile loads with pinned ids and a fail-closed safety
  tier, precedence, refusals, tone tier creation, tamper refusal, and a warm brand's report written by the
  warm adapter.

## Why it matters (layman's terms)

Not everyone has a Mac with mlx: now the same system runs on whichever local "engine" you have, and the
rules about pinning exact model versions apply to all of them. And instead of one writer for every client,
a coffee shop and a luxury brand can each get a writer trained on their own voice — with a fingerprint
check so nobody can swap in a different writer unnoticed.
