# 0025 — Serving your two models with mlx-lm, and the local setup guide

**In one sentence:** two scripts start your Qwen models as local AI servers, and a step-by-step guide
takes you from a clean Mac to a fully running AdIntel.

## What changed

- `scripts/mlx/serve_small.sh` — **Qwen3.6-35B-A3B-4bit** on port 8080 (small, report and safety tiers);
  `MLX_ADAPTER=...` serves a signed report adapter after verifying its fingerprint.
- `scripts/mlx/serve_frontier.sh` — **Qwen3.8-27B-8bit** on port 8081 (frontier and judge tiers).
- `scripts/mlx/check.sh` — confirms both servers answer, shows which model each serves, and runs a JSON
  smoke test. `make mlx-small`, `make mlx-frontier` wrap the scripts.
- `docs/13-setup/local-setup.md` — hardware/memory needs (≥ 64 GB for both models, or a one-model mode),
  install, the 30-second mock demo, serving the models, `make up`, switching to Mongo/Redis/real
  embeddings, running the four services and the Angular app, seeded users, a guided product walkthrough,
  evaluating your models, everyday commands and troubleshooting.

## Why it matters (layman's terms)

Everything runs on your own computer: no data leaves it, and the same configuration switches cleanly to
cloud models later.
