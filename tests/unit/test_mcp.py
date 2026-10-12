"""MCP server: read-only, same identity and scope as the web app, outputs fenced as data."""

import io
import json

import pytest

from adintel.approvals.service import load_user
from adintel.connectors.synthetic import reset_world
from adintel.mcp.server import FENCE, TOOLS, Backend, MCPServer, serve
from adintel.security.auth import issue_token
from adintel.seed.catalog import seed


@pytest.fixture
def server(db, mock_llm):
    reset_world()
    seed(db, with_kb=False)
    return MCPServer(Backend(issue_token(load_user(db, "brightwave", "u_jordan"))))


def call(srv, name, args=None, mid=1):
    return srv.handle(
        {"jsonrpc": "2.0", "id": mid, "method": "tools/call", "params": {"name": name, "arguments": args or {}}}
    )


def test_handshake_and_tool_list(server):
    init = server.handle(
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18"}}
    )
    assert init["result"]["protocolVersion"] == "2025-06-18" and "tools" in init["result"]["capabilities"]
    assert server.handle({"jsonrpc": "2.0", "method": "notifications/initialized"}) is None
    tools = server.handle({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})["result"]["tools"]
    assert {t["name"] for t in tools} == set(TOOLS) and all(t["annotations"]["readOnlyHint"] for t in tools)
    assert not any(w in " ".join(TOOLS) for w in ("approve", "reject", "run_", "set_", "delete"))


def test_scope_is_the_users_scope(server):
    r = call(server, "list_brands")["result"]
    assert not r["isError"] and r["content"][0]["text"].startswith(FENCE)
    brands = {b["brand_id"] for b in json.loads(r["content"][0]["text"].split("\n\n", 1)[1])}
    assert brands == {"urban-roast", "fitely"}  # Jordan's brands only
    denied = call(server, "brand_summary", {"brand_id": "northpeak"})["result"]  # Priya's brand
    assert denied["isError"] and "refused" in denied["content"][0]["text"]
    other_tenant = call(server, "brand_summary", {"brand_id": "harbor-bikes"})["result"]
    assert other_tenant["isError"]


def test_bad_calls_are_errors_not_crashes(server):
    assert call(server, "approve_recommendation")["result"]["isError"]
    assert "invalid arguments" in call(server, "brand_summary", {"brand": "x"})["result"]["content"][0]["text"]
    assert server.handle({"jsonrpc": "2.0", "id": 9, "method": "resources/list"})["error"]["code"] == -32601


def test_stdio_transport_round_trip(server):
    lines = (
        "\n".join(
            json.dumps(m)
            for m in (
                {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
                {"jsonrpc": "2.0", "method": "notifications/initialized"},
                {
                    "jsonrpc": "2.0",
                    "id": 2,
                    "method": "tools/call",
                    "params": {"name": "list_anomalies", "arguments": {}},
                },
            )
        )
        + "\nnot json\n"
    )
    out = io.StringIO()
    serve(server, io.StringIO(lines), out)
    replies = [json.loads(x) for x in out.getvalue().splitlines()]
    assert [r.get("id") for r in replies] == [1, 2, None] and replies[2]["error"]["code"] == -32700
