"""A2A wiring tests: the budget service serves a valid agent card, and the A2A
coordinator wires the budget specialist as a remote agent.

No API key needed — the agent card is served from metadata, and RemoteA2aAgent
connects lazily, so neither path calls the LLM.
"""

from google.adk.agents.remote_a2a_agent import RemoteA2aAgent
from starlette.testclient import TestClient

from budget_service import app
from trip_concierge.a2a_agent import root_agent


def test_budget_service_serves_agent_card():
    with TestClient(app) as client:
        resp = client.get("/.well-known/agent-card.json")
    assert resp.status_code == 200
    card = resp.json()
    assert card["name"] == "budget"
    assert card["skills"]


def test_coordinator_uses_remote_budget():
    budget = next(a for a in root_agent.sub_agents if a.name == "budget")
    assert isinstance(budget, RemoteA2aAgent)
    # guide and planner remain local
    assert {a.name for a in root_agent.sub_agents} == {"guide", "budget", "planner"}
