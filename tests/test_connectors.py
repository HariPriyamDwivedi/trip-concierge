"""Mail/Calendar connectors: off by default, guard blocks their tools until the
traveller turns them on for the trip, and the switch persists in the session.
"""

import asyncio
from types import SimpleNamespace

from fastapi.testclient import TestClient
from google.adk.artifacts import InMemoryArtifactService
from google.adk.sessions import InMemorySessionService

from backend.agent_runner import ConciergeRunner
from backend.app import create_app
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
    after_on = asyncio.run(runner.set_connector("trip-1", "calendar", True))
    assert {c["id"]: c["connected"] for c in after_on} == {"calendar": True, "mail": False}
    view = asyncio.run(runner.view("trip-1"))
    assert [c["connected"] for c in view["connectors"] if c["id"] == "calendar"] == [True]
    assert view["messages"] == []  # toggling adds no chat message
    asyncio.run(runner.set_connector("trip-1", "calendar", False))
    assert not any(c["connected"] for c in asyncio.run(runner.view("trip-1"))["connectors"])


def test_api_route():
    runner = ConciergeRunner(InMemorySessionService(), InMemoryArtifactService())
    client = TestClient(create_app(service=runner))
    resp = client.put("/api/sessions/trip-2/connectors/mail", json={"connected": True})
    assert resp.status_code == 200
    assert {c["id"]: c["connected"] for c in resp.json()}["mail"] is True
    assert client.put("/api/sessions/trip-2/connectors/slack", json={"connected": True}).status_code == 404
    assert client.put("/api/sessions/bad%20id/connectors/mail", json={"connected": True}).status_code == 422
