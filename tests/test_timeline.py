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
    assert a["Chart prepared soon"][0] == "2027-03-14T02:00Z" and "4521337890" in a["Chart prepared soon"][1]
    assert a["Time to board"][0] == "2027-03-14T05:30Z"
    assert a["Wake up — your stop is near"] == ("2027-03-14T13:40Z", "Shatabdi 12002 reaches Kalka at 14:10 UTC. Get your bags ready.")
    assert a["Your trip starts tomorrow"][0] == "2027-03-13T06:00Z"


def test_flight_stay_activity_alerts():
    flight = _alerts(new_item("flight", "6E 2131", "2027-03-14T09:00", "2027-03-14T11:30", "DEL", "GOI", "PNR7Q"))
    assert flight["Web check-in is open"][0] == "2027-03-13T09:00Z"
    assert flight["Boarding soon"][0] == "2027-03-14T08:15Z" and flight["Landed"][0] == "2027-03-14T11:30Z"
    stay = _alerts(new_item("stay", "goSTOPS Goa", "2027-03-14T14:00", "2027-03-17T11:00", "Anjuna"))
    assert stay["Check-in today"] == ("2027-03-14T11:00Z", "goSTOPS Goa: check-in from 14:00 UTC.")  # no empty "Booking ." text
    assert stay["Check-out soon"][0] == "2027-03-17T09:00Z"
    act = _alerts(new_item("activity", "Sunset kayak", "2027-03-15T17:00", from_place="Chapora"))
    assert act["Starting in an hour"] == ("2027-03-15T16:00Z", "Sunset kayak at 17:00 UTC at Chapora.")


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


def test_times_are_zoned_and_alerts_are_utc():
    # Delhi 21:30 IST departure, lands Tokyo 09:05 JST next morning
    f = new_item("flight", "AI 306", "2027-03-14T21:30", "2027-03-15T09:05", "Delhi", "Narita", None,
                 "Asia/Kolkata", "Asia/Tokyo")
    assert f["starts_utc"] == "2027-03-14T16:00Z" and f["ends_utc"] == "2027-03-15T00:05Z"
    a = _alerts(f)
    assert a["Leave for the airport"] == ("2027-03-14T13:00Z", "AI 306 departs Delhi at 21:30 IST.")
    assert a["Landed"] == ("2027-03-15T00:05Z", "AI 306 is due in Narita at 09:05 JST.")
    with pytest.raises(ValueError):  # lands before it leaves, once zones are applied
        # 21:30 IST is 16:00Z; 18:00 JST the same day is 09:00Z — before departure
        new_item("flight", "x", "2027-03-14T21:30", "2027-03-14T18:00", start_tz="Asia/Kolkata", end_tz="Asia/Tokyo")
    with pytest.raises(ValueError):
        new_item("train", "x", "2027-03-14T10:00", start_tz="Mars/Olympus")


def test_daylight_saving_is_respected():
    # 09:00 in New York is 13:00Z in summer (EDT) but 14:00Z in winter (EST)
    assert new_item("activity", "a", "2027-07-01T09:00", start_tz="America/New_York")["starts_utc"] == "2027-07-01T13:00Z"
    assert new_item("activity", "b", "2027-01-15T09:00", start_tz="America/New_York")["starts_utc"] == "2027-01-15T14:00Z"


def test_items_api_round_trip(make_client):
    client = make_client(ConciergeRunner(InMemorySessionService(), InMemoryArtifactService()))
    trip = client.post("/api/trips", json={}).json()["id"]
    body = {"kind": "train", "title": "Shatabdi", "starts_at": "2027-03-14T06:00", "ends_at": "2027-03-14T14:10",
            "to_place": "Kalka", "start_tz": "Asia/Kolkata"}
    added = client.post(f"/api/trips/{trip}/items", json=body).json()
    item = added["trip"]["items"][0]
    assert item["end_tz"] == "Asia/Kolkata"  # defaults to the start zone
    board = next(n for n in added["notifications"] if n["title"] == "Time to board")
    assert board["due_at"] == "2027-03-14T00:00Z"  # 05:30 IST
    assert client.get(f"/api/trips/{trip}").json()["notifications"] == added["notifications"]
    listed = {t["id"]: t for t in client.get("/api/trips").json()}[trip]
    assert listed["status"] == "upcoming" and listed["starts_at"].startswith("2027-03-14T00:30")
    assert client.post(f"/api/trips/{trip}/items", json={**body, "kind": "boat"}).status_code == 422
    assert client.delete(f"/api/trips/{trip}/items/{item['id']}").json()["trip"]["items"] == []
    assert client.delete(f"/api/trips/{trip}/items/nope").status_code == 404


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


def test_items_without_a_zone_use_the_profile_zone(make_client):
    client = make_client(ConciergeRunner(InMemorySessionService(), InMemoryArtifactService()))
    client.patch("/api/me", json={"timezone": "Asia/Kolkata"})
    trip = client.post("/api/trips", json={}).json()["id"]
    item = client.post(f"/api/trips/{trip}/items", json={"kind": "activity", "title": "Walk", "starts_at": "2027-03-14T06:00"}).json()["trip"]["items"][0]
    assert (item["start_tz"], item["starts_utc"]) == ("Asia/Kolkata", "2027-03-14T00:30Z")
