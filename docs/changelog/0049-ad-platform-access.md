# 0049 — Don't wait for the slowest ad platform

**In one sentence:** each ad platform can now be switched from "spreadsheet exports" to "live API" on its
own as its approval comes through, and there's a checklist for getting those approvals.

## What changed

- `ADINTEL_CONNECTOR_MODES` — per-platform `synthetic | csv | live` on top of `ADINTEL_CONNECTORS`; used by
  the connector factory and the secret store.
- Production refuses synthetic data for any platform.
- `docs/14-production/ad-platform-access.md` — owner decision (CSV first; live read per platform as
  approved; executor write access only after four clean weekly read cycles), typical prerequisites and
  scopes per platform (marked "check current docs"), application checklist, tracker.
- Tests for per-platform modes and the production refusal.

## Why it matters (layman's terms)

Getting API approval from five ad platforms is like waiting for five different permits. Instead of keeping
the shop closed until the last one arrives, each counter opens as its permit lands — and the till (changing
budgets automatically) only opens after a month of the counter working properly.
