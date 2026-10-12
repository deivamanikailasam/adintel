# Promoting AdIntel from local to production — step by step

This guide takes the system you run on your laptop to a governed production deployment on AWS. Nothing
in the application code changes: every local component sits behind an interface, and promotion swaps the
implementation through configuration (`docs/01-architecture/aws-to-local-mapping.md`).

> **In plain words:** you've been flying the plane in a simulator. This is the checklist for moving to the
> real aircraft: same controls, real engines, a co-pilot (staging), and a sign-off before each flight.

---

## Phase 0 — Decide and sign off (week 0)

| Decision | Who | Record |
|----------|-----|--------|
| Production model for each tier (frontier on Bedrock, small/report/safety on SageMaker or Bedrock) | ML lead | `config/models.yaml` PR + eval report |
| Autonomy level stays **L2** (human approves all execution) | Sponsor | ADR D-07 |
| Approval matrix and personal limits | Sponsor + Head of Performance | `approvals/matrix.py`, `users` |
| Data residency, retention and the client disclosure | Legal + Security | `docs/04-security/data-map.md`, `docs/03-governance/client-disclosure.md` |
| On-call rota and escalation | Tech lead | PagerDuty |

**Exit criterion:** all five recorded, named owners in the RACI (`docs/03-governance/raci.md`).

## Phase 1 — Accounts, network and identity (weeks 1–2)

1. **Three AWS accounts** (AWS Organizations): `prod`, `staging`, `shared-services` (CI/CD, ECR, central
   logs, Terraform state). An account is the only truly hard blast-radius boundary in AWS.
2. **Terraform state** in shared-services: S3 bucket (versioned, KMS) + DynamoDB lock table; uncomment the
   `backend "s3"` block in `infra/terraform/envs/*/main.tf`.
3. **CI → AWS via OIDC** (no long-lived keys): create deploy roles per account and set
   `AWS_SHARED_SERVICES_ROLE`, `AWS_STAGING_DEPLOY_ROLE`, `AWS_PROD_DEPLOY_ROLE` as GitHub secrets.
4. `terraform apply` the staging environment (`infra/terraform/envs/staging`): one VPC over 3 AZs, public /
   private-app / private-data subnets, NAT with **static Elastic IPs** (give these to ad platforms that
   require IP allow-listing — output `nat_egress_ips`), VPC endpoints for Bedrock, SageMaker, Secrets
   Manager, SQS, KMS, Logs, ECR, Scheduler and S3.
5. **Cognito** user pool (MFA on, `tenant_id` immutable attribute). Replace `security/auth.decode_token`
   with RS256/JWKS verification against the pool; set `ADINTEL_DEV_LOGIN_ENABLED=false` (startup refuses
   otherwise in staging/production).

**Exit criterion:** `terraform plan` clean; no resource has a public endpoint except the ALB and CloudFront.

## Phase 2 — Data plane (weeks 2–3)

1. **MongoDB Atlas** (M30, 3-node, customer-managed KMS, PITR, 7-day continuous backup + 12 monthly
   snapshots) with **PrivateLink only** — the access list contains only the PrivateLink endpoint. Store the
   connection string in `adintel/<env>/atlas-uri`.
2. Create indexes: `python -c "from adintel.storage import get_database; get_database()"` runs
   `ensure_indexes` (every index leads with `tenant_id`). Create the vector index with the **production
   embedder's dimension** (1,024 for a voyage-3-class model; 384 for BGE-small):
   `get_database().ensure_vector_index("kb_chunks", 1024, ["tenant_id","brand_id","doc_type","is_active","vertical","anonymised","date"])`.
   Consider a time-series collection for `metrics_daily` (4–6× smaller, faster range scans).
3. Grant the services a database role with **insert + find only on `audit_log`** (no update/delete).
4. **S3:** artefacts bucket (prompt archive 13 months, reports, KB sources; Glacier IR after 90 days) and
   the **audit bucket with Object Lock (compliance, 7 years)**; schedule the daily audit export.
5. **SQS:** `agent-runs` (visibility 900 s) and `executions.fifo`, each with a DLQ (maxReceiveCount 5) —
   created by Terraform. Set `ADINTEL_QUEUE=sqs`.
6. **ElastiCache Redis** (multi-AZ, TLS) for the semantic cache, rate-limit buckets and SSE reconnect
   buffers. Move `RateLimiter` and `SemanticCache` to Redis-backed implementations when running more than
   one API task (they are in-process locally).

**Exit criterion:** `pytest -m integration` passes against staging Atlas and Redis from a bastion/CI runner.

## Phase 3 — Models (weeks 2–4, in parallel)

| Tier | Local | Production | Config change |
|------|-------|-----------|---------------|
| frontier | Qwen3.8-27B-8bit (mlx) | Bedrock frontier model, **exact versioned model ID** | `provider: bedrock`, `model_id`, `ADINTEL_LLM_PROVIDER=bedrock` |
| small | Qwen3.6-35B-A3B-4bit (mlx) | SageMaker LMI/vLLM endpoint (OpenAI-compatible) or Bedrock | `provider: openai_compat`, `base_url` = endpoint proxy, `model_id` pinned |
| report | small + LoRA adapter | Same base on SageMaker with **multi-adapter (LoRA) serving** | adapter `path` + `sha256` |
| safety | Qwen classifier prompt | Llama Guard 3 on SageMaker + Bedrock Guardrails (ADR L-08 revisit) | `safety` tier |

Steps:
1. Choose models; **re-run the full eval suite against them** in staging
   (`python -m adintel.evals.runner --provider mlx` with the staging `config/models.yaml`; the runner uses
   whatever providers the registry names). Production models must pass every hard threshold **and** the
   quality thresholds; record the report in the PR.
2. Re-train the report adapters on the production base model (`finetune/`), sign them, upload to versioned
   S3 with MFA delete; pin the SHA-256 in `config/models.yaml`.
3. Bedrock: request access, enable **data retention opt-out**, configure **provisioned throughput for
   Monday 06:00–12:00** (the peak), on-demand otherwise. Add prompt-caching headers via `extra_body`.
4. SageMaker: `report-model` scaled up Sunday 22:00–Monday 10:00; `guardrail-model` minimum 1 (it must
   always be up because it fails closed).

**Exit criterion:** `GET /admin/models` shows every tier healthy in staging; eval gate passes on production
models; cost per run path within ±15% of the accepted baseline.

## Phase 4 — Services (weeks 3–5)

1. CI builds **SHA-tagged images** to ECR (`.github/workflows/release.yml`; the Terraform variable refuses
   `:latest`).
2. ECS Fargate services (Terraform `ecs.tf`), each with its **own task role** (`iam.tf`):
   - `api` — 1 vCPU/2 GB, 2–20 tasks on CPU; read-only platform credentials; approval signing key.
   - `agent-worker` — 2 vCPU/8 GB, 2–40 tasks on queue depth; **cannot read write-credentials**.
   - `executor` — 0.5 vCPU/1 GB, 1–4 tasks; **the only role with write credentials; explicit IAM deny on
     every model API**; read-only root filesystem.
   - `scheduler` — or replace with **EventBridge Scheduler**: one schedule per brand in its timezone with the
     90-minute stagger, targeting the `agent-runs` queue (group `adintel-<env>-brands`).
3. Secrets: per-tenant, per-platform credentials in Secrets Manager under
   `adintel/<tenant>/<platform>/{read,write}`, rotated every 90 days; set `ADINTEL_SECRETS=aws`.
4. Analyst sandbox: `ADINTEL_SANDBOX=docker` equivalent — run the sandbox image as a separate
   network-isolated task (or Firecracker/Lambda without VPC egress) with cgroup CPU/memory limits.
5. Connectors: implement `connectors/live.py` for each platform (OAuth app per agency, **read-only scopes for
   ingestion**, write scopes only in the executor's credentials); add nightly **contract tests** against
   read-only sandbox accounts to catch API schema drift before it breaks a run.
6. Frontend: `ng build --configuration production` → S3 + CloudFront; WAF on the ALB; CSP headers at the CDN.

**Exit criterion:** staging smoke (`/ready`), the 40-scenario E2E golden runs and the k6 Monday-peak test
(`tests/load/monday_peak.js`, gate on p95) all pass in staging.

## Phase 5 — Observability and operations (weeks 4–6)

1. Logs → CloudWatch (structured JSON, `trace_id`/`run_id`/`tenant_id` on every line); traces →
   OpenTelemetry → X-Ray (`ADINTEL_OTEL_ENDPOINT` to an ADOT collector); metrics → CloudWatch EMF or Amazon
   Managed Prometheus; reuse the Grafana dashboards in `deploy/grafana/dashboards/`.
2. Langfuse **self-hosted inside the VPC** (traces contain client ad data, ADR D-09).
3. Alarms (Terraform `observability.tf` + `deploy/prometheus/alerts.yml` translated): P1 → PagerDuty 24/7,
   P2 → PagerDuty business hours, P3 → Slack.
4. Schedule the daily jobs (reconciliation, audit verification, DLQ, cost, expiry, narratives) — the
   scheduler service, or EventBridge → ECS RunTask.
5. **DR test with a real restore** before go-live (`docs/12-operations/disaster-recovery.md`).
6. Walk every P1 runbook once in staging (`docs/12-operations/runbooks.md`).

## Phase 6 — Staging with real (anonymised) data (weeks 5–7)

**Staging uses an anonymised copy of production data, refreshed weekly**, because synthetic data hides
exactly the messiness that breaks production. Models are the same as production on separate endpoints.

| Environment | Data | Models |
|-------------|------|--------|
| Local | Synthetic fixtures (`connectors/synthetic.py`) | Your mlx-lm models or mocked |
| Staging | Anonymised copy of production, refreshed weekly | Same as production, separate endpoints |
| Production | Real | Version-pinned |

## Phase 7 — Roll out brand by brand (weeks 7–11)

1. **Shadow mode:** for each brand, runs execute but reports are not sent and recommendations are not
   actionable; analysts compare and rate the outputs (feedback collection). Minimum **3 days on 20% of
   traffic** per change (the promotion gate).
2. Move a brand to live when its analysts sign off; feature flags enable new agents per tenant.
3. Start the **weekly 60-minute eval triage** from the first live week (`docs/07-evaluation/flywheel.md`).

## Phase 8 — Prove value and hand over (weeks 11–14)

Measure against the same baseline you measured before building (60% → 15% mechanical time; 5–9 days →
< 24 h detection; 3–4 h → < 10 min report turnaround). Hand over runbooks, on-call and the decision log.
**Handover is proven, not asserted:** the client's team handles every P1 runbook, runs the eval suite, adds
a brand end to end, rolls back a component and runs the weekly triage without you.

---

## The release pipeline (after go-live)

**On every pull request** (`.github/workflows/ci.yml`): ruff, `mypy --strict`, unit/API/E2E/chaos tests
with the 85% coverage gate, integration tests (Atlas Local + Redis service containers), agent evals +
promotion gate (no category regression; hard thresholds; **cost within ±15%**), bandit, npm audit, Trivy,
frontend build/tests, `terraform validate` (+ plan as a PR comment once credentials exist).

**On merge to main** (`.github/workflows/release.yml`): SHA-tagged image → staging via Terraform → 40-scenario
E2E golden runs and the full eval suite on staging models (gate) → k6 Monday-peak load test (gate on p95) →
smoke tests.

**Promote to production (manual approval = the named human sign-off):** blue/green ECS deploy with the ALB
shifting **10% → 50% → 100%**. **Automatic rollback** if the 5xx rate exceeds 1%, p95 latency doubles, the
eval canary score drops more than 5%, or the guardrail block rate rises at all. **Model and adapter changes
are canaried separately at 5% for 48 hours.**

## Deployment principles

- **Immutable artefacts:** SHA-tagged images, versioned adapters, versioned prompts (hash-pinned).
- **Independent lifecycles:** a prompt fix doesn't need a code deploy; a model rollback doesn't need a
  redeploy (change the version pointer).
- **Everything reversible in under 5 minutes:** code by shifting the ALB back; a prompt or model by changing a
  version pointer; infrastructure by applying the previous Terraform state.
- **Forward-compatible database changes:** ship the schema change before the code that uses it, never in the
  same release.

## Production readiness checklist

- [ ] `ADINTEL_ENV=production`; startup accepted (no dev secrets, no dev login, no memory storage/queue, no mock)
- [ ] JWT verification against Cognito JWKS; MFA enforced
- [ ] Approval signing key in Secrets Manager (prefer KMS asymmetric signing — ADR L-11 revisit)
- [ ] Executor task role: write secrets allowed, **all model APIs explicitly denied**; worker/api: write secrets denied
- [ ] Atlas PrivateLink only; KMS; PITR; audit role insert/find only; vector index at the production dimension
- [ ] S3 Object Lock audit export running daily; `adintel verify-audit` green
- [ ] Every tier pinned to an exact model ID; adapters signed and hash-pinned; eval report attached
- [ ] All hard eval thresholds at 100% / 0 on production models; baseline accepted and committed
- [ ] k6 Monday-peak p95 within SLO; chat p95 first token < 2.5 s
- [ ] DR restore tested; every P1 runbook walked; on-call rota live
- [ ] Client disclosure signed; data map reviewed by Security and Legal
- [ ] Shadow mode completed for the first brands; analysts signed off
