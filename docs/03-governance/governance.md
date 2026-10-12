# Governance, human-in-the-loop and safe actions

AdIntel sits deliberately at **autonomy level L2**: the AI proposes with evidence, a named human
approves, and the system executes. This is a product principle, not a v1 limitation.

| Level | Meaning | AdIntel |
|-------|---------|---------|
| L0 | Human does everything | — |
| L1 | AI suggests, human does | — |
| **L2** | **AI proposes with evidence, human approves, system executes** | **Here** |
| L3 | AI executes, human can override afterwards | Considered for low-risk actions in v3, not committed |
| L4 | Full autonomy | Explicitly rejected |

**Why L2:** autonomous execution saves a few hours; one wrong autonomous budget change can lose a
client. The asymmetry is not close. It was put to the sponsor as a business decision (ADR D-07).

**A gate must be fast, or it gets rubber-stamped.** Evidence is one click away and low-exposure
changes are one tap. A rubber-stamped gate is worse than none, because it creates false assurance.

## Approval authority matrix (`src/adintel/approvals/matrix.py`)

| Daily exposure | Who can approve | Second approver? |
|----------------|-----------------|------------------|
| < $50, low risk | Any account manager | No |
| $50–$500, low/medium | The brand's assigned AM (or a senior AM / Head of Performance) | No |
| $500–$2,000 | Senior AM or Head of Performance | No |
| > $2,000 | Head of Performance | **Yes** |
| Any, high risk or irreversible | Head of Performance | **Yes** |
| Any, during a blackout window | **Blocked** | — |

On top of the role, each person has a personal `approval_limit_usd` (e.g. an AM: $500/day).

## The approval endpoint, checked in code (`src/adintel/approvals/service.py`)

When someone clicks Approve, the server checks, **in order**:

1. It is still pending and not expired.
2. **The typed exposure matches** the recommendation's exposure — stops blind clicking.
3. The approver's role and limit cover this exposure and risk.
4. Above the threshold, a **second, different** approver (Head of Performance) is required.
5. Not in a blackout window.
6. **Brand constraints still pass now**, not just at 2 AM.
7. **The live ad entity hasn't changed:** its snapshot hash must match the one the recommendation was
   made against.

Checks 6 and 7 are the ones teams forget: a recommendation made at 2 AM and approved at 4 PM may be
stale because someone paused the ad set or the budget was renegotiated. Every failed check is
audit-logged with its name.

Then the approval is **signed** (HMAC-SHA256, ADR L-11), audit-logged and queued to the executor
(FIFO). A person may also **approve with modification** (reduce the amount) — recorded as "gold"
feedback — or **reject with a reason category** (`wrong_diagnosis`, `right_diagnosis_wrong_action`,
`violates_unstated_preference`, `poorly_explained`, `stale`, `other`), which feeds the weekly triage.

## After approval: the executor (`src/adintel/executor/`)

The executor has write credentials and **no model access** (a test fails the build if it can import
any model, agent, RAG or graph code). It verifies the signature, the recommendation status, that no
execution exists yet, the blackout window, and **re-reads live state** before writing. Budget shifts
decrease the source first, so a partial failure removes money rather than doubling it. Writes retry
at most once and never after a partial apply. A **nightly reconciliation** compares every executed
change with what was approved; any mismatch pages immediately (P1).

## Feature flags: planned rollout, per tenant and per brand (`src/adintel/harness/flags.py`)

Kill switches are emergency brakes; feature flags are the rollout dial. A flag turns one capability on
or off for a tenant or a single brand, and the brand override wins:

| Flag | Default | When off |
|------|---------|----------|
| `agent.analyst` | on | No root-cause investigation; report covers performance and anomalies |
| `agent.optimizer` | on | No budget proposals — "report-only" mode for a new client |
| `chat.frontier_route` | on | Complex chat questions are answered by the small model without RAG |
| `outcome_tracking` | on | 14-day actual-vs-predicted grading is skipped |

A flagged-off agent is skipped through the same path as an unavailable one, with the
`feature_disabled` degradation, so the client report says what was not done (run health stays *ok*:
it was planned). Changes are admin-only (`POST /admin/flags`, `adintel flags --set agent.optimizer=off`)
and every change is written to the audit log (`feature_flag.changed`). Typical rollout: new agency starts
with `agent.optimizer` off for two weekly cycles, then on for one pilot brand, then tenant-wide.

## Governance artefacts

| Artefact | Purpose | Owner | Where |
|----------|---------|-------|-------|
| Model registry | Every model, version, adapter hash, owner and production equivalent | ML lead | `config/models.yaml` |
| Prompt registry | Versioned prompts with pinned hashes and eval suites | ML lead | `prompts/registry.yaml` |
| Decision log | Decisions, rationale, revisit triggers | Tech lead | `docs/02-decisions/` |
| Audit log | Immutable record of every agent and human action | System | `audit_log` collection |
| Weekly eval report | Quality metrics vs thresholds | ML lead | `evals/reports/` |
| Incident log | Every P1/P2 with postmortem | On-call | `docs/12-operations/incidents/` |
| Data map | What data, where, retention, access | Security | `docs/04-security/data-map.md` |
| Client disclosure | Plain statement of what AdIntel does with client data | Legal + FDE | `docs/03-governance/client-disclosure.md` |
| RACI | Who decides what | Sponsor | `docs/03-governance/raci.md` |

**Transparency to clients:** contracts and reports state that AI drafts and analyses and that a
named human approves every recommendation. Each report's footer names the system version and the
approver. Leading with that is a selling point, not a liability.

## Seven non-negotiable safety principles

1. No autonomous spending. Ever.
2. Fail closed on safety checks.
3. Refuse rather than fabricate: no analysis on untrustworthy data.
4. Every number traceable to source data.
5. Every recommendation traceable to cited evidence.
6. Tenant isolation never degrades.
7. Every action attributable to a named human, or to an identified agent and model version.

Each principle maps to code and a test — see `docs/05-safety/safety.md`.
