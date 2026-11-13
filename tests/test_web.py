"""Web layer tests: static page served and /chat round-trips (no API key).

The reply callable is faked so the HTTP wiring is tested without calling the LLM.
"""

from fastapi.testclient import TestClient

from web.app import create_app


async def _fake_reply(client_id: str, message: str) -> str:
    return f"echo[{client_id}]: {message}"


def _client() -> TestClient:
    return TestClient(create_app(reply=_fake_reply))


def test_index_is_served():
    resp = _client().get("/")
    assert resp.status_code == 200
    assert "Trip Concierge" in resp.text


def test_chat_round_trip():
    resp = _client().post("/chat", json={"session_id": "s1", "message": "hi"})
    assert resp.status_code == 200
    assert resp.json()["reply"] == "echo[s1]: hi"


def test_chat_requires_message():
    resp = _client().post("/chat", json={"session_id": "s1"})
    assert resp.status_code == 422  # message is required
