# 0068 — The open items from the third review, closed

| Open item | Closed by | Evidence |
|-----------|-----------|----------|
| Logout and refresh assumed Keycloak URLs | [0065](0065-oidc-discovery.md) OIDC discovery + Cognito logout style | `test_oidc_discovery.py`, `logoutUrl` specs |
| MCP server only tested by its own tests | [0066](0066-mcp-conformance.md) official SDK clients 1.30 and 2.3 over real stdio | `tests/mcp/`, CI `mcp-compat` |
| No formal accessibility audit | [0067](0067-accessibility-audit.md) axe-core WCAG 2.1 A/AA on all 12 screens, fixes, conformance report | `a11y.spec.ts` (0 violations) |

What remains is a human task, not code: the ~45-minute screen-reader walkthrough scripted in the
accessibility conformance report, which turns five "pending manual verification" entries into confirmed ones.

Checks: ruff, mypy --strict, ~325 backend tests (88 % coverage, gate 85 %), 24 frontend tests, MCP SDK 1.x and
2.x conformance — all pass.
