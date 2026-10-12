# Model servers: mlx-lm and the alternatives

AdIntel talks to models through one OpenAI-compatible client (`llm/providers/openai_compat.py`), so any
server that speaks `/v1/chat/completions` works. Pick one with a single setting:

```bash
ADINTEL_MODEL_PROFILE=mlx        # default: mlx_lm.server on :8080 (small) and :8081 (frontier)
ADINTEL_MODEL_PROFILE=ollama     # Ollama on :11434
ADINTEL_MODEL_PROFILE=lmstudio   # LM Studio on :1234
ADINTEL_MODEL_PROFILE=llamacpp   # two llama-server processes on :8080 / :8081
ADINTEL_MODEL_PROFILE=vllm       # vLLM on :8001 / :8002 (Linux + NVIDIA)
```

Profiles live in `config/model-profiles.yaml`. Precedence: `config/models.yaml` → profile → env overrides
(`ADINTEL_MODEL_SMALL_ID`, `ADINTEL_MODEL_FRONTIER_BASE_URL`, …). Every model id must be **pinned**: use the
exact tag or file name your server lists; `latest` is refused at startup. Then check the wiring:

```bash
.venv/bin/adintel models     # each tier: model id, URL, reachable?, what the server reports it serves
```

| Server | Best for | Start | Notes |
|--------|----------|-------|-------|
| **mlx-lm** (default) | Apple Silicon, best tokens/s and memory use | `make mlx-small`, `make mlx-frontier` | LoRA adapters trained with `mlx_lm.lora` load natively |
| **Ollama** | Simplest install, one server for both models | `ollama serve`; `ollama pull qwen3.6:35b-a3b-q4_K_M qwen3.8:27b-q8_0` | Set `OLLAMA_CONTEXT_LENGTH=32768` (its default context is small); keep `OLLAMA_MAX_LOADED_MODELS=2` |
| **LM Studio** | GUI, model browser, Windows/Mac | Developer tab → Start server; load both models | Model ids look like `qwen3.6-35b-a3b@q4_k_m` — copy them from `lms ls` |
| **llama.cpp** | Any OS / CPU / CUDA / Vulkan; GGUF files | `llama-server -m <file>.gguf --port 8080 -c 32768 --jinja` (and 8081) | `--jinja` is needed for Qwen's chat template |
| **vLLM** | Linux + NVIDIA, highest throughput, closest to production serving | `vllm serve Qwen/Qwen3.6-35B-A3B-AWQ --port 8001 --max-model-len 32768` (and 8002) | Port 8000 is the AdIntel API, hence 8001/8002 |

**One model only** (smaller machines): point both tiers at the same server/model with
`ADINTEL_MODEL_FRONTIER_BASE_URL` and `ADINTEL_MODEL_FRONTIER_ID` equal to the small tier. The fallback
chain then has nowhere to go, which `adintel models` and the degradation banner make visible.

## Changing server is a model change

Different servers apply different chat templates, sampling defaults and quantisations, so outputs differ
even for "the same" model. Treat a switch like any model change (governance: model registry):

1. `make evals-mlx` against the new profile (the suite runs on whatever the tiers point at);
2. `make gate` — no category may regress and the safety/money gates stay at 100%;
3. record the result and bump `registry_version` in `config/models.yaml` if you make it the default.

## Per-tone report adapters

Each brand has a `profile.tone_cluster` (`warm`, `premium`, `neutral`, …). Train one adapter per cluster with
`finetune/train.sh <tone>` (which signs it), then register it under `tiers.report.tone_adapters` in
`config/models.yaml`:

```yaml
tone_adapters:
  warm:    { path: finetune/adapters/report-warm-v3, sha256: "<from finetune/sign_adapter.py>" }
```

Each entry becomes its own tier, `report:<tone>`, with its own pinned SHA-256 (startup refuses a mismatch)
and the same fallback to the frontier tier. Brands whose tone has no adapter use the `report` tier. The
report records which tier and adapter hash wrote it (`model_tier`, `adapter_sha256`), so an audit can tell
exactly which weights produced a client's report.

How the adapter is selected per request, by server:

| Server | Configuration |
|--------|---------------|
| mlx-lm | default: the request carries `"adapters": "<path>"`. If your mlx-lm version does not switch adapters per request, serve each tone separately (`MLX_ADAPTER=<path> scripts/mlx/serve_small.sh <model> 8083`) and set `base_url` on the entry |
| vLLM | `vllm serve <base> --enable-lora --lora-modules report-warm=<path>`; set `model_id: report-warm`, `extra_body: {}` |
| llama.cpp | convert the adapter to GGUF and start a server per tone with `--lora`; set `base_url`, `extra_body: {}` |
| Ollama | a Modelfile with `ADAPTER <path>` per tone (`ollama create report-warm`); set `model_id: report-warm`, `extra_body: {}` |
