# 0006 — Observability foundation

**In one sentence:** we installed the dashboard lights, the flight recorder and the alarm bell before
building the engine, so every later piece reports how it is doing from day one.

## What changed

- `observability/context.py` + `logging.py` — every log line is JSON and carries the run, tenant and
  brand IDs automatically.
- `observability/metrics.py` — ~35 Prometheus metrics grouped by system, agent, model, quality and
  security (for example the recommendation approval rate and the cache hit rate).
- `observability/tracing.py` — OpenTelemetry spans; off by default, on when you point it at Jaeger.
- `observability/langfuse.py` — optional agent traces in a self-hosted Langfuse, sent in the
  background so tracing can never slow down or break a run.
- `observability/alerts.py` — P1–P4 alert routing. Cross-tenant access attempts are wired to a
  metric and a **P1 security page** automatically.
- `docs/09-observability/observability.md`.

## Why it matters (layman's terms)

AI systems rarely crash; they quietly get worse. The metrics here are chosen to catch that: if
account managers start rejecting more recommendations, or dismissing more anomalies, or if the cache
suddenly stops being hit (which means a bigger bill with no error message), it shows up on a graph
and can trigger an alert.
