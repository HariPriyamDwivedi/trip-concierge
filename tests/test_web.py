"""Web layer tests: static page served, /chat round-trips, /upload validates (no API key).

The reply and upload callables are faked so the HTTP wiring is tested without calling the LLM.
"""

import pytest
from fastapi.testclient import TestClient

from web.app import create_app


async def _fake_reply(client_id: str, message: str) -> str:
    return f"echo[{client_id}]: {message}"


uploads: list[tuple] = []


async def _fake_upload(client_id: str, filename: str, text: str) -> dict:
    uploads.append((client_id, filename, text))
    return {"filename": filename, "chars": len(text)}


def _client() -> TestClient:
    return TestClient(create_app(reply=_fake_reply, upload=_fake_upload))


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


def test_upload_extracts_and_stores_text():
    uploads.clear()
    resp = _client().post(
        "/upload",
        data={"session_id": "web-s1"},
        files={"file": ("../../hotel notes.txt", b"Check-in 3pm", "text/plain")},
    )
    assert resp.status_code == 200
    assert uploads == [("web-s1", "hotel notes.txt", "Check-in 3pm")]  # path parts stripped


@pytest.mark.parametrize(
    "session_id, name, data, status",
    [
        ("web-s1", "virus.exe", b"MZ", 422),  # file type not allowed
        ("web-s1", "big.txt", b"x" * (5 * 2**20 + 1), 413),  # over 5 MB
        ("../etc", "a.txt", b"hi", 422),  # unsafe session id
    ],
)
def test_upload_rejects_bad_input(session_id, name, data, status):
    uploads.clear()
    resp = _client().post("/upload", data={"session_id": session_id}, files={"file": (name, data)})
    assert resp.status_code == status
    assert uploads == []
