"""OAuth sign-in for the Mail/Calendar connectors, and the tools using the signed-in
account. Every provider call goes through a fake transport: no network, no real keys.
"""

import asyncio
import base64
import json
import time
import urllib.parse
from types import SimpleNamespace

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from google.adk.artifacts import InMemoryArtifactService
from google.adk.sessions import InMemorySessionService

from backend.agent_runner import APP, ConciergeRunner
from backend.app import create_app
from trip_concierge import accounts, calendar, notifications


@pytest.fixture(autouse=True)
def oauth_env(monkeypatch):
    monkeypatch.setenv("ENCRYPTION_KEY", Fernet.generate_key().decode())
    for p in ("GOOGLE", "MICROSOFT"):
        monkeypatch.setenv(f"{p}_CLIENT_ID", f"{p.lower()}-client")
        monkeypatch.setenv(f"{p}_CLIENT_SECRET", "secret")


def _id_token(email):
    claims = base64.urlsafe_b64encode(json.dumps({"email": email}).encode()).decode().rstrip("=")
    return f"h.{claims}.s"


def _query(url):
    return dict(urllib.parse.parse_qsl(urllib.parse.urlparse(url).query))


def test_one_sign_in_asks_for_calendar_and_mail_with_minimal_scopes():
    flow = accounts.start("google")
    q = _query(flow["url"])
    # free/busy only + send only — one consent covers both connectors
    assert q["scope"] == "openid email https://www.googleapis.com/auth/calendar.freebusy https://www.googleapis.com/auth/gmail.send"
    assert q["state"] == flow["state"] and q["code_challenge_method"] == "S256"
    assert q["redirect_uri"] == "http://localhost:8080/oauth/callback"
    ms = _query(accounts.start("microsoft")["url"])
    assert ms["scope"] == "openid email offline_access Calendars.Read Mail.Send"
    # Microsoft: no forced consent (it turns into "admin approval required" in many tenants)
    assert ms["prompt"] == "select_account" and "access_type" not in ms
    assert (q["prompt"], q["access_type"]) == ("select_account consent", "offline")  # Google still gets a refresh token


def test_no_sign_in_without_encryption_key(monkeypatch):
    monkeypatch.delenv("ENCRYPTION_KEY")
    assert accounts.available_providers() == []
    with pytest.raises(ValueError):
        accounts.start("google")


def test_finish_stores_encrypted_record_and_view_hides_tokens():
    sent = {}

    def transport(url, fields):
        sent.update(fields)
        return {"access_token": "ya29.secret-access-token", "refresh_token": "RT", "expires_in": 3600, "id_token": _id_token("me@x.test")}

    rec = accounts.finish("google", "CODE", "VERIFIER", transport=transport)
    assert sent["code_verifier"] == "VERIFIER" and rec["account"] == "me@x.test"
    blob = accounts.seal(rec)
    assert "secret-access-token" not in blob  # encrypted at rest
    view = accounts.account_view({"user:account_google": blob}, "google")
    assert view == {"provider": "google", "label": "Google", "account": "me@x.test"}


def test_finish_reports_provider_error():
    with pytest.raises(ValueError, match="bad code"):
        accounts.finish("google", "X", "V", transport=lambda u, f: {"error": "invalid_grant", "error_description": "bad code"})


def test_access_token_refreshes_and_writes_back():
    old = {"provider": "microsoft", "account": "a@b", "access_token": "OLD", "refresh_token": "RT", "expires_at": time.time() - 5}
    state = {"user:account_microsoft": accounts.seal(old)}
    got = accounts.access_token(state, "microsoft", transport=lambda u, f: {"access_token": "NEW", "expires_in": 3600})
    assert got == ("microsoft", "NEW", "a@b")
    assert accounts.unseal(state["user:account_microsoft"])["access_token"] == "NEW"


def _record(provider, who="me@x.test", token="AT"):
    return accounts.seal({"provider": provider, "account": who, "access_token": token, "refresh_token": "RT", "expires_at": time.time() + 3600})


def _signed_in(*providers, **extra):
    state = {f"user:account_{p}": _record(p, f"me@{p}.test", f"AT-{p}") for p in providers}
    return SimpleNamespace(state={**state, **extra})


def test_busy_hours_cover_whole_meetings():
    busy = calendar._busy_hours("2027-03-14", [("2027-03-14T10:30:00Z", "2027-03-14T12:15:00Z")])
    assert busy == {"10:00", "11:00", "12:00"}


def test_free_slots_reads_connected_microsoft_calendar(monkeypatch):
    def graph(method, url, token, body):
        assert token == "AT-microsoft" and "calendarView" in url
        return {"value": [{"start": {"dateTime": "2027-03-14T09:00:00.0000000"}, "end": {"dateTime": "2027-03-14T11:00:00.0000000"}, "showAs": "busy"},
                          {"start": {"dateTime": "2027-03-14T14:00:00.0000000"}, "end": {"dateTime": "2027-03-14T15:00:00.0000000"}, "showAs": "free"}]}

    monkeypatch.setattr(calendar, "api_request", graph)
    got = calendar.free_slots("2027-03-14", _signed_in("microsoft"))
    assert got["provider"] == "Microsoft Calendar (me@microsoft.test)"
    assert "09:00" not in got["free_slots"] and "10:00" not in got["free_slots"] and "14:00" in got["free_slots"]


def test_free_slots_merges_google_and_microsoft(monkeypatch):
    monkeypatch.setattr(calendar, "api_request", lambda m, u, t, b: {"value": [
        {"start": {"dateTime": "2027-03-14T09:00:00"}, "end": {"dateTime": "2027-03-14T10:00:00"}, "showAs": "busy"}]})
    monkeypatch.setattr(calendar, "_busy_from_google", lambda date, token: {"15:00"} if token == "AT-google" else set())
    got = calendar.free_slots("2027-03-14", _signed_in("google", "microsoft"))
    assert got["provider"] == "Google Calendar (me@google.test) + Microsoft Calendar (me@microsoft.test)"
    assert "09:00" not in got["free_slots"] and "15:00" not in got["free_slots"] and "12:00" in got["free_slots"]


def test_free_slots_keeps_working_if_one_calendar_fails(monkeypatch):
    def broken(*a):
        raise RuntimeError("token revoked")

    monkeypatch.setattr(calendar, "api_request", broken)
    monkeypatch.setattr(calendar, "_busy_from_google", lambda date, token: {"15:00"})
    got = calendar.free_slots("2027-03-14", _signed_in("google", "microsoft"))
    assert got["provider"] == "Google Calendar (me@google.test)" and "Microsoft" in got["warning"]


def test_send_itinerary_uses_the_chosen_mailbox(monkeypatch):
    calls = []
    monkeypatch.setattr(accounts, "api_request", lambda *a: calls.append(a) or {})
    got = notifications.send_itinerary("friend@x.test", "Kyoto", "Day 1 ...", _signed_in("google"))
    assert got == {"status": "sent", "to": "friend@x.test", "subject": "Kyoto", "from": "me@google.test"}
    method, url, token, body = calls[0]
    assert url.endswith("/gmail/v1/users/me/messages/send") and token == "AT-google"
    assert b"To: friend@x.test" in base64.urlsafe_b64decode(body["raw"])
    # both connected, Microsoft chosen as sender -> Graph sendMail
    notifications.send_itinerary("friend@x.test", "Kyoto", "b", _signed_in("google", "microsoft", **{"user:mail_from": "microsoft"}))
    assert calls[-1][1].endswith("/me/sendMail") and calls[-1][2] == "AT-microsoft"
    # one recipient only: no lists, no header tricks
    assert "error" in notifications.send_itinerary("a@x.test, b@x.test", "s", "b", _signed_in("google"))
    assert len(calls) == 2


def test_runner_one_sign_in_connects_both_and_providers_stack(monkeypatch):
    runner = ConciergeRunner(InMemorySessionService(), InMemoryArtifactService())
    monkeypatch.setattr(
        accounts, "finish",
        lambda p, code, v: {"provider": p, "account": f"me@{p}.test", "access_token": "AT", "refresh_token": None, "expires_at": time.time() + 3600},
    )
    state = _query(runner.oauth_start("u1", "trip-1", "google"))["state"]
    assert asyncio.run(runner.oauth_finish(state, "CODE")) == {"provider": "google", "account": "me@google.test", "trip_id": "trip-1"}
    with pytest.raises(ValueError):  # the state is one-time
        asyncio.run(runner.oauth_finish(state, "CODE"))
    view = asyncio.run(runner.view("u1", "trip-1"))
    conns = {c["id"]: c for c in view["connectors"]}
    assert conns["calendar"]["connected"] and conns["mail"]["connected"]  # one sign-in, both on
    assert conns["calendar"]["mode"] == conns["mail"]["mode"] == "live"
    assert view["accounts"]["mail_from"] == "google"

    # connect Microsoft as well: both accounts listed, calendar reads both, sender stays Google
    state = _query(runner.oauth_start("u1", "trip-1", "microsoft"))["state"]
    asyncio.run(runner.oauth_finish(state, "CODE"))
    view = asyncio.run(runner.view("u1", "trip-1"))
    assert [p["account"]["account"] for p in view["accounts"]["providers"] if p["account"]] == ["me@google.test", "me@microsoft.test"]
    assert {c["id"]: c for c in view["connectors"]}["calendar"]["provider"] == "Google · me@google.test + Microsoft · me@microsoft.test"
    assert view["accounts"]["mail_from"] == "google"
    switched = asyncio.run(runner.set_mail_from("u1", "trip-1", "microsoft"))
    assert switched["accounts"]["mail_from"] == "microsoft"
    assert {c["id"]: c for c in switched["connectors"]}["mail"]["provider"] == "Sends from me@microsoft.test (Microsoft)"

    # sign out of Microsoft: sender falls back to Google
    after = asyncio.run(runner.disconnect_account("u1", "trip-1", "microsoft"))
    assert after["accounts"]["mail_from"] == "google"
    with pytest.raises(KeyError):
        asyncio.run(runner.set_mail_from("u1", "trip-1", "microsoft"))


def test_callback_route_redirects_back_to_app():
    class Svc:
        async def oauth_finish(self, state, code):
            if state != "good":
                raise ValueError("sign-in link expired")
            return {"provider": "google", "account": "me@x.test", "trip_id": "trip-1"}

    client = TestClient(create_app(service=Svc()), follow_redirects=False)
    ok = client.get("/api/oauth/callback?state=good&code=c")
    assert ok.status_code == 302 and _query(ok.headers["location"]) == {"oauth": "connected", "provider": "google", "account": "me@x.test", "trip_id": "trip-1"}
    bad = client.get("/api/oauth/callback?state=old&code=c")
    assert _query(bad.headers["location"])["oauth"] == "error"
    denied = client.get("/api/oauth/callback?error=access_denied")
    assert _query(denied.headers["location"]) == {"oauth": "error", "message": "access_denied"}
