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


def test_start_uses_pkce_and_minimal_scopes():
    flow = accounts.start("google", "mail")
    q = _query(flow["url"])
    assert q["scope"] == "openid email https://www.googleapis.com/auth/gmail.send"  # send only
    assert q["state"] == flow["state"] and q["code_challenge_method"] == "S256"
    assert q["redirect_uri"] == "http://localhost:8080/oauth/callback"
    ms = _query(accounts.start("microsoft", "calendar")["url"])
    assert ms["scope"] == "openid email offline_access Calendars.Read"


def test_no_sign_in_without_encryption_key(monkeypatch):
    monkeypatch.delenv("ENCRYPTION_KEY")
    assert accounts.available_providers() == []
    with pytest.raises(ValueError):
        accounts.start("google", "mail")


def test_finish_stores_encrypted_record_and_view_hides_tokens():
    sent = {}

    def transport(url, fields):
        sent.update(fields)
        return {"access_token": "ya29.secret-access-token", "refresh_token": "RT", "expires_in": 3600, "id_token": _id_token("me@x.test")}

    rec = accounts.finish("google", "calendar", "CODE", "VERIFIER", transport=transport)
    assert sent["code_verifier"] == "VERIFIER" and rec["account"] == "me@x.test"
    blob = accounts.seal(rec)
    assert "secret-access-token" not in blob  # encrypted at rest
    view = accounts.account_view({"account_calendar": blob}, "calendar")
    assert view == {"provider": "google", "label": "Google", "account": "me@x.test"}


def test_finish_reports_provider_error():
    with pytest.raises(ValueError, match="bad code"):
        accounts.finish("google", "mail", "X", "V", transport=lambda u, f: {"error": "invalid_grant", "error_description": "bad code"})


def test_access_token_refreshes_and_writes_back():
    old = {"provider": "microsoft", "account": "a@b", "access_token": "OLD", "refresh_token": "RT", "expires_at": time.time() - 5}
    state = {"account_mail": accounts.seal(old)}
    got = accounts.access_token(state, "mail", transport=lambda u, f: {"access_token": "NEW", "expires_in": 3600})
    assert got == ("microsoft", "NEW", "a@b")
    assert accounts.unseal(state["account_mail"])["access_token"] == "NEW"


def _signed_in(connector, provider="google"):
    rec = {"provider": provider, "account": "me@x.test", "access_token": "AT", "refresh_token": "RT", "expires_at": time.time() + 3600}
    return SimpleNamespace(state={f"account_{connector}": accounts.seal(rec)})


def test_busy_hours_cover_whole_meetings():
    busy = calendar._busy_hours("2027-03-14", [("2027-03-14T10:30:00Z", "2027-03-14T12:15:00Z")])
    assert busy == {"10:00", "11:00", "12:00"}


def test_free_slots_reads_connected_microsoft_calendar(monkeypatch):
    def graph(method, url, token, body):
        assert token == "AT" and "calendarView" in url
        return {"value": [{"start": {"dateTime": "2027-03-14T09:00:00.0000000"}, "end": {"dateTime": "2027-03-14T11:00:00.0000000"}, "showAs": "busy"},
                          {"start": {"dateTime": "2027-03-14T14:00:00.0000000"}, "end": {"dateTime": "2027-03-14T15:00:00.0000000"}, "showAs": "free"}]}

    monkeypatch.setattr(calendar, "api_request", graph)
    got = calendar.free_slots("2027-03-14", _signed_in("calendar", "microsoft"))
    assert got["provider"] == "Microsoft Calendar (me@x.test)"
    assert "09:00" not in got["free_slots"] and "10:00" not in got["free_slots"] and "14:00" in got["free_slots"]


def test_send_itinerary_uses_gmail_when_signed_in(monkeypatch):
    calls = []
    monkeypatch.setattr(accounts, "api_request", lambda *a: calls.append(a) or {})
    got = notifications.send_itinerary("friend@x.test", "Kyoto", "Day 1 ...", _signed_in("mail"))
    assert got == {"status": "sent", "to": "friend@x.test", "subject": "Kyoto", "from": "me@x.test"}
    method, url, token, body = calls[0]
    assert url.endswith("/gmail/v1/users/me/messages/send") and token == "AT"
    assert b"To: friend@x.test" in base64.urlsafe_b64decode(body["raw"])
    # one recipient only: no lists, no header tricks
    assert "error" in notifications.send_itinerary("a@x.test, b@x.test", "s", "b", _signed_in("mail"))
    assert len(calls) == 1


def test_runner_sign_in_flow(monkeypatch):
    runner = ConciergeRunner(InMemorySessionService(), InMemoryArtifactService())
    url = runner.oauth_start("trip-1", "mail", "google")
    state = _query(url)["state"]
    monkeypatch.setattr(
        accounts, "finish",
        lambda p, c, code, v: {"provider": p, "account": "me@x.test", "access_token": "AT", "refresh_token": None, "expires_at": time.time() + 3600},
    )
    assert asyncio.run(runner.oauth_finish(state, "CODE")) == {"connector": "mail", "account": "me@x.test"}
    with pytest.raises(ValueError):  # the state is one-time
        asyncio.run(runner.oauth_finish(state, "CODE"))
    mail = {c["id"]: c for c in asyncio.run(runner.view("trip-1"))["connectors"]}["mail"]
    assert mail["connected"] and mail["mode"] == "live" and mail["account"]["account"] == "me@x.test"
    after = {c["id"]: c for c in asyncio.run(runner.disconnect_account("trip-1", "mail"))}["mail"]
    assert after["account"] is None and not after["connected"]


def test_callback_route_redirects_back_to_app():
    class Svc:
        async def oauth_finish(self, state, code):
            if state != "good":
                raise ValueError("sign-in link expired")
            return {"connector": "calendar", "account": "me@x.test"}

    client = TestClient(create_app(service=Svc()), follow_redirects=False)
    ok = client.get("/api/oauth/callback?state=good&code=c")
    assert ok.status_code == 302 and _query(ok.headers["location"]) == {"oauth": "connected", "connector": "calendar", "account": "me@x.test"}
    bad = client.get("/api/oauth/callback?state=old&code=c")
    assert _query(bad.headers["location"])["oauth"] == "error"
    denied = client.get("/api/oauth/callback?error=access_denied")
    assert _query(denied.headers["location"]) == {"oauth": "error", "message": "access_denied"}
