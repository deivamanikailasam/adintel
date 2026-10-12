# 0066 — Proven to work with real MCP clients, old and new

**In one sentence:** the AdIntel MCP server is now tested with the official MCP client library — both the
current 2.x and the older 1.x generation many desktop assistants still use — not only with its own tests.

## What changed

- `tests/mcp/test_sdk_conformance.py` + `tests/mcp/launch_demo_server.py` — the SDK's `stdio_client` and
  `ClientSession` start the server as a subprocess (seeded demo data), complete the handshake, list tools
  (all read-only) and call them; Jordan sees only Jordan's brands, other brands are refused.
- Verified: MCP SDK **2.3.0** (asks for protocol `2026-07-28`, accepts our `2025-06-18`) and **1.30.0**.
- `pyproject.toml` extra `mcp` (test-only; the server has no SDK dependency); CI `tests` installs it and a new
  `mcp-compat` job runs an SDK 1.x client against the server; the branch ruleset requires it (sync test).
- Docs: compatibility section in `docs/17-api/mcp.md`.

## Why it matters (layman's terms)

Saying "it speaks the standard" is one thing; having the standard's own reference client hold a full
conversation with it — in two generations — is the proof.
