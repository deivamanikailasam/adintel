# Terraform (AWS production)

```
modules/adintel/   network (VPC, 3 AZs, NAT + static EIPs, VPC endpoints) · data (KMS, S3 + Object Lock audit,
                   SQS + DLQs, Secrets Manager, ElastiCache) · iam (one task role per service; executor denied
                   all model APIs; worker/api denied write secrets) · ecs (Fargate services + autoscaling) ·
                   edge (ALB, WAF, S3 frontend, Cognito with MFA) · scheduler (EventBridge group) · observability
envs/staging/      one AWS account
envs/prod/         another AWS account
```

```bash
cd infra/terraform/envs/staging
terraform init            # configure the S3 backend first (see main.tf)
terraform plan -var image=<account>.dkr.ecr.us-east-1.amazonaws.com/adintel:<git-sha>
```

MongoDB Atlas (M30, PrivateLink only) is provisioned with the Atlas console or the `mongodbatlas`
provider; its connection string goes into the `adintel/<env>/atlas-uri` secret. SageMaker endpoints for the
small/report/guardrail tiers are created by the model-deployment pipeline (they change on a different
lifecycle from the infrastructure). Full walkthrough: `docs/14-production/promotion-to-production.md`.
