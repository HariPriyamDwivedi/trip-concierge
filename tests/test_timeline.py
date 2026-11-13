"""Trip timeline alerts (ixigo / ConfirmTkt / hostel-style) and season-wise picks."""

import asyncio
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from google.adk.artifacts import InMemoryArtifactService
from google.adk.sessions import InMemorySessionService

from backend.agent_runner import ConciergeRunner
from backend.app import create_app
from trip_concierge.seasons import seasonal_destinations
from trip_concierge.timeline import add_trip_item, new_item, notifications


def _alerts(item):
    return {n["title"]: (n["due_at"], n["body"]) for n in notifications([item])}


def test_train_gets_chart_boarding_and_wake_up_alerts():
    train = new_item("train", "Shatabdi 12002", "2027-03-14T06:00", "2027-03-14T14:10", "New Delhi", "Kalka", "4521337890")
    a = _alerts(train)
    assert a["Chart prepared soon"][0] == "2027-03-14T02:00" and "4521337890" in a["Chart prepared soon"][1]
    assert a["Time to board"][0] == "2027-03-14T05:30"
    assert a["Wake up — your stop is near"] == ("2027-03-14T13:40", "Shatabdi 12002 reaches Kalka at 14:10. Get your bags ready.")
    assert a["Your trip starts tomorrow"][0] == "2027-03-13T06:00"


def test_flight_stay_activity_alerts():
    flight = _alerts(new_item("flight", "6E 2131", "2027-03-14T09:00", "2027-03-14T11:30", "DEL", "GOI", "PNR7Q"))
    assert flight["Web check-in is open"][0] == "2027-03-13T09:00"
    assert flight["Boarding soon"][0] == "2027-03-14T08:15" and flight["Landed"][0] == "2027-03-14T11:30"
    stay = _alerts(new_item("stay", "goSTOPS Goa", "2027-03-14T14:00", "2027-03-17T11:00", "Anjuna"))
    assert stay["Check-in today"] == ("2027-03-14T11:00", "goSTOPS Goa: check-in from 14:00.")  # no empty "Booking ." text
    assert stay["Check-out soon"][0] == "2027-03-17T09:00"
    act = _alerts(new_item("activity", "Sunset kayak", "2027-03-15T17:00", from_place="Chapora"))
    assert act["Starting in an hour"] == ("2027-03-15T16:00", "Sunset kayak at 17:00 at Chapora.")


def test_alerts_without_arrival_skip_arrival_rules():
    titles = [n["title"] for n in notifications([new_item("bus", "Volvo to Manali", "2027-03-14T20:00")])]
    assert "Time to board" in titles and "Arriving soon" not in titles


@pytest.mark.parametrize(
    "args",
    [("boat", "x", "2027-03-14T10:00"), ("train", " ", "2027-03-14T10:00"), ("train", "x", "not a date"),
     ("train", "x", "2027-03-14T10:00", "2027-03-14T09:00")],
)
def test_bad_items_are_rejected(args):
    with pytest.raises(ValueError):
        new_item(*args)


def test_agent_tool_adds_sorted_items_and_reports_errors():
    ctx = SimpleNamespace(state={})
    add_trip_item("activity", "Dinner", "2027-03-15T20:00", ctx)
    add_trip_item("train", "Shatabdi", "2027-03-14T06:00", ctx)
    assert [i["title"] for i in ctx.state["trip_items"]] == ["Shatabdi", "Dinner"]
    assert "error" in add_trip_item("train", "x", "tomorrow morning", ctx)


def test_items_api_round_trip():
    client = TestClient(create_app(service=ConciergeRunner(InMemorySessionService(), InMemoryArtifactService())))
    body = {"kind": "train", "title": "Shatabdi", "starts_at": "2027-03-14T06:00", "ends_at": "2027-03-14T14:10", "to_place": "Kalka"}
    added = client.post("/api/sessions/trip-t1/items", json=body).json()
    item = added["trip"]["items"][0]
    assert any(n["title"] == "Time to board" for n in added["notifications"])
    assert client.get("/api/sessions/trip-t1").json()["notifications"] == added["notifications"]
    assert client.post("/api/sessions/trip-t1/items", json={**body, "kind": "boat"}).status_code == 422
    assert client.delete(f"/api/sessions/trip-t1/items/{item['id']}").json()["trip"]["items"] == []
    assert client.delete("/api/sessions/trip-t1/items/nope").status_code == 404


def test_seasonal_destinations():
    nov = seasonal_destinations("November")
    names = {d["name"] for d in nov["in_season"]}
    assert {"Goa", "Jaipur", "Kyoto"} <= names and "Leh-Ladakh" not in names
    monsoon = seasonal_destinations("monsoon")
    assert "Goa" in {d["name"] for d in monsoon["avoid"]} and "Leh-Ladakh" in {d["name"] for d in monsoon["in_season"]}
    assert seasonal_destinations("11")["months"] == ["November"]
    assert "error" in seasonal_destinations("someday")
    client = TestClient(create_app(service=object()))
    assert client.get("/api/seasonal?when=dec").json()["months"] == ["December"]
    assert client.get("/api/seasonal?when=xyz").status_code == 422
