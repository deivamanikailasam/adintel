# Accessibility and session security in the web app

## Accessibility (target: WCAG 2.1 AA)

| Area | What the app does |
|------|-------------------|
| Keyboard | "Skip to content" link; all actions are buttons/links/forms (no click-only divs); visible focus outline on every control (`:focus-visible`) |
| Names and labels | Every input and select has a visible `<label>` or an `aria-label`; main navigation is `aria-label="Main"`; `lang="en"` |
| Live content | Chat answers stream into `role="log" aria-live="polite"` (with `aria-busy` while streaming); the run timeline and the status banner are live regions, so screen readers hear progress without the page being re-read |
| Motion | `prefers-reduced-motion` disables animation and smooth scrolling |
| Colour | Status is never colour-only: badges carry text (`approved`, `failed`, `degraded`); all text colour pairs ≥ 5.6:1 (verified by axe); links in text are underlined |
| Model output | Rendered as escaped text (interpolation only), which also keeps assistive tech from reading injected markup |

Automated audit: axe-core runs on all 12 screens in every build (`a11y.spec.ts`, 0 violations). Full
criterion-by-criterion results: [accessibility-conformance-report.md](accessibility-conformance-report.md).
Remaining: a manual assistive-technology walkthrough (script in the report).

## Sessions

| Control | Behaviour |
|---------|-----------|
| Token storage | `sessionStorage` (cleared when the tab closes); the SSO refresh token lives **in memory only** |
| Idle timeout | Signed out after `ADINTEL_SESSION_IDLE_MINUTES` (default 30) without activity, after a one-minute warning with "Stay signed in" (WCAG 2.2.1); the sign-in page says why |
| Expiry | Dev tokens: signed out at `exp`. SSO: refreshed a minute before `exp` with the refresh token; failure → sign-out with a message |
| Logout | Clears the local session **and** ends the identity-provider session (OIDC RP-initiated logout), so the next person at the machine can't sign straight back in |
| Server side | Every request re-checks the user record (deactivated/demoted users are refused regardless of token) |

Tests: `frontend/src/app/core/auth.service.spec.ts` (expiry parsing, idle sign-out, expiry sign-out).
