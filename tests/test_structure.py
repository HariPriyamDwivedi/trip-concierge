"""Smoke tests: agent tree wiring and tool logic (no network / API key needed)."""

from trip_concierge import root_agent
from trip_concierge.tools import estimate_trip_cost, find_attractions


def test_agent_tree():
    assert root_agent.name == "trip_concierge"
    names = {a.name for a in root_agent.sub_agents}
    assert names == {"guide", "budget", "planner"}


def test_specialists_have_tools():
    for agent in root_agent.sub_agents:
        assert agent.tools, f"{agent.name} should expose at least one tool"


def test_find_attractions_known_and_unknown():
    hit = find_attractions("Kyoto")
    assert hit["found"] is True
    assert len(hit["attractions"]) >= 3

    miss = find_attractions("Atlantis")
    assert miss["found"] is False
    assert "Lisbon" in miss["supported_cities"]


def test_estimate_trip_cost_math_and_validation():
    est = estimate_trip_cost("Lisbon", nights=3, travelers=2)
    assert est["estimated_total_usd"] == 110 * 3 * 2

    assert "error" in estimate_trip_cost("Lisbon", nights=0, travelers=1)
    assert "error" in estimate_trip_cost("Nowhere", nights=2, travelers=1)
