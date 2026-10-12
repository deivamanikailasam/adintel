# L-15: Model providers must not train on or retain customer data — enforced in code

- **Status:** accepted
- **Owner:** Product owner, Security
- **Date:** 2026-10-12

## Context

Every model call carries (redacted) customer advertising data. Contracts and DPAs promise customers their
data is not used for training and not kept by third parties. A promise that depends on someone remembering
to pick the right API plan is not a control.

## Decision

- Default deployment runs models **locally** (mlx-lm or another local server): no third party involved.
- In staging and production, a model tier may be used only if `config/models.yaml` declares
  `data_terms: { no_training: true, retention: "none…" }` for it; the model registry **refuses to start**
  otherwise, and refuses `no_training: false` in every environment (`llm/registry.py::_check_data_terms`).
- Production providers are reached only through the cloud account's private endpoints (Bedrock /
  SageMaker via VPC endpoints); consumer chat products and direct third-party APIs are not used.
- Declaring the terms is a governance act: the change needs the model owner's review (CODEOWNERS) and a
  link to the provider's contractual terms in the PR.

## Consequences

A provider that keeps prompts for abuse monitoring (e.g. 30 days) cannot be used until a zero-retention
arrangement exists; this can rule out the newest hosted models for a while. The check proves the
configuration, not the provider's behaviour — the DPA and the provider's contract cover that.

## Alternatives rejected

- **Policy document only** — not testable; drifts the first time someone swaps a model under deadline.
- **Allow short retention (≤ 30 days)** — contradicts the customer promise and the sub-processor register.

## Revisit when

A customer explicitly opts into a provider with retention for a feature they want, or regulation requires
provider-side logging; then the exception becomes a per-tenant setting with its own disclosure.
