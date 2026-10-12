# Owner decisions

Decisions that belong to the owner of a production system rather than to its code — made, recorded with
their reasoning, and enforced by code wherever code can enforce them. What remains is a short list of
actions only a person can take (sign, hire, apply, click).

| # | Decision | Why | Enforced by | Record | Human action still needed |
|---|----------|-----|-------------|--------|---------------------------|
| 1 | **Proprietary licence**; only permissive / weak-copyleft dependencies | Governance code is the product; open-sourcing is irreversible; procurement needs a clean licence report | CI licence gate, `Private :: Do Not Upload`, `THIRD_PARTY_NOTICES.md` | [L-14](../02-decisions/l-14-proprietary-licence-and-dependency-policy.md) | Confirm each model's `weights_license` on its model card before promotion |
| 2 | **Vendor is processor**; customer data stays with AWS + MongoDB Atlas (none locally) | Smallest possible sub-processor list; matches how the system is built | Sub-processor register; change procedure | [legal pack](legal/README.md) | Counsel review; sign DPA per customer; fill in legal entity and region |
| 3 | **No model provider may train on or retain data** | The core customer promise must not depend on picking the right plan | Model registry refuses staging/production tiers without the terms | [L-15](../02-decisions/l-15-model-provider-data-terms.md) | Link each provider's contractual terms in the PR that declares them |
| 4 | **Human oversight is permanent (L2)**; not a high-risk AI use on our assessment | The system advises on budgets, it never decides about people | Architecture tests, signed approvals, executor without a model | [AI system card](legal/ai-system-card.md), [DPIA](legal/dpia.md) | Counsel confirms the regulatory position per market |
| 5 | **External pentest** before go-live, annually, after major change; DAST on every PR | Independent evidence customers ask for; machines catch regressions between tests | CI `dast`, `make dast` | [penetration-testing.md](../04-security/penetration-testing.md) | Select and contract the firm; schedule before go-live |
| 6 | **Two-person rule on the default branch**; immutable release tags | No single person can push money-moving code unreviewed | Rulesets as code + sync test | [0047](../changelog/0047-branch-protection.md) | Run `scripts/apply_repo_rules.sh deivamanikailasam/adintel` once as admin |
| 7 | **P1 pages 24/7**, P2 business hours, weekly rota of ≥ 4 | Isolation/audit/execution incidents can't wait; design limits night-time impact | Alert routing, webhook, weak-token refusal | [on-call.md](../12-operations/on-call.md) | Staff the rota; create PagerDuty/Slack receivers |
| 8 | **Platform-by-platform go-live**: CSV first, live read on approval, write after 4 clean weeks | Don't block launch on the slowest approval; earn write access | Per-platform modes; production refuses synthetic data | [ad-platform-access.md](../14-production/ad-platform-access.md) | Submit the five applications; implement `connectors/live.py` per approved platform |
| 9 | **Forward-only migrations**, backup as rollback | Safe blue/green deploys | Migration runner, `--check` gate in the release | [L-13](../02-decisions/l-13-forward-only-data-migrations.md) | — |

Review this page at every major release and whenever a "revisit when" trigger in a linked ADR fires.
