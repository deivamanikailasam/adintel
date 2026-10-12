# 0045 — The paperwork a customer's lawyers ask for, and a rule the code enforces

**In one sentence:** AdIntel now has a ready-to-review data processing agreement, a list of who else
touches data, the official records and risk assessment privacy law expects, a plain "AI system card" —
and the promise "your data is never used for training or kept by a model provider" is checked at start-up.

## What changed

- `docs/03-governance/legal/` — DPA template (processor role, 48-hour breach notice, AI commitments, return
  and deletion via `adintel offboard`), sub-processor register (local: none; production: AWS and MongoDB
  Atlas only for customer data), GDPR Art. 30 records, DPIA summary (residual risk low), AI system card
  (intended use, prohibited uses, L2 human oversight, models, evals, limitations, regulatory position).
- `config/models.yaml` — `data_terms` per tier; `llm/registry.py` refuses staging/production tiers without
  `no_training: true` and zero retention, and refuses `no_training: false` everywhere (ADR L-15).
- Test: `tests/unit/test_model_profiles.py::test_data_terms_are_enforced_outside_local`.
- Docs index links the pack. All templates are marked for counsel review.

## Why it matters (layman's terms)

Enterprise buyers can't sign until their privacy and legal teams have these documents; now they exist and
match how the system actually works. And the most important promise — nobody else learns from or keeps the
client's data — no longer relies on someone choosing the right setting: the system won't start in
production if a model's terms break it.
