# 0058 — Other AI assistants can ask AdIntel, without getting any new powers

**In one sentence:** a person's AI assistant (desktop, IDE or company copilot) can now look up their
brands, anomalies, recommendations and reports in AdIntel through the standard Model Context Protocol — seeing
exactly what that person may see, and unable to approve or change anything.

## What changed

- `mcp/server.py` — stdio MCP server (`python -m adintel.mcp.server`): `initialize`, `tools/list`,
  `tools/call`, `ping`; seven read-only tools mapped to existing GET routes; calls the API in-process (or
  `ADINTEL_MCP_API_URL`) with the user's own token (`ADINTEL_MCP_TOKEN`); results fenced as untrusted data;
  bad calls return tool errors, never crash the session.
- Docs: `docs/17-api/mcp.md` (setup, client config, tools, governance).
- Tests: `tests/unit/test_mcp.py` (handshake, read-only tool set, Jordan sees only Jordan's brands, other
  brands and tenants refused, stdio round trip, parse errors).

## Why it matters (layman's terms)

Instead of giving every robot assistant a master key, AdIntel gives it the person's own visitor badge,
for the reading room only — and every page it hands over is stamped "information, not instructions".
