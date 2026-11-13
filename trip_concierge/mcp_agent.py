"""A trip concierge whose tools are served over MCP instead of in-process.

Same behaviour as the Phase 1 agent, but the tools are provided by the local
MCP server (`mcp_server.server`) over stdio via ADK's McpToolset. This is the
Phase 2 demonstration of consuming MCP tools from an ADK agent.

`root_agent` here is an alternative entry point; `adk run trip_concierge` still
uses the in-process Phase 1 agent.
"""

import os
import sys

from google.adk.agents import Agent
from google.adk.tools.mcp_tool import McpToolset, StdioConnectionParams
from mcp import StdioServerParameters

from .agent import MODEL

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def trip_tools_toolset() -> McpToolset:
    """Launch the local MCP server over stdio and expose its tools to ADK."""
    return McpToolset(
        connection_params=StdioConnectionParams(
            server_params=StdioServerParameters(
                command=sys.executable,
                args=["-m", "mcp_server.server"],
                cwd=_PROJECT_ROOT,
            )
        )
    )


root_agent = Agent(
    name="trip_concierge_mcp",
    model=MODEL,
    description="A trip concierge that gets its tools from the MCP server.",
    instruction=(
        "You are a trip concierge. Use find_attractions for what-to-do and "
        "itinerary questions, and estimate_trip_cost for budget questions. Ask "
        "for any missing detail, then answer warmly and briefly."
    ),
    tools=[trip_tools_toolset()],
)
