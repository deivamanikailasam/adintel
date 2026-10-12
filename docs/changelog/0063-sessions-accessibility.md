# 0063 — Sessions that end when they should, and a UI everyone can use

**In one sentence:** the web app now signs people out after inactivity or when their session expires (and
also at the company's sign-in service), and it works properly with keyboards and screen readers.

## What changed

- `core/auth.service.ts` — idle timeout from `/auth/config` (`ADINTEL_SESSION_IDLE_MINUTES`, default 30);
  token expiry scheduling; SSO refresh a minute before expiry with the refresh token kept in memory only;
  RP-initiated logout at the identity provider; the sign-in page shows why the last session ended.
- Accessibility: accessible names for every control, skip link, `aria-label` on navigation, live regions for
  chat, run timeline and the status banner, visible focus outlines, reduced-motion support.
- `/auth/config` returns the session settings.
- Docs: `docs/16-frontend/accessibility-and-sessions.md` (including known gaps and how to produce a
  conformance report). Tests: `auth.service.spec.ts` (3 new; 8 frontend tests total).

## Why it matters (layman's terms)

A shared office computer left signed in is an open door; now it locks itself. And enterprise buyers must
make their tools usable by everyone — someone navigating by keyboard or listening with a screen reader can
now follow a run, read a chat answer and approve a change.
