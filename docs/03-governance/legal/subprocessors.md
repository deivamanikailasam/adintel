# Sub-processor register

Owner decision: **customer data stays inside infrastructure we control**. Only two third parties host
customer data in production, and model inference never leaves them. Everything else receives operational
metadata at most.

## Local / on-premises deployment

| Sub-processor | Data | Notes |
|---------------|------|-------|
| — | — | **None.** Models (mlx-lm or alternatives), database, queues, identity (Keycloak), object storage (MinIO) and observability all run on the agency's own machine |

## Production (AWS)

| Sub-processor | Service | Customer data? | Purpose | Location | Safeguards |
|---------------|---------|----------------|---------|----------|------------|
| Amazon Web Services | ECS, S3, SQS, KMS, Secrets Manager, Cognito, CloudWatch | **Yes** | Hosting, storage, identity, logs | [Selected region] | DPA + SCCs; KMS encryption; VPC endpoints |
| Amazon Web Services | Amazon Bedrock / SageMaker (model inference) | **Yes** (redacted prompts) | Frontier and volume models | Same region | No training on inputs, no prompt retention by AWS or model publishers (ADR L-15); VPC endpoint only |
| MongoDB, Inc. | Atlas (dedicated cluster) | **Yes** | Primary database, vector search | Same region, PrivateLink | DPA + SCCs; encryption at rest with customer-managed KMS key |
| PagerDuty, Inc. | Incident paging | No — alert titles and tenant ids only | On-call | US | No PII in alerts (enforced by alert templates) |
| Slack Technologies | P3 notifications | No — alert titles only | Team notifications | [Region] | As above |
| GitHub, Inc. | Source control, CI | No — code only | Development | US | Synthetic data only in tests and fixtures; secret scanning |

Not used, deliberately: third-party LLM APIs outside the cloud account, hosted Langfuse (self-hosted in
the VPC instead), analytics or session-replay tools in the web app.

**Change procedure:** a new sub-processor needs a security review, an update to this register, a DPA,
and [30] days' notice to customers (DPA §5). Model-provider changes also need the promotion gate.
