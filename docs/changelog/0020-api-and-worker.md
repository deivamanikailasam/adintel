# 0020 — API service and agent worker

**In one sentence:** the system now has a secure front door: people log in, see only their own brands,
start runs, watch them live, read the full "why" behind every recommendation, approve or reject, chat,
and — for admins — pull the emergency brakes.

## What changed

- `security/auth.py` — JWT login (local issuer; Cognito in production) and role checks.
- `api/app.py` + `api/routers/` — the FastAPI service (see `docs/17-api/api-reference.md`):
  runs (idempotent start, live SSE progress, replay), **explainability trace** (every decision, model
  call with its exact prompt and answer, retrieved sources and audit entries), reports and ratings,
  recommendations (approve with typed exposure / modify / reject), anomaly dismissal and rule proposals,
  streaming chat, knowledge-base uploads (sanitised and audited), and admin endpoints for kill switches,
  audit verification, cost, model health, notifications and queues. Security headers on every response,
  request IDs, metrics, per-tenant rate limiting, CORS limited to the frontend.
- `workers/agent_worker.py` — consumes the run queue and executes runs; on shutdown it hands the
  run back so another worker resumes from the checkpoint. In single-process local mode the API runs
  this worker in a background thread.
- Tests (`tests/api/test_api.py`) cover the full flow over HTTP, RBAC, **cross-tenant access returning
  404**, idempotency, kill switches, SSE chat, upload flagging and the dev-login lock in production.

## Why it matters (layman's terms)

"Explainability sells." One click from a recommendation shows the anomaly, the analysis, the evidence
and the exact text the AI saw and wrote. That is what makes account managers comfortable approving
instead of second-guessing.
