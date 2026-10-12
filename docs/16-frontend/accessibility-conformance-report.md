# Accessibility conformance report — AdIntel web app

Format modelled on the VPAT® 2.x / WCAG 2.1 edition. **Standard:** WCAG 2.1 levels A and AA.
**Product:** AdIntel web app (Angular), version in `frontend/package.json`. **Date:** 2026-10-12.

## Evaluation methods

1. **Automated audit — every page, every build.** `frontend/src/app/a11y.spec.ts` renders all 12 screens
   (shell, sign-in, brands, brand detail, approvals, recommendation, report, run detail, chat, governance,
   learning & rollout, privacy) with realistic data, including the idle-warning dialog and status banner, and
   runs **axe-core 4.10.2** with the `wcag2a`, `wcag2aa`, `wcag21a`, `wcag21aa` rule sets (68 rules, 23 success
   criteria). **Result: 0 violations on all 12 screens.** Any new violation fails CI.
2. **Expert code review** of templates and styles against each criterion below (keyboard operability, focus
   order, names, status messages, timing).
3. **Not yet performed:** a manual walkthrough with assistive technology (VoiceOver on macOS, NVDA on
   Windows) and keyboard-only by a tester. Criteria that can only be confirmed that way are marked
   "Supports (pending manual verification)".

Findings the audit surfaced and that were **fixed** before this report: badge text contrast (success 3.9:1 and
warning 3.3:1 → all colour pairs now ≥ 5.6:1); links inside text distinguished by colour only (now underlined);
identical page titles (now per screen); idle sign-out without warning (now a one-minute warning with "Stay
signed in"); error messages not announced (now `role="alert"`).

## Results

Conformance levels: **Supports**, **Partially supports**, **Does not support**, **Not applicable**.

### Level A

| Criterion | Level | Notes |
|-----------|-------|-------|
| 1.1.1 Non-text content | Supports | No informative images; status conveyed as text (axe: image-alt, etc. pass) |
| 1.2.1–1.2.3 Time-based media | Not applicable | No audio or video |
| 1.3.1 Info and relationships | Supports | Semantic headings, lists, tables with `<th>`, labelled form controls (axe) |
| 1.3.2 Meaningful sequence | Supports | DOM order equals visual order (code review) |
| 1.3.3 Sensory characteristics | Supports | Instructions don't rely on shape, colour or position |
| 1.4.1 Use of colour | Supports | Badges carry text; in-text links underlined (axe: link-in-text-block) |
| 1.4.2 Audio control | Not applicable | No audio |
| 2.1.1 Keyboard | Supports (pending manual verification) | Native buttons, links and form controls only; no click-only elements |
| 2.1.2 No keyboard trap | Supports (pending manual verification) | No custom focus management that could trap |
| 2.1.4 Character key shortcuts | Not applicable | No single-key shortcuts |
| 2.2.1 Timing adjustable | Supports | Idle sign-out warns one minute ahead with "Stay signed in"; timeout configurable (`ADINTEL_SESSION_IDLE_MINUTES`); approvals expire by business rule, shown with the expiry time |
| 2.2.2 Pause, stop, hide | Supports | No auto-moving content; live text updates are user-initiated (runs, chat) |
| 2.3.1 Three flashes | Supports | No flashing content |
| 2.4.1 Bypass blocks | Supports | "Skip to content" link; `<main>` landmark |
| 2.4.2 Page titled | Supports | Distinct title per route (`app.routes.ts`) |
| 2.4.3 Focus order | Supports (pending manual verification) | Follows DOM order |
| 2.4.4 Link purpose (in context) | Supports | Link text describes destination ("Review →", run ids, "full trace →") |
| 2.5.1 Pointer gestures | Not applicable | No multipoint or path gestures |
| 2.5.2 Pointer cancellation | Supports | Native controls activate on up-event |
| 2.5.3 Label in name | Supports | Visible labels match accessible names |
| 2.5.4 Motion actuation | Not applicable | No motion-triggered functions |
| 3.1.1 Language of page | Supports | `<html lang="en">` |
| 3.2.1 On focus | Supports | No context change on focus |
| 3.2.2 On input | Supports | Selecting an option never navigates; filters update content in place |
| 3.3.1 Error identification | Supports | Errors described in text and announced (`role="alert"`); server refusals name the failed check |
| 3.3.2 Labels or instructions | Supports | Every input has a label or accessible name (axe: label, select-name) |
| 4.1.1 Parsing | Supports | Obsolete in WCAG 2.2; Angular emits well-formed markup |
| 4.1.2 Name, role, value | Supports | Native controls; ARIA only for live regions and the idle dialog (axe: aria-*) |

### Level AA

| Criterion | Level | Notes |
|-----------|-------|-------|
| 1.2.4–1.2.5 Captions / audio description | Not applicable | No media |
| 1.3.4 Orientation | Supports | Layout not locked to an orientation |
| 1.3.5 Identify input purpose | Not applicable | No fields collecting the user's personal data (sign-in happens at the identity provider) |
| 1.4.3 Contrast (minimum) | Supports | All text ≥ 4.5:1, verified by axe on every screen |
| 1.4.4 Resize text | Supports (pending manual verification) | rem-based typography, no fixed-height text containers |
| 1.4.5 Images of text | Supports | None used |
| 1.4.10 Reflow | Partially supports | Content reflows at 320 px; wide data tables scroll horizontally inside their panel (data tables are an allowed exception) |
| 1.4.11 Non-text contrast | Supports | Focus outline 3 px in the accent colour (≥ 3:1); control borders visible |
| 1.4.12 Text spacing | Supports (pending manual verification) | No clipped fixed-size text boxes |
| 1.4.13 Content on hover or focus | Not applicable | No tooltips or hover-revealed content |
| 2.4.5 Multiple ways | Supports | Main navigation plus direct links between brands, runs, reports and approvals |
| 2.4.6 Headings and labels | Supports | Descriptive headings per section |
| 2.4.7 Focus visible | Supports | `:focus-visible` outline on every control |
| 3.1.2 Language of parts | Not applicable | Single-language UI |
| 3.2.3 Consistent navigation | Supports | One shell navigation on every screen |
| 3.2.4 Consistent identification | Supports | Same components and wording throughout |
| 3.3.3 Error suggestion | Supports | Validation messages say what to do ("type the daily exposure…", rejection reasons) |
| 3.3.4 Error prevention (legal, financial, data) | Supports | Spending approvals require typing the exact exposure; erasure requires typing the user id twice; both are confirmed before submission and audited |
| 4.1.3 Status messages | Supports | Live regions for chat, run timeline, status banner and confirmations |

## Summary

Level A: 30 criteria — 23 Supports, 7 Not applicable. Level AA: 20 criteria — 14 Supports, 1 Partially
supports (1.4.10, data tables), 5 Not applicable. Five "Supports" entries (2.1.1, 2.1.2, 2.4.3, 1.4.4, 1.4.12)
await the manual assistive-technology walkthrough; that walkthrough (script below) is the one remaining step before issuing this report externally.

## Manual verification script (≈ 45 minutes)

With VoiceOver (macOS, Safari) and NVDA (Windows, Firefox), keyboard only: sign in → open a brand → start a
run and listen to the timeline → open the recommendation, type the exposure, approve → open the report and
its provenance line → ask a chat question and hear the streamed answer → let the session idle until the
warning and choose "Stay signed in" → zoom to 200 % and 400 % and check reflow. Record any issue against the
criterion above and update this file.
