"""Coordinator that calls the budget specialist over A2A.

Same concierge as Phase 1, but the `budget` sub-agent is a RemoteA2aAgent
pointing at the service in `budget_service.py` rather than an in-process agent.
Start that service first (see its module docstring), then run this agent.

`root_agent` here is an alternative entry point; it needs the budget service
reachable at BUDGET_AGENT_URL (default http://localhost:8001).
"""

import os

from google.adk.agents import Agent
from google.adk.agents.remote_a2a_agent import (
    AGENT_CARD_WELL_KNOWN_PATH,
    RemoteA2aAgent,
)

from .agent import MODEL, make_guide, make_planner

_BUDGET_URL = os.getenv("BUDGET_AGENT_URL", "http://localhost:8001")

remote_budget = RemoteA2aAgent(
    name="budget",
    agent_card=f"{_BUDGET_URL}{AGENT_CARD_WELL_KNOWN_PATH}",
    description="Estimates the rough cost of a trip (served over A2A).",
)

root_agent = Agent(
    name="trip_concierge_a2a",
    model=MODEL,
    description="A trip concierge that calls a remote budget specialist over A2A.",
    instruction=(
        "You are a trip concierge. Delegate what-to-do and itinerary questions "
        "to 'guide' and 'planner', and cost questions to the remote 'budget' "
        "specialist. Keep replies warm and brief."
    ),
    sub_agents=[make_guide(), remote_budget, make_planner()],
)
