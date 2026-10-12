# 0064 — Third gap review: trust, interoperability and day-to-day operability

**In one sentence:** a third pass asked what an enterprise still expects once the system is secure and
running — that other agents can use it safely, that its reports can be proven genuine, that emergencies don't
need standing admin rights, that the machine warns before it fails, that integrations don't break, and that
the UI is safe and usable for everyone — and added each.

| Change | Gap | Now |
|--------|-----|-----|
| [0058](0058-mcp-server.md) | Other AI agents had no governed way in | Read-only MCP server acting as the user |
| [0059](0059-report-provenance.md) | A forwarded report couldn't be proven genuine | Ed25519-signed reports, AI disclosure, public verification |
| [0060](0060-break-glass.md) | Emergencies meant standing admin rights | Two-person / paged break-glass with auto-expiry |
| [0061](0061-host-health-status.md) | Nobody watched the machine's disk and memory | Host alerts and a user-facing status banner |
| [0062](0062-api-versioning.md) | Integrations could break on any release | `/v1` contract with a breaking-change test |
| [0063](0063-sessions-accessibility.md) | Sessions never idled out; UI not accessible | Idle sign-out, refresh, IdP logout; a11y pass |

Checks: ruff, mypy --strict, ~320 backend tests, 8 frontend tests, 10 eval suites and the promotion gate pass.

## Why it matters (layman's terms)

The first reviews made the building safe and keep the lights on. This one is about living in it: visitors
get a badge, documents get a seal, the spare key is behind glass, the fuel gauge is watched, the address
doesn't change, and the doors work for everyone.
