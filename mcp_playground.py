"""MCP playground: connect to the local MCP server, list its tools and call them.

No API key needed — this talks straight to the MCP server over stdio, so it's a
quick way to see the tools working on their own.

    python mcp_playground.py
"""

import asyncio
import json
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

SERVER = StdioServerParameters(command=sys.executable, args=["-m", "mcp_server.server"])


def _unwrap(result) -> object:
    """Pull the JSON payload out of an MCP tool result."""
    if getattr(result, "structuredContent", None):
        sc = result.structuredContent
        return sc.get("result", sc) if isinstance(sc, dict) else sc
    return json.loads(result.content[0].text)


async def main() -> None:
    async with stdio_client(SERVER) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            tools = await session.list_tools()
            print("Tools:", [t.name for t in tools.tools])

            got = await session.call_tool("find_attractions", {"city": "Lisbon"})
            print("\nfind_attractions('Lisbon'):")
            print(json.dumps(_unwrap(got), indent=2))

            cost = await session.call_tool(
                "estimate_trip_cost",
                {"city": "Kyoto", "nights": 4, "travelers": 2},
            )
            print("\nestimate_trip_cost('Kyoto', 4, 2):")
            print(json.dumps(_unwrap(cost), indent=2))


if __name__ == "__main__":
    asyncio.run(main())
