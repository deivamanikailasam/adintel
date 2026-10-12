# 0035 — Did it work? Outcome tracking, feature flags and the weekly triage page

**In one sentence:** the system now checks, two weeks after each approved change, whether it actually did
what was predicted; lets admins switch individual agents on or off per agency or brand; and prepares the
weekly review page automatically.

## What changed

- `feedback/outcomes.py` — daily job (05:00 UTC, `adintel outcomes`) that compares blended CPA 14 days
  before vs 14 days after each successful execution with the predicted range, and grades it
  (`within_range`, `better_than_expected`, `improved_less_than_expected`, `worsened`, `insufficient_data`).
  Stored in a new `outcomes` collection (7-year retention), on the recommendation, in `feedback`, in the audit
  log and as `adintel_outcomes_total{verdict}`. A `worsened` result notifies the account manager.
- `harness/flags.py` — feature flags `agent.analyst`, `agent.optimizer`, `chat.frontier_route`,
  `outcome_tracking`; brand override → tenant override → default; every change audited
  (`feature_flag.changed`). The graph skips a flagged-off agent with the new `feature_disabled`
  degradation (visible caveat, run health stays ok); chat falls back to the simple route.
- `feedback/triage.py` — weekly triage (`adintel triage`, `GET /admin/triage`, Monday 09:00 UTC job posting
  to the Head of Performance) with suggested actions derived from rejection reasons, degradations, outcomes,
  ratings and guardrail blocks.
- Admin API: `GET/POST /admin/flags`, `GET /admin/triage`, `GET /admin/outcomes`.
- Tests: `tests/unit/test_feedback_loop.py`, plus API and CLI tests. Evals and the promotion gate still pass.

## Why it matters (layman's terms)

A doctor who never checks whether the patient got better can't learn. Before, AdIntel predicted "this
budget move should cut cost per sale by 22–34%" and never looked back. Now it looks back two weeks later
with plain arithmetic, writes down whether it was right, and tells the account manager when a change made
things worse. Feature flags are the dimmer switch next to the emergency off-switch: you can give a new
client the reports first and turn on budget suggestions later, one brand at a time.
