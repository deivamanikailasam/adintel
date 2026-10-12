# 0023 — The Angular 18 frontend

**In one sentence:** account managers and leaders now have a web app to watch runs live, see exactly why
the AI suggested something, approve or reject it, chat about a brand, and — for admins — pull the brakes.

## What changed

- `frontend/` — Angular 18 standalone app (signals, new control flow, lazy routes):
  brands, brand detail (anomalies with dismiss-with-reason, runs, *Run now*), **run detail** (live SSE
  timeline, rule-vs-model decisions, degradations, root cause with the sandboxed queries, every model call
  with its exact prompt and response, sources, audit trail), **approval queue and approval screen**
  (evidence one click away, who may approve, *type the exposure*, reduce, reject with a reason), report
  viewer with rating, streaming chat, and a governance console (audit verification, notional cost, kill
  switches, model health, notifications).
- Security: strict Content-Security-Policy; model output is rendered as escaped text only (no
  `innerHTML`); JWT in session storage with automatic logout on 401; SSE via `fetch` so the token is sent.
- `docs/16-frontend/frontend.md`.

## Why it matters (layman's terms)

A human-approval gate only works if approving properly is quick and approving blindly is impossible. The
screen puts the evidence next to the button and makes you type the dollar amount.

## How to verify

```bash
cd frontend && npm ci && npx ng build && npx ng test --watch=false --browsers=ChromeHeadless
```
