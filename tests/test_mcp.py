"""Integration test: the MCP server lists and serves the trip tools over stdio.

No API key needed — this exercises the MCP transport end to end, not the LLM.
"""

import asyncio
import json
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

SERVER = StdioServerParameters(command=sys.executable, args=["-m", "mcp_server.server"])


def _unwrap(result):
    if getattr(result, "structuredContent", None):
        sc = result.structuredContent
        return sc.get("result", sc) if isinstance(sc, dict) else sc
    return json.loads(result.content[0].text)


async def _exercise():
    async with stdio_client(SERVER) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            names = {t.name for t in (await session.list_tools()).tools}
            cost = _unwrap(
                await session.call_tool(
                    "estimate_trip_cost",
                    {"city": "Kyoto", "nights": 4, "travelers": 2},
                )
            )
            return names, cost


def test_mcp_server_serves_tools():
    names, cost = asyncio.run(_exercise())
    assert {"find_attractions", "estimate_trip_cost"} <= names
    # 140/day * 4 nights * 2 travellers
    assert cost["estimated_total_usd"] == 140 * 4 * 2
