# Frontend (Angular 18)

Standalone components, signals and the new control flow (`@if`, `@for`), lazy-loaded routes.

| Page | Route | What it does |
|------|-------|--------------|
| Login | `/login` | Local dev login by seeded user (Cognito hosted UI in production) |
| Brands | `/brands` | Brands in your scope with last-run status and health |
| Brand | `/brands/:id` | Open anomalies (dismiss with a reason → procedural memory), runs, **Run now** |
| Run | `/runs/:id` | **Live SSE timeline**, orchestrator decisions (rule vs model), degradations, root cause with the sandboxed queries, every model call with the **exact prompt and response**, retrieved sources, audit trail |
| Approvals | `/approvals` | Queue of pending recommendations; learned-rule proposals |
| Recommendation | `/approvals/:id` | Proposal, evidence one click away, who may approve, **type the exposure to approve**, reduce the amount, reject with a reason |
| Report | `/reports/:id` | Sections (rendered as escaped text), grounding badge, footer, 1–5 rating |
| Chat | `/chat` | Streaming chat per brand; shows route/tier/cached; blocked output replaced by a refusal |
| Governance | `/admin` | Audit-chain verification, notional cost by agent, kill switches, model registry health, notifications |
| Learning & rollout | `/admin/learning` | Weekly triage with suggested actions, 14-day outcomes of executed changes (graded), feature flags with brand/tenant overrides (changes: admin only, reason audited) |
| Privacy requests | `/admin/privacy` | Admin only: export everything held about a user (download JSON) or erase them; erasure needs the user id typed twice and is refused on your own account |

## Security choices

- **Model output is never rendered as HTML** — Angular interpolation only (escaped); no `innerHTML`, no
  `bypassSecurityTrust*`. Strict CSP in `src/index.html` (and at the CDN in production).
- JWT kept in `sessionStorage` (cleared with the tab); 401 → logout via the interceptor.
- SSE over `fetch` (`core/sse.ts`) so the Authorization header is sent (EventSource can't).

## Commands

```bash
cd frontend
npm ci
npm start                      # http://localhost:4200, proxies /api → http://127.0.0.1:8000
npx ng build --configuration production
npx ng test --watch=false --browsers=ChromeHeadless
```

Accessibility (WCAG 2.1 AA target) and session security (idle timeout, refresh, IdP logout):
[accessibility-and-sessions.md](accessibility-and-sessions.md).
