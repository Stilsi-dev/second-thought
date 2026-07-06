"""Thin sync wrapper around a real MCP stdio client (Day 2). Every tool call
spawns/talks to decision_concierge/mcp_server/server.py over the Model Context
Protocol. If the subprocess or the `mcp` package is unavailable, we fall back
to calling the same tool functions in-process — the orchestrator never has to
care which path executed, only that the tool contract was honored.
"""

import asyncio
import json
import sys
from pathlib import Path

SERVER_SCRIPT = Path(__file__).resolve().parent / "mcp_server" / "server.py"


async def _call_via_mcp(tool_name: str, arguments: dict) -> dict:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    params = StdioServerParameters(command=sys.executable, args=[str(SERVER_SCRIPT)])
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(tool_name, arguments)
            text = result.content[0].text if result.content else "{}"
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                return {"raw": text}


def _call_local_fallback(tool_name: str, arguments: dict) -> dict:
    from .mcp_server import server as local

    fn = getattr(local, tool_name)
    return fn(**arguments)


def call_tool(tool_name: str, arguments: dict) -> dict:
    try:
        return asyncio.run(_call_via_mcp(tool_name, arguments))
    except Exception:
        return _call_local_fallback(tool_name, arguments)
