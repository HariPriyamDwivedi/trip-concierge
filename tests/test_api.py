"""API tests: routes, validation and upload handling (no API key).

The concierge service is faked so the HTTP layer is tested without calling the LLM.
"""

import pytest
from fastapi.testclient import TestClient

from backend.app import create_app


class FakeService:
    def __init__(self):
        self.uploads: list[tuple] = []

    async def view(self, session_id):
        return {"messages": [], "trip": {}, "documents": [], "id": session_id}

    async def chat(self, session_id, message):
        return {
            "reply": f"echo[{session_id}]: {message}",
            "sources": [{"kind": "guide", "label": "kyoto"}],
            "trip": {"city": "Kyoto"},
        }

    async def upload(self, session_id, filename, text):
        self.uploads.append((session_id, filename, text))
        return {"filename": filename, "chars": len(text), "documents": [filename]}


@pytest.fixture
def svc():
    return FakeService()


@pytest.fixture
def client(svc):
    return TestClient(create_app(service=svc))


def test_health(client):
    assert client.get("/api/health").json() == {"ok": True}


def test_chat_round_trip(client):
    resp = client.post("/api/chat", json={"session_id": "s1", "message": "hi"})
    assert resp.status_code == 200
    assert resp.json() == {
        "reply": "echo[s1]: hi",
        "sources": [{"kind": "guide", "label": "kyoto", "url": None}],
        "trip": {"city": "Kyoto"},
        "notifications": [],
    }


@pytest.mark.parametrize(
    "body",
    [{"session_id": "s1"}, {"session_id": "s1", "message": ""}, {"session_id": "../x", "message": "hi"}],
)
def test_chat_rejects_bad_input(client, body):
    assert client.post("/api/chat", json=body).status_code == 422


def test_session_view(client):
    assert client.get("/api/sessions/web-1").json()["id"] == "web-1"
    assert client.get("/api/sessions/bad%20id").status_code == 422


def test_upload_extracts_and_stores_text(client, svc):
    resp = client.post(
        "/api/upload",
        data={"session_id": "web-s1"},
        files={"file": ("../../hotel notes.txt", b"Check-in 3pm", "text/plain")},
    )
    assert resp.status_code == 200
    assert svc.uploads == [("web-s1", "hotel notes.txt", "Check-in 3pm")]  # path parts stripped


@pytest.mark.parametrize(
    "session_id, name, data, status",
    [
        ("web-s1", "virus.exe", b"MZ", 422),  # file type not allowed
        ("web-s1", "big.txt", b"x" * (5 * 2**20 + 1), 413),  # over 5 MB
        ("../etc", "a.txt", b"hi", 422),  # unsafe session id
    ],
)
def test_upload_rejects_bad_input(client, svc, session_id, name, data, status):
    resp = client.post("/api/upload", data={"session_id": session_id}, files={"file": (name, data)})
    assert resp.status_code == status
    assert svc.uploads == []


def test_chat_stream_sends_server_sent_events():
    class StreamSvc(FakeService):
        async def chat_stream(self, session_id, message):
            yield {"type": "tool", "name": "search_guides"}
            yield {"type": "delta", "text": "Take "}
            yield {"type": "delta", "text": "buses."}
            yield {"type": "done", "reply": "Take buses.", "sources": [], "trip": {}}

    with TestClient(create_app(service=StreamSvc())).stream(
        "POST", "/api/chat/stream", json={"session_id": "s1", "message": "hi"}
    ) as resp:
        assert resp.headers["content-type"].startswith("text/event-stream")
        body = "".join(resp.iter_text())
    events = [b.split("\n")[0].removeprefix("event: ") for b in body.strip().split("\n\n")]
    assert events == ["tool", "delta", "delta", "done"]
    assert 'data: {"text": "buses."}' in body


def test_chat_stream_reports_failures_as_an_event():
    class Broken(FakeService):
        async def chat_stream(self, session_id, message):
            yield {"type": "tool", "name": "search_guides"}
            raise RuntimeError("model down")

    with TestClient(create_app(service=Broken())).stream(
        "POST", "/api/chat/stream", json={"session_id": "s1", "message": "hi"}
    ) as resp:
        body = "".join(resp.iter_text())
    assert "event: error" in body and "model down" not in body  # no internals leaked
