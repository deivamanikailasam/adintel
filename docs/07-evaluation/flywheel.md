# The evaluation flywheel

```
production runs → capture signals → weekly triage → curate datasets → improve → offline eval gate
       ↑                                                                               ↓
       └──────────────── promote or revert ←── shadow / A-B ←─────────────────────────┘
```

## Signals, ranked by value (all captured in the `feedback` collection)

| Signal | Volume (reference) | Why it matters |
|--------|-------------------|----------------|
| Recommendation approved or rejected (+ reason category) | ~40/week | A direct human judgement on the highest-stakes output. **Approval rate is the single best proxy for Optimizer quality.** |
| Approved **with modification** | ~8/week | "Gold": the human showed you the right answer |
| Actual vs predicted impact, 14 days after execution | ~25/month | The only objective quality signal |
| Report ratings, dismissed anomalies, guardrail blocks, frontier fallbacks, validation failures, degradations | continuous | Leading indicators |

## Weekly 60-minute triage (named owner: ML lead)

Review every rejection and categorise it (`wrong_diagnosis`, `right_diagnosis_wrong_action`,
`violates_unstated_preference`, `poorly_explained`, `stale`), every modification, every guardrail
block and ungrounded number, dismissed anomalies, and the top 3 degradation causes. Assign each to
one of four fixes.

**Prepared automatically.** `adintel triage --tenant brightwave` (or `GET /admin/triage`, or the Monday
09:00 UTC scheduler job that posts it to the Head of Performance) assembles the week's runs, degradations,
decisions, rejection reasons, approved-÷-proposed ratio, report ratings, guardrail blocks, cost and
outcomes into one page with suggested actions (`src/adintel/feedback/triage.py`). The meeting starts from
that page instead of from raw queries.

## Outcome tracking (actual vs predicted, `src/adintel/feedback/outcomes.py`)

Every day at 05:00 UTC the scheduler grades each successful execution that is at least 14 days old:
blended CPA of the touched entities in the 14 days before vs the 14 days after (execution day excluded),
compared with the Optimizer's predicted range. Verdicts: `within_range`, `better_than_expected`,
`improved_less_than_expected`, `worsened` (account manager notified, consider reverting) and
`insufficient_data` (fewer than 7 days or zero conversions on either side — nothing is claimed). Results go
to `outcomes`, the recommendation's `outcome` field, `feedback` (`outcome_measured`), the audit log and the
`adintel_outcomes_total{verdict}` metric. It is plain arithmetic: no model grades its own work. Run it by
hand with `adintel outcomes`.

## The four fixes, in order of preference

| Fix | When to use it | Takes | Risk |
|-----|----------------|-------|------|
| 1. Knowledge base | The model lacked information | Hours | Very low |
| 2. Deterministic rule | The behaviour should never vary | Hours | Low |
| 3. Prompt change | The model had the info but reasoned badly | Days | Medium |
| 4. Fine-tune or model change | Systematic style or capability gap | Weeks | Highest |

Most "the model got it wrong" cases are really "the model wasn't told" (fix 1) or "this shouldn't
have been the model's decision" (fix 2). Fix 2 is how the system becomes **more deterministic over
time**. Every triaged case also becomes a permanent eval case in `evals/datasets/`.

## Where the data lives

```python
db.feedback.find({"kind": {"$in": ["recommendation_rejected", "recommendation_modified",
                                   "recommendation_approved", "report_rating", "anomaly_dismissed"]}})
```
