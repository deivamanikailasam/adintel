# Environments and CI/CD

| Environment | Data | Models | Infra | Who deploys |
|-------------|------|--------|-------|-------------|
| Local | Synthetic (seeded, deterministic) | Your mlx-lm models, or the mock | Laptop + Docker Compose | You |
| CI | Synthetic | Mock (evals), Atlas Local + Redis service containers | GitHub Actions | Every PR |
| Staging | Anonymised copy of production, refreshed weekly | Same as production, separate endpoints | AWS staging account | Merge to main |
| Production | Real | Version-pinned | AWS prod account | Manual approval |

Pipelines: `.github/workflows/ci.yml` (every PR) and `.github/workflows/release.yml` (main → staging →
manual → production). Details in [promotion-to-production.md](promotion-to-production.md#the-release-pipeline-after-go-live).

## Lifecycles

| Artefact | Versioned by | Gate | Rollback |
|----------|--------------|------|----------|
| Code | Git SHA → image tag | CI + eval gate + staging + manual | ALB shift back (blue/green) |
| Prompt | `prompts/registry.yaml` version + pinned SHA | `make evals` on the prompt's suite | Revert the registry entry |
| Model | `config/models.yaml` exact model ID | `make evals-mlx` / staging evals + 5% canary 48 h | Change the pointer |
| Adapter | Directory + SHA-256 + signature | `finetune/evaluate_adapter.py` + blind test + canary | Change the pointer |
| Infrastructure | Terraform state | `terraform plan` review | Apply the previous state |
| Brand rules / suppressions | `brand_rules.version` + audit | Human approval | Remove the rule (audited) |
