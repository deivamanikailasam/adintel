# 0039 — Run AdIntel on your own ad exports

**In one sentence:** without any ad-platform API access, you can drop CSV exports into a folder and get the
full nightly analysis, recommendations and approvals — and approved changes come out as a to-do list for a
person to apply.

## What changed

- `connectors/csv_files.py` — `ADINTEL_CONNECTORS=csv` reads `data/import/<tenant>/<brand>/<platform>.csv`
  in a simple template (`adintel csv-template`); one currency per file, converted to USD.
- `connectors/normalize.py` — a canonical row format (`adintel-csv/1`) alongside the five native platform
  shapes; unknown columns still surface as schema drift.
- **Manual execution**: the executor runs every check as usual, then the connector appends the exact
  instruction to `outbox.jsonl` and records the new budget in `budgets.json`, so the next run, the
  snapshot check and reconciliation all see it. No ad platform is ever written to in this mode.
- `adintel csv-sample` writes a brand's synthetic data as template CSVs — a worked example.
- Credentials: CSV mode needs none (scope policy still enforced, like synthetic mode).
- Docs: local setup §8a, `.env.example`, production promotion; tests in `tests/unit/test_csv_connector.py`
  (a complete run from CSV, approval, manual execution, write-scope refusal).

## Why it matters (layman's terms)

Getting API access from ad platforms can take weeks of paperwork. This lets an agency start with the
spreadsheets it already downloads every week. AdIntel does the same thinking, and instead of pressing the
button itself, it writes a precise note — "set Retargeting's budget from $800 to $600" — for a person to do.
