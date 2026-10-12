# 0041 — Rules for changing the code itself

**In one sentence:** the repository now enforces who must review what, how security problems are reported,
and what can never be committed, and every build lists exactly which software went into it.

## What changed

- `SECURITY.md` — private reporting, response times, the areas that matter most, scope and safe harbour.
- `.github/CODEOWNERS` — owners for security-critical, model-governance and infrastructure paths.
- `.github/pull_request_template.md` and issue templates (bug, feature; security issues redirected to a
  private advisory).
- `.pre-commit-config.yaml` + `make pre-commit` — ruff, mypy, gitleaks, large-file block, and a hook that
  refuses anything under `secrets/`, `data/import/`, `backups/`, `offboarding/` and `*.safetensors`/`*.gguf`.
- `.github/dependabot.yml` — weekly, grouped updates for pip, npm, GitHub Actions, Docker and Terraform.
- CI `supply-chain` job — gitleaks over the full history, CycloneDX SBOM for Python dependencies and an SPDX
  SBOM for the container image, uploaded as artefacts. `make sbom` for a local SBOM.
- Governance doc and CONTRIBUTING updated.

## Why it matters (layman's terms)

A bank vault needs rules about who holds which key, not just a thick door. These files say who must check
changes to the money-moving parts, stop passwords or client spreadsheets from being saved into the code
by accident, keep third-party parts up to date, and produce an ingredients list for every release so that
when a vulnerability is announced you can tell in minutes whether you are affected.
