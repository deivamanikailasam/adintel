# 0067 — A real accessibility audit, and the fixes it forced

**In one sentence:** every screen of the web app is now checked automatically against the WCAG 2.1 AA
rules on every build, the problems that check found are fixed, and there is a criterion-by-criterion
conformance report for customers' procurement teams.

## What the audit found (and what was fixed)

| Finding | WCAG | Fix |
|---------|------|-----|
| Success and warning badge text below 4.5:1 contrast (3.9:1, 3.3:1) — contradicting our earlier doc | 1.4.3 | New colour tokens, every pair ≥ 5.6:1 |
| Links inside sentences distinguishable by colour only | 1.4.1 | Underlined in-text links |
| Every screen had the same page title | 2.4.2 | Per-route titles |
| Idle sign-out happened without warning | 2.2.1 | One-minute warning dialog with "Stay signed in" |
| Error messages not announced to screen readers | 3.3.1 / 4.1.3 | `role="alert"` on error text |
| Wide tables could break narrow layouts | 1.4.10 | Panels scroll horizontally (data-table exception) |

## What changed

- `frontend/src/app/a11y.spec.ts` — renders all 12 screens with realistic data (including the status banner
  and idle dialog) and runs axe-core 4.10.2 with the WCAG 2.0/2.1 A + AA rule sets; any violation fails CI.
- `docs/16-frontend/accessibility-conformance-report.md` — all 50 WCAG 2.1 A/AA criteria: A 23 Supports / 7 N/A;
  AA 14 Supports / 1 Partially (reflow of data tables) / 5 N/A; five entries await the manual
  assistive-technology walkthrough, whose 45-minute script is included.
- Session spec covers the idle warning; 24 frontend tests in total.

## Why it matters (layman's terms)

"We think it's accessible" isn't something a buyer can sign off. A machine now checks every screen on every
change, it caught real problems we had wrongly said were fine, and the report says exactly what's proven,
what's not applicable, and the one human test left to do.
