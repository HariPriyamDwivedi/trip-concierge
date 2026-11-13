"""Calendar tests: stub free slots, Google wiring (fake transport), opt-in guard."""

from trip_concierge import calendar as cal


def test_stub_free_slots_excludes_busy(monkeypatch):
    monkeypatch.delenv("TRIP_CONCIERGE_CALENDAR", raising=False)
    result = cal.free_slots("2026-05-01")
    assert result["provider"] == "stub"
    # 10:00, 11:00, 15:00 are busy in the stub.
    assert "10:00" not in result["free_slots"]
    assert "09:00" in result["free_slots"]


def test_google_busy_parsed_from_transport():
    def fake_transport(url, body, token):
        assert token == "tok"
        return {"calendars": {"primary": {"busy": [{"start": "2026-05-01T14:00:00Z"}]}}}

    busy = cal._busy_from_google("2026-05-01", "tok", transport=fake_transport)
    assert busy == {"14:00"}


def test_google_without_token_returns_error(monkeypatch):
    monkeypatch.setenv("TRIP_CONCIERGE_CALENDAR", "google")
    monkeypatch.delenv("GOOGLE_CALENDAR_TOKEN", raising=False)
    assert "error" in cal.free_slots("2026-05-01")
