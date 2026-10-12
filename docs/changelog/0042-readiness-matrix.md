# 0042 — One page that says what is ready, and what is still a decision

**In one sentence:** a single checklist now shows, for every capability an enterprise agentic AI system
needs, how AdIntel does it locally, which alternatives you can swap in, what production uses, where the
proof is, and what still depends on the owner rather than on code.

## What changed

- `docs/14-production/production-readiness-matrix.md` — agentic core, models, data, security and identity,
  governance/audit/privacy, quality and learning, operations; status ✅ / 🟡 / ⬜ with evidence links, and
  the known limits of a single-machine setup (admin screens for flags/triage/privacy are API + CLI only).
- Linked from the docs index and the top of the promotion guide.
- README: the new capabilities (SSO, learning loop, data lifecycle, local alternatives), the local ↔
  production table rows for identity, audit archive and ad data, and current test/matrix counts.

## Why it matters (layman's terms)

Before a building opens, an inspector walks through with a clipboard. This is that clipboard: every line
says what's there, how it was checked, and — just as importantly — what the owner still has to sign
(contracts, a licence, a penetration test, people on call) because no amount of code can do it for them.
