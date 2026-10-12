# Local setup — step by step

This guide takes you from a clean Mac to a running AdIntel with your two local models. It also covers
a zero-dependency mode (no Docker, no models) for a first look.

> **Who this is for:** anyone. Each step says *what* to run, *why*, and *how to check it worked*.

## 0. What you need

| Item | Version | Why |
|------|---------|-----|
| Apple Silicon Mac (M2 Pro/Max or newer recommended) | macOS 14+ | `mlx-lm` uses the Apple GPU |
| Unified memory | **≥ 64 GB** to run both models at once (27B @ 8-bit ≈ 29 GB + 35B-A3B @ 4-bit ≈ 20 GB + KV cache) | With 32–48 GB, run one model and point both tiers at it (step 3b) |
| Python | 3.12 | Backend |
| [uv](https://docs.astral.sh/uv/) | latest | Fast virtualenv + installs |
| Docker Desktop | 4.30+ | MongoDB Atlas Local, Redis, Langfuse, Prometheus, Grafana, Jaeger |
| Node.js | 20 or 22 LTS | Angular 18 frontend |
| k6 (optional) | latest | Load test |

## 1. Get the code and the Python environment

```bash
git clone <your-repo-url> adintel && cd adintel
make venv            # creates .venv with Python 3.12
make install         # installs AdIntel + dev tools + the ml extra (BGE embeddings/reranker)
cp .env.example .env
```

**Check:** `.venv/bin/adintel --help` prints the command list.

## 2. First look in 30 seconds (no Docker, no models)

```bash
ADINTEL_LLM_PROVIDER=mock .venv/bin/adintel demo
```

This seeds two agencies and five brands into an in-memory database and replays "one night in
production" with deterministic stand-in models. You should see Urban Roast go through the full
investigation to a **$200/day recommendation pending approval**, Fitely go straight to report, and
NorthPeak **stop** because its conversion tracking is broken.

Then run the tests: `make test` (≈ 3 minutes, no services needed).

## 3. Serve your two models with mlx-lm

```bash
uv pip install "mlx-lm>=0.22"        # in the same venv, or `pipx install mlx-lm`
```

### 3a. Both models (recommended, ≥ 64 GB)

Open two terminals:

```bash
make mlx-small       # Qwen3.6-35B-A3B-4bit on http://127.0.0.1:8080  (small / report / safety tiers)
make mlx-frontier    # Qwen3.8-27B-8bit     on http://127.0.0.1:8081  (frontier / judge tiers)
```

The first start downloads the weights from Hugging Face (`mlx-community/...`). If your copies have
different names or live on disk, either pass them (`scripts/mlx/serve_small.sh /path/to/model`) and
set `ADINTEL_MODEL_SMALL_ID` / `ADINTEL_MODEL_FRONTIER_ID` in `.env` to the **same** value — the
model ID in requests must match what the server loaded.

**Check:** `scripts/mlx/check.sh` shows both servers `OK` and a JSON smoke test, and
`.venv/bin/adintel models` shows `"ok": true` for every tier.

### 3b. One model only (32–48 GB)

Serve just the small model on :8080 and point the frontier tier at it:

```bash
echo 'ADINTEL_MODEL_FRONTIER_BASE_URL=http://127.0.0.1:8080/v1' >> .env
echo 'ADINTEL_MODEL_FRONTIER_ID=mlx-community/Qwen3.6-35B-A3B-4bit' >> .env
```

Everything works; judgement quality is lower. Re-run `make evals-mlx` to see by how much.

### Qwen "thinking" mode

Qwen3-family models can emit `<think>…</think>` reasoning. AdIntel strips it before parsing and, by
default, adds Qwen's `/no_think` switch (`ADINTEL_QWEN_NO_THINK=true`) for faster, cleaner JSON.

## 4. Start the local infrastructure

```bash
make up
docker compose -f deploy/docker-compose.yml ps     # all services "healthy"/"running"
```

| Service | URL | Login |
|---------|-----|-------|
| MongoDB Atlas Local (with Vector Search) | `mongodb://localhost:27017` | — |
| Redis (queues, AOF on) | `redis://localhost:6379` | — |
| Langfuse (agent traces) | http://localhost:3000 | `admin@adintel.local` / `adintel-local` |
| Jaeger (distributed traces) | http://localhost:16686 | — |
| Prometheus | http://localhost:9090 | — |
| Alertmanager | http://localhost:9093 | — |
| Grafana (4 dashboards in folder "AdIntel") | http://localhost:3001 | `admin` / `adintel-local` |
| Keycloak (enterprise SSO stand-in for Cognito, realm `adintel`) | http://localhost:8180 | `admin` / `adintel-local` |
| MinIO (write-once audit archive, stand-in for S3 Object Lock) | http://localhost:9001 | `adintel` / `adintel-local` |

Switch AdIntel to the real services in `.env`:

```bash
ADINTEL_STORAGE=mongo
ADINTEL_QUEUE=redis
ADINTEL_SHARED_STATE=redis          # rate limits + semantic cache shared by api/worker/scheduler
ADINTEL_EMBEDDER=fastembed          # BGE embeddings (downloads ~100 MB once)
ADINTEL_RERANKER=fastembed          # BGE cross-encoder
ADINTEL_OTEL_ENDPOINT=http://localhost:4318
ADINTEL_LANGFUSE_HOST=http://localhost:3000
ADINTEL_LANGFUSE_PUBLIC_KEY=pk-lf-local
ADINTEL_LANGFUSE_SECRET_KEY=sk-lf-local
```

Then load the reference data (and create the vector index on first run):

```bash
.venv/bin/adintel seed
.venv/bin/adintel migrate          # apply data migrations (recorded in schema_migrations)
```

**Check:** `pytest -m integration` passes (real Mongo `$vectorSearch` pre-filter and Redis queue
visibility/DLQ).

## 5. Run the services (four terminals, or the compose `app` profile)

```bash
make run-api         # :8000  — FastAPI; OpenAPI docs at http://localhost:8000/docs
make run-worker      # agent-worker (LangGraph); metrics on :9464; read-only credentials
make run-executor    # executor-service; metrics on :9465; the ONLY process with write credentials
make run-scheduler   # weekly runs per brand timezone + daily governance jobs
```

Or containerised (models stay on the host):

```bash
docker compose -f deploy/docker-compose.yml --profile app up -d --build
```

> **Single-process shortcut:** with `ADINTEL_QUEUE=memory` the API runs the agent worker in a background
> thread, so `make run-api` alone is enough for exploring (the executor still needs `make run-executor`
> with a shared queue, i.e. Redis).

## 6. Start the frontend

```bash
make frontend-install
cd frontend && npm start         # http://localhost:4200 (proxies /api → :8000)
```

Log in as one of the seeded users (local dev login, no password):

| Email | Role | Can approve up to |
|-------|------|-------------------|
| `jordan@brightwave.example` | Account manager (Urban Roast, Fitely) | $500/day |
| `priya@brightwave.example` | Account manager (NorthPeak, Cobalt) | $500/day |
| `sam@brightwave.example` | Senior account manager | $2,000/day |
| `hana@brightwave.example`, `alex@brightwave.example` | Head of Performance (four-eyes pair) | $100,000/day |
| `admin@brightwave.example` | Admin (kill switches, audit) | — |
| `viewer@brightwave.example` | Viewer (read-only) | — |
| `am@acme.example` | Account manager at a **different agency** (isolation demo) | $500/day |

**Enterprise sign-in (SSO).** With Compose running, the login page also shows **Sign in with SSO**. It
redirects to Keycloak (authorization code + PKCE), where the same users exist with password
`adintel-local`. The API verifies the Keycloak-signed token against its JWKS. To rehearse production
behaviour, set `ADINTEL_AUTH_MODE=oidc` — the password-less dev login then stops working, exactly as in
staging and production.

| Variable | Local value | Production value |
|----------|-------------|------------------|
| `ADINTEL_AUTH_MODE` | `both` (Compose) / `dev` (bare) | `oidc` (enforced) |
| `ADINTEL_OIDC_ISSUER` | `http://localhost:8180/realms/adintel` | `https://cognito-idp.<region>.amazonaws.com/<pool-id>` |
| `ADINTEL_OIDC_AUDIENCE` | `adintel-api` | the Cognito app client id |
| `ADINTEL_OIDC_TENANT_CLAIM` | `tenant_id` | `custom:tenant_id` |
| `ADINTEL_OIDC_ROLES_CLAIM` | `realm_access.roles` | `cognito:groups` |

## 7. Walk through the product

1. As **Jordan**, open *Brands → Urban Roast → Run now* and watch the live timeline.
2. Open the recommendation: evidence, root cause, the exact prompts (Trace tab). Type `200` and approve.
3. The executor applies it: AS-B budget 800 → 600, AS-A 560 → 760 (`/admin/notifications`).
4. As **Acme AM**, try to open Jordan's run URL → 404. Isolation works.
5. As **Admin**, engage a brand kill switch and try to start a run → 423.
6. Ask the chat "What was spend last week?" (fast path) and "Why did retargeting costs rise?" (frontier + RAG).

## 8. Evaluate your models

```bash
make evals-mlx      # all suites against Qwen3.8-27B + Qwen3.6-35B-A3B
make gate           # promotion gate vs evals/baseline.json
```

Use `--sample 3` for a quick pass. See `docs/07-evaluation/evaluation.md`.

## 8b. Back up, archive, and practise a restore

```bash
.venv/bin/adintel audit-archive            # copy new audit entries to write-once storage
.venv/bin/adintel audit-archive --verify   # does the database still match the archive?
scripts/backup.sh                          # native Mongo/Redis/secrets backup → backups/<timestamp>/
.venv/bin/adintel backup --out backups     # portable backup + automatic restore drill
```

See [disaster recovery](../12-operations/disaster-recovery.md) for restores.

## 9. Everyday commands

| Command | What it does |
|---------|--------------|
| `make test` / `make test-cov` | Tests / with the 85% coverage gate |
| `make lint typecheck security` | ruff, mypy --strict, bandit |
| `make evals` / `make gate` | Eval suites (mock) / promotion gate |
| `make verify-audit` | Verify every tenant's audit hash chain |
| `make reconcile` | Executed changes vs approvals |
| `make load-test` | k6 Monday-peak profile |
| `adintel token --user u_jordan` | A JWT for curl |

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| `adintel models` shows `ok: false` | The mlx server isn't running on that port, or the model ID in `.env` differs from what the server loaded |
| Runs end `degraded: frontier_unavailable` | Frontier server down or timing out (90 s). Check memory pressure; try 3b |
| JSON validation failures in logs | Usually thinking text: keep `ADINTEL_QWEN_NO_THINK=true` |
| `$vectorSearch` errors | You're on plain MongoDB; use the `mongodb-atlas-local` image (compose) or `ADINTEL_VECTOR_SEARCH=python` |
| Executor refuses "live entity changed" | Expected after a manual change in the platform: the recommendation is stale; re-run |
| Startup refuses "unsafe configuration" | You set `ADINTEL_ENV=staging/production` with development secrets — by design |
