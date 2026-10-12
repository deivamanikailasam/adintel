"""Conformance: drive the AdIntel MCP server with the official MCP Python SDK client over real stdio.

Skipped when the SDK isn't installed (`pip install -e ".[mcp]"`); CI installs it.
"""

import asyncio
import json
import os
import sys
from pathlib import Path

import pytest

mcp = pytest.importorskip("mcp")
from mcp.client.stdio import stdio_client  # noqa: E402

from mcp import ClientSession, StdioServerParameters  # noqa: E402

LAUNCHER = Path(__file__).with_name("launch_demo_server.py")


def attr(obj, *names):
    """SDK 1.x uses the wire names (camelCase), 2.x snake_case — accept both."""
    for n in names:
        if hasattr(obj, n):
            return getattr(obj, n)
    raise AttributeError(names)


def run(coro):
    return asyncio.run(asyncio.wait_for(coro, timeout=120))


async def _session(user, fn):
    env = {**os.environ, "DEMO_USER": user, "ADINTEL_STORAGE": "memory", "ADINTEL_LOG_LEVEL": "WARNING"}
    # the server may run in another environment than the client (to test old/new SDK clients against it)
    server_python = os.environ.get("ADINTEL_MCP_SERVER_PYTHON", sys.executable)
    params = StdioServerParameters(command=server_python, args=[str(LAUNCHER)], env=env, cwd=str(LAUNCHER.parents[2]))
    async with stdio_client(params) as (read, write), ClientSession(read, write) as session:
        init = await session.initialize()
        return await fn(session, init)


def test_sdk_client_handshake_lists_read_only_tools():
    async def fn(session, init):
        tools = await session.list_tools()
        return init, tools

    init, tools = run(_session("u_jordan", fn))
    assert attr(init, "server_info", "serverInfo").name == "adintel" and init.capabilities.tools is not None
    names = {t.name for t in tools.tools}
    assert {"list_brands", "brand_summary", "explain_recommendation"} <= names
    assert all(t.annotations and attr(t.annotations, "read_only_hint", "readOnlyHint") for t in tools.tools)


def test_sdk_client_calls_tools_with_the_users_scope():
    async def fn(session, init):
        mine = await session.call_tool("list_brands", {})
        other = await session.call_tool("brand_summary", {"brand_id": "northpeak"})
        return mine, other

    mine, other = run(_session("u_jordan", fn))
    assert not attr(mine, "is_error", "isError")
    payload = json.loads(mine.content[0].text.split("\n\n", 1)[1])
    assert {b["brand_id"] for b in payload} == {"urban-roast", "fitely"}
    assert attr(other, "is_error", "isError") and "refused" in other.content[0].text
