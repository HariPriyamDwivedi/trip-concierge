"""Mail/Calendar connectors: off by default, guard blocks their tools until the
traveller turns them on for the trip, and the switch persists in the session.
"""

import asyncio
from types import SimpleNamespace

from google.adk.artifacts import InMemoryArtifactService
from google.adk.sessions import InMemorySessionService

from backend.agent_runner import ConciergeRunner
from trip_concierge.connectors import connectors_view, guard_connectors


def _guard(tool_name, state):
    return guard_connectors(SimpleNamespace(name=tool_name), {}, SimpleNamespace(state=state))


def test_guard_blocks_connector_tools_until_connected():
    assert "Calendar connector is off" in _guard("free_slots", {})["error"]
    assert "Mail connector is off" in _guard("send_itinerary", {})["error"]
    assert _guard("free_slots", {"connector_calendar": True}) is None
    assert _guard("send_itinerary", {"connector_mail": True}) is None
    assert _guard("find_attractions", {}) is None  # trip tools never need a connector


def test_view_describes_trip_purpose_and_safe_defaults(monkeypatch):
    for var in ("TRIP_CONCIERGE_CALENDAR", "TRIP_CONCIERGE_EMAIL_SEND", "SMTP_HOST"):
        monkeypatch.delenv(var, raising=False)
    view = {c["id"]: c for c in connectors_view({})}
    assert set(view) == {"calendar", "mail"}
    assert not any(c["connected"] for c in view.values())
    assert view["mail"]["mode"] == "demo" and "nothing is sent" in view["mail"]["provider"]
    assert "travel dates" in view["calendar"]["purpose"]


def test_switch_persists_in_the_session():
    runner = ConciergeRunner(InMemorySessionService(), InMemoryArtifactService())
    after_on = asyncio.run(runner.set_connector("u1", "trip-1", "calendar", True))
    assert {c["id"]: c["connected"] for c in after_on} == {"calendar": True, "mail": False}
    view = asyncio.run(runner.view("u1", "trip-1"))
    assert [c["connected"] for c in view["connectors"] if c["id"] == "calendar"] == [True]
    assert view["messages"] == []  # toggling adds no chat message
    asyncio.run(runner.set_connector("u1", "trip-1", "calendar", False))
    assert not any(c["connected"] for c in asyncio.run(runner.view("u1", "trip-1"))["connectors"])


def test_api_route(make_client):
    client = make_client(ConciergeRunner(InMemorySessionService(), InMemoryArtifactService()))
    trip = client.post("/api/trips", json={}).json()["id"]
    resp = client.put(f"/api/trips/{trip}/connectors/mail", json={"connected": True})
    assert resp.status_code == 200
    assert {c["id"]: c["connected"] for c in resp.json()}["mail"] is True
    assert client.put(f"/api/trips/{trip}/connectors/slack", json={"connected": True}).status_code == 404
    assert client.put("/api/trips/trip-not-mine/connectors/mail", json={"connected": True}).status_code == 404
