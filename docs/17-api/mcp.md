# AdIntel as an MCP server (for other AI agents)

Agencies increasingly work through AI assistants. Instead of each assistant scraping the web app or getting
a database login, AdIntel exposes a **read-only Model Context Protocol server** that acts strictly as the
signed-in person.

```bash
ADINTEL_MCP_TOKEN=$(.venv/bin/adintel token --user u_jordan) .venv/bin/python -m adintel.mcp.server
```

Client configuration (e.g. an MCP-capable desktop assistant):

```json
{
  "mcpServers": {
    "adintel": {
      "command": "/path/to/adintel/.venv/bin/python",
      "args": ["-m", "adintel.mcp.server"],
      "env": { "ADINTEL_MCP_TOKEN": "<your AdIntel token>", "ADINTEL_MCP_API_URL": "http://127.0.0.1:8000" }
    }
  }
}
```

Without `ADINTEL_MCP_API_URL` the server runs the API in-process against the configured database.

## Tools

| Tool | What it returns |
|------|-----------------|
| `list_brands` | Brands you can see, with their latest run status |
| `brand_summary` | Recent runs, open anomalies, latest report, constraints |
| `list_anomalies` | Open anomalies, optionally for one brand |
| `list_recommendations` | Proposed changes and their approval state |
| `explain_recommendation` | Root cause, evidence, citations, constraint checks |
| `get_report` | Report sections, caveats, grounding result |
| `get_run` | A run's path, degradations and usage |

## Governance

- **No new authority.** Each call goes through the real API with the user's token: same roles, brand scope
  and tenant isolation as the web app. A viewer's assistant sees what a viewer sees.
- **Read-only by construction.** Only GET routes are mapped; approvals, rejections, runs, kill switches and
  settings are not reachable. Autonomy stays at L2: money moves only after a named person approves in AdIntel.
- **Cross-agent injection hygiene.** Results are prefixed with a notice that strings inside are untrusted
  data, so a hostile campaign name can't masquerade as instructions to the consuming agent.
- **Short-lived tokens.** Use the user's normal (OIDC) token; when they leave, SCIM deactivation stops the
  MCP access on the next call.

Tests: `tests/unit/test_mcp.py`.
