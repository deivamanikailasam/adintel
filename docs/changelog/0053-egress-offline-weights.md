# 0053 — Nothing leaves the machine, and the model is the one we tested

**In one sentence:** AdIntel can now run genuinely air-gapped — it refuses to start if anything is
configured to talk to the outside world — and it can prove that the model files on disk are byte-for-byte
the ones that passed evaluation.

## What changed

- `security/egress.py` — `ADINTEL_OFFLINE` (only loopback, LAN, internal service names) and
  `ADINTEL_EGRESS_ALLOWLIST` (`host`, `host:port`, `*.suffix`). Checked at start-up for every configured
  endpoint (model tiers, OTEL, Langfuse, alert webhook, identity provider, S3/MinIO) and again when the model
  client or alert webhook connects. Offline also disables Hugging Face downloads and telemetry via env.
  `adintel egress-check` shows each endpoint's verdict.
- `llm/weights.py` — `adintel weights lock` records the SHA-256 of every base-model file (Hugging Face cache
  for mlx-lm/vLLM, or `--path model=file` for Ollama/llama.cpp/LM Studio); `adintel weights verify` fails on
  any mismatch, missing or extra file.
- Threat model T14 (exfiltration through a configured endpoint) and T15 (swapped weights); security
  controls table; local setup §8c "Run fully offline"; `.env.example`.
- Tests: `tests/unit/test_egress_weights.py`.

## Why it matters (layman's terms)

"It runs on your machine" is only a promise until something checks it. Now the system itself refuses any
address outside the building, and keeps a fingerprint of the exact model it was tested with — so a swapped
or corrupted model file is caught before it writes a single client report.
