# L-14: Proprietary licence, with an enforced open-source dependency policy

- **Status:** accepted
- **Owner:** Product owner (Deiva Mani Kailasam)
- **Date:** 2026-10-12

## Context

AdIntel is sold to agencies as an enterprise system that can move client money behind human approval.
Its value is in the governance code (approval matrix, executor separation, evals, audit) as much as in the
agents. Customers' procurement teams ask two licence questions: *what rights do we get?* and *does anything
inside it force us to publish our code or limit commercial use?* Open-sourcing is a one-way door; a
proprietary licence can be relaxed later.

## Decision

- **AdIntel itself is proprietary** (`LICENSE`: all rights reserved; use only under a signed Customer
  Agreement). `pyproject.toml` carries the proprietary classifier and `Private :: Do Not Upload` (PyPI
  refuses the upload); the frontend is `"private": true`, `"license": "UNLICENSED"`.
- **Dependencies are allowed only under an approved licence** (`config/license-policy.yaml`): permissive
  (MIT, BSD, Apache-2.0, ISC, PSF…) and file-level/weak copyleft used unmodified (MPL-2.0, LGPL). Strong or
  network copyleft (GPL, AGPL, SSPL), source-available (BUSL) and non-commercial licences are **denied**;
  EPL/CDDL/CC-BY need a recorded exception.
- `scripts/check_licenses.py` enforces it in CI on the **production** install (Python + production npm
  tree) and regenerates `THIRD_PARTY_NOTICES.md`, shipped with every build next to the SBOMs (L-13/0041).
- **Model weights are not software we license**: each tier in `config/models.yaml` records
  `weights_license`, which must be confirmed on the exact model card before a model is promoted.

## Consequences

Customers get a clear contract position; procurement receives an SBOM, notices and a licence report with
every release. A useful library under GPL/AGPL cannot be adopted — find an alternative or isolate it
behind a network boundary with legal sign-off. Contributors outside the owner need a contributor agreement.

## Alternatives rejected

- **Apache-2.0 / MIT** — gives away the governance layer that differentiates the product; reversible only
  for future versions.
- **AGPL + commercial dual licence** — scares enterprise procurement and complicates hosted deployments.
- **Source-available (BUSL)** — adds a licence most procurement teams must review case by case, for no gain
  over a proprietary licence with a source-escrow clause in the Customer Agreement.

## Revisit when

The product strategy moves to an open-core model, or a customer requires source escrow or an
open-source licence as a condition of purchase.
