# 0043 — Screens for the weekly review, outcomes, feature flags and privacy requests

**In one sentence:** the Head of Performance and admins can now see the weekly triage, check whether
approved changes worked, switch capabilities on per brand, and handle "show me / forget me" requests in the
web app instead of the command line.

## What changed

- `/admin/learning` (`pages/learning.component.ts`): triage with suggested actions and a 7/14/30-day window,
  the 14-day outcome table with colour-coded verdicts, effective flags for the tenant or a brand, the list
  of overrides, and (admins only) a form to change a flag with an audited reason.
- `/admin/privacy` (`pages/privacy.component.ts`, admin only): export a user's data (summary + JSON
  download) and erase a user — the button stays disabled until the user id is typed twice; server refusals
  (e.g. erasing yourself) are shown.
- Links from the Governance page; new `ApiService` methods; component specs (5 frontend tests in total).
- Removed the unused Angular CLI placeholder template and stylesheet.
- Docs: frontend page table; readiness matrix "known limits" updated (offboarding, purge, backups and
  migrations remain CLI-only by design).

## Why it matters (layman's terms)

The learning loop only helps if the people who run the meeting can see it. Now the weekly review page,
the "did it work?" scorecard and the on/off switches are a click away, and privacy requests have a guarded
form with a "type it again to confirm" step — the kind of safety catch you want on a delete button.
