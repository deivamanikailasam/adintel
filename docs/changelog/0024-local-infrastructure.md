# 0024 — Local infrastructure and the observability stack

**In one sentence:** one command (`make up`) now starts every supporting service AdIntel needs on your
machine — the database with vector search, queues, tracing, metrics, alerting and dashboards.

## What changed

- `Dockerfile` — one image for all four services; the command and `ADINTEL_PROCESS_ROLE` pick the role.
  Models are not in the image (they run on the host with mlx-lm, because Docker on macOS can't use the GPU).
- `deploy/docker-compose.yml` — MongoDB **Atlas Local** (real `$vectorSearch`), Redis with durable AOF,
  Langfuse (self-hosted agent traces), Jaeger (OpenTelemetry), Prometheus, Alertmanager, Grafana; plus an
  optional `app` profile running api/worker/executor/scheduler in containers. **Only the executor
  container mounts the write-credential secrets.** The worker gets 120 s to checkpoint on shutdown.
- `deploy/prometheus/alerts.yml` — P1–P4 alert rules (cross-tenant violation, audit-chain break,
  execution mismatch, guardrail down, frontier outage, step-limit loops, DLQ, cost spike, cache-hit drop,
  chat first-token SLO…). `deploy/alertmanager/alertmanager.yml` routes them by severity.
- `deploy/grafana/` — four provisioned dashboards: System, Agents & harness, Models & cost (notional),
  Quality & safety (approval rate, rejection reasons, guardrail blocks, isolation violations = 0).
- `deploy/sandbox/Dockerfile` — the network-isolated image for `ADINTEL_SANDBOX=docker`.
- `docs/09-observability/alerting.md`.

## Why it matters (layman's terms)

Running the real database, queue and monitoring locally means what you test on your laptop behaves like
production — including the alarms that should wake someone up.
