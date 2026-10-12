# 0028 — Infrastructure as code for AWS, and how to promote to production

**In one sentence:** the production environment is described as code, and a phase-by-phase guide explains
how to move from your laptop to a governed AWS deployment.

## What changed

- `infra/terraform/modules/adintel` — VPC over three availability zones with private subnets, NAT with
  static IPs (for ad-platform allow-listing) and VPC endpoints so AWS traffic never crosses the internet;
  KMS encryption; S3 artefacts bucket and an **Object Lock** audit bucket (7 years); SQS queues with DLQs
  (`executions` is FIFO); Secrets Manager; Redis; ECS Fargate services with autoscaling; ALB + WAF;
  Cognito with MFA; EventBridge Scheduler group; alarms. **IAM:** one role per service — the executor can
  read write-credentials but has an *explicit deny* on every model API; the worker and API are denied
  write-credentials. The image variable refuses `:latest`.
- `infra/terraform/envs/{staging,prod}` — one AWS account each.
- `docs/14-production/promotion-to-production.md` — eight phases (decide and sign off; accounts, network
  and identity; data plane; models; services; observability and operations; staging with anonymised data;
  brand-by-brand rollout in shadow mode; prove value and hand over), the release pipeline, deployment
  principles and a production-readiness checklist.

## Why it matters (layman's terms)

"Works on my laptop" isn't a plan. This is the plan — including who must sign what, which settings change,
and which tests must pass before real client money is anywhere near the system.

## Note

`terraform fmt` passes. `terraform validate` needs the AWS provider download; CI runs it (the sandbox this
was written in blocks the Terraform registry).
