# Open questions the design still carries

Having these written down is part of governance: they are known unknowns with owners, not surprises.

| # | Question | Owner | How we'll decide |
|---|----------|-------|------------------|
| Q1 | Is anonymising cross-brand incidents at index time enough contractually when some clients compete, or should cross-brand learning be opt-in? | Legal + FDE | Client contract review; default is anonymised + same-tenant only |
| Q2 | Is ~4 anomaly alerts per brand per week the right load for an account manager with 3 brands? | Head of Performance | Track dismissal rate; rising dismissals mean drift towards noise |
| Q3 | Should recommendations expire in 72 hours or less? Longer means more stale-world rejections; shorter means missed weekend approvals. | Product | `ADINTEL_RECOMMENDATION_TTL_HOURS`; analyse rejection reasons "stale" |
| Q4 | Is the MoE small model (or a dedicated 7–9B dense model) a better fine-tune base for reports? | ML lead | Report eval set: tone, structure, grounding, blind preference |
| Q5 | At what brand count do per-tenant vector indexes beat shared indexes with filters? | Tech lead | p95 retrieval latency and recall@6 at 50/200 brands |
| Q6 | Do high-spend brands need intraday runs? | Head of Performance | Spend-at-risk per day of detection lag |
