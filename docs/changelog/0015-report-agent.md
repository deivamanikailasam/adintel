# 0015 — Report agent

**In one sentence:** the weekly client report is written in the brand's voice by the fast model, and
if a single number in it can't be verified, it is rewritten — or replaced by a plain, correct template.

## What changed

- `agents/report.py`
  - Builds a **facts** object from the database: totals, prior-period changes, per-platform figures,
    anomalies with their normal ranges, root causes, proposed actions and caveats. These are the only
    numbers the prose may use.
  - Writes the report with the report tier (Qwen3.6-35B-A3B + an optional style adapter per tone
    cluster) at temperature 0.2, in six fixed sections.
  - Checks every number (`rag/grounding.py`). If one fails → rewrites with the frontier model. If that
    fails, or the models or budget are unavailable → a **deterministic template** whose numbers are
    correct by construction.
  - **Appends every caveat by code**, so a model can't leave out "TikTok data was unavailable tonight".

## Why it matters (layman's terms)

A report that is slightly less elegant is acceptable; a report with one wrong number is not. This
agent is built so the worst case is "plain but correct", never "polished but wrong".
