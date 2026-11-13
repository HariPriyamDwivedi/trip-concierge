"""MCP server exposing the trip-concierge tools over stdio.

Reuses the exact tool logic from `trip_concierge.tools` so there is a single
source of truth; this module only adds the MCP wiring. Any MCP client (the ADK
agent in `trip_concierge/mcp_agent.py`, the playground, Claude Desktop, etc.)
can consume these tools.

Run standalone:  python -m mcp_server.server
"""

from mcp.server.fastmcp import FastMCP

from trip_concierge.tools import estimate_trip_cost as _estimate_trip_cost
from trip_concierge.tools import find_attractions as _find_attractions

mcp = FastMCP("trip-tools")


@mcp.tool()
def find_attractions(city: str) -> dict:
    """Return notable attractions for a city, or the supported cities if unknown."""
    return _find_attractions(city)


@mcp.tool()
def estimate_trip_cost(city: str, nights: int, travelers: int) -> dict:
    """Estimate a rough total trip cost in USD from per-city daily rates."""
    return _estimate_trip_cost(city, nights, travelers)


if __name__ == "__main__":
    mcp.run()
