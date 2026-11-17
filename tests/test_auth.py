"""Email / user-ID one-time-code sign-in, profile, and keeping users' trips apart."""

from fastapi.testclient import TestClient

from tests.conftest import sign_in
from tests.test_api import FakeService


def test_first_sign_in_creates_account_with_user_id(make_client):
    c = make_client(FakeService(), email="Priya.Sharma@Example.test")
    assert c.user["email"] == "priya.sharma@example.test"
    assert c.user["username"] == "priya.sharma"
    me = c.get("/api/me").json()
    assert me["user"]["id"] == c.user["id"] and me["stats"] == {"trips": 0, "memories": 0, "places": 0}


def test_sign_in_with_user_id_sends_code_to_the_email(make_client):
    c = make_client(FakeService())
    c.post("/api/auth/logout")
    assert c.get("/api/me").status_code == 401
    c.post("/api/auth/request-code", json={"identifier": "ana"})
    code = c.mailbox.code_for("ana@example.test")  # delivered to the account's email
    resp = c.post("/api/auth/verify", json={"identifier": "ana", "code": code})
    assert resp.status_code == 200 and resp.json()["user"]["email"] == "ana@example.test"


def test_unknown_user_id_gets_the_same_answer_and_no_email(make_client):
    c = make_client(FakeService(), signed_in=False)
    sent = len(c.mailbox)
    assert c.post("/api/auth/request-code", json={"identifier": "nobody_here"}).json() == {"ok": True}
    assert len(c.mailbox) == sent


def test_codes_are_one_time_limited_and_rate_limited(make_client):
    c = make_client(FakeService(), signed_in=False)
    c.post("/api/auth/request-code", json={"identifier": "bo@example.test"})
    code = c.mailbox.code_for("bo@example.test")
    assert c.post("/api/auth/request-code", json={"identifier": "bo@example.test"}).status_code == 429  # 30 s cooldown
    wrong = "000000" if code != "000000" else "111111"
    for _ in range(5):
        assert c.post("/api/auth/verify", json={"identifier": "bo@example.test", "code": wrong}).status_code == 400
    # after 5 wrong tries even the right code is refused
    assert c.post("/api/auth/verify", json={"identifier": "bo@example.test", "code": code}).status_code == 400


def test_code_cannot_be_reused(make_client):
    c = make_client(FakeService(), signed_in=False)
    c.post("/api/auth/request-code", json={"identifier": "cy@example.test"})
    code = c.mailbox.code_for("cy@example.test")
    assert c.post("/api/auth/verify", json={"identifier": "cy@example.test", "code": code}).status_code == 200
    assert c.post("/api/auth/verify", json={"identifier": "cy@example.test", "code": code}).status_code == 400


def test_session_cookie_is_httponly(make_client):
    c = make_client(FakeService(), signed_in=False)
    c.post("/api/auth/request-code", json={"identifier": "di@example.test"})
    resp = c.post("/api/auth/verify", json={"identifier": "di@example.test", "code": c.mailbox.code_for("di@example.test")})
    cookie = resp.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=lax" in cookie


def test_profile_update_and_user_id_rules(make_client):
    a = make_client(FakeService())
    b = make_client(app=a.app, email="ben@example.test")
    assert a.patch("/api/me", json={"name": "Ana D", "timezone": "Asia/Kolkata", "home_city": "Pune"}).status_code == 200
    me = a.get("/api/me").json()["user"]
    assert (me["name"], me["timezone"], me["home_city"]) == ("Ana D", "Asia/Kolkata", "Pune")
    assert a.patch("/api/me", json={"timezone": "Mars/Base"}).status_code == 422
    assert a.patch("/api/me", json={"username": "x"}).status_code == 422
    assert b.patch("/api/me", json={"username": "ana"}).status_code == 409  # taken
    assert a.patch("/api/me", json={"username": "ana_travels"}).json()["user"]["username"] == "ana_travels"


def test_users_cannot_see_each_others_trips(make_client):
    a = make_client(FakeService())
    b = make_client(app=a.app, email="ben@example.test")
    trip = a.post("/api/trips", json={"title": "Goa"}).json()["id"]
    assert b.get(f"/api/trips/{trip}").status_code == 404
    assert b.post(f"/api/trips/{trip}/chat", json={"message": "hi"}).status_code == 404
    assert b.get("/api/trips").json() == []
    assert [t["title"] for t in a.get("/api/trips").json()] == ["Goa"]


def test_dev_fixed_code_only_without_real_email(make_client, monkeypatch):
    monkeypatch.setenv("DEV_FIXED_OTP", "123456")
    monkeypatch.delenv("SMTP_HOST", raising=False)
    c = make_client(FakeService(), signed_in=False)
    c.post("/api/auth/request-code", json={"identifier": "fx@example.test"})
    assert c.mailbox.code_for("fx@example.test") == "123456"
    assert c.post("/api/auth/verify", json={"identifier": "fx@example.test", "code": "123456"}).status_code == 200
    # with a real email sender configured, the fixed code is ignored
    monkeypatch.setenv("SMTP_HOST", "smtp.example.test")
    from backend import auth
    assert auth.dev_fixed_code() is None
