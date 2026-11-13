"""Email dry-run and reminder-store tests (no sending, isolated store)."""

import os

from trip_concierge.notifications import send_itinerary
from trip_concierge.reminders import list_reminders, schedule_reminder


def test_email_dry_run_writes_outbox_and_does_not_send(monkeypatch):
    monkeypatch.delenv("TRIP_CONCIERGE_EMAIL_SEND", raising=False)
    result = send_itinerary("traveller@example.com", "Your Kyoto trip", "Day 1: ...")
    assert result["status"] == "dry_run"
    assert os.path.exists(result["saved_to"])
    body = open(result["saved_to"], encoding="utf-8").read()
    assert "traveller@example.com" in body
    assert "Day 1" in body


def test_reminders_persist_and_read_back(tmp_path, monkeypatch):
    store = tmp_path / "reminders.json"
    monkeypatch.setenv("TRIP_CONCIERGE_REMINDERS", str(store))
    assert list_reminders() == {"reminders": []}

    schedule_reminder("Check in for the flight", "2026-05-01T09:00")
    schedule_reminder("Renew travel insurance", "2026-04-20")

    items = list_reminders()["reminders"]
    assert [r["id"] for r in items] == [1, 2]
    assert items[0]["message"] == "Check in for the flight"
