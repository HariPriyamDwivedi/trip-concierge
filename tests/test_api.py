"""API tests with a fake concierge service: trips, chat (plain and streamed),
documents, validation. Users sign in through the real email-code flow.
"""

import pytest


class FakeService:
    def __init__(self):
        self.uploads: list[tuple] = []

    async def set_user_timezone(self, user_id, trip_id, tz):
        pass

    async def view(self, user_id, trip_id):
        return {"messages": [], "trip": {}, "documents": [], "connectors": [], "notifications": []}

    async def chat(self, user_id, trip_id, message):
        return {"reply": f"echo[{trip_id}]: {message}", "sources": [{"kind": "guide", "label": "kyoto"}],
                "trip": {"city": "Kyoto"}, "notifications": []}

    async def chat_stream(self, user_id, trip_id, message):
        yield {"type": "tool", "name": "search_guides"}
        yield {"type": "delta", "text": "Take "}
        yield {"type": "delta", "text": "buses."}
        yield {"type": "done", "reply": "Take buses.", "sources": [], "trip": {"city": "Kyoto"}, "notifications": []}

    async def upload(self, user_id, trip_id, filename, text):
        self.uploads.append((trip_id, filename, text))
        return {"filename": filename, "chars": len(text), "documents": [filename]}


@pytest.fixture
def svc():
    return FakeService()


@pytest.fixture
def client(make_client, svc):
    return make_client(svc)


@pytest.fixture
def trip(client):
    return client.post("/api/trips", json={}).json()["id"]


def test_health_and_seasonal_are_public(make_client):
    anon = make_client(FakeService(), signed_in=False)
    assert anon.get("/api/health").json() == {"ok": True}
    assert anon.get("/api/seasonal?when=dec").json()["months"] == ["December"]
    assert anon.get("/api/seasonal?when=xyz").status_code == 422


def test_everything_else_needs_sign_in(make_client):
    anon = make_client(FakeService(), signed_in=False)
    for method, path in [("get", "/api/me"), ("get", "/api/trips"), ("post", "/api/trips"), ("get", "/api/media"),
                         ("get", "/api/places"), ("get", "/api/trips/trip-x")]:
        assert getattr(anon, method)(path).status_code == 401, path


def test_trip_lifecycle_and_title_from_chat(client, trip):
    assert client.post(f"/api/trips/{trip}/chat", json={"message": "hi"}).json()["reply"] == f"echo[{trip}]: hi"
    listed = client.get("/api/trips").json()
    assert [(t["id"], t["title"], t["status"]) for t in listed] == [(trip, "Kyoto trip", "planning")]
    assert client.patch(f"/api/trips/{trip}", json={"title": "Spring in Kyoto"}).json()["title"] == "Spring in Kyoto"
    assert client.get(f"/api/trips/{trip}").json()["trip_meta"]["title"] == "Spring in Kyoto"


@pytest.mark.parametrize("body", [{}, {"message": ""}, {"message": "x" * 4001}])
def test_chat_rejects_bad_input(client, trip, body):
    assert client.post(f"/api/trips/{trip}/chat", json=body).status_code == 422


def test_chat_stream_sends_server_sent_events(client, trip):
    with client.stream("POST", f"/api/trips/{trip}/chat/stream", json={"message": "hi"}) as resp:
        assert resp.headers["content-type"].startswith("text/event-stream")
        body = "".join(resp.iter_text())
    events = [b.split("\n")[0].removeprefix("event: ") for b in body.strip().split("\n\n")]
    assert events == ["tool", "delta", "delta", "done"]
    assert 'data: {"text": "buses."}' in body


def test_chat_stream_reports_failures_as_an_event(make_client):
    class Broken(FakeService):
        async def chat_stream(self, user_id, trip_id, message):
            yield {"type": "tool", "name": "search_guides"}
            raise RuntimeError("model down")

    client = make_client(Broken())
    trip = client.post("/api/trips", json={}).json()["id"]
    with client.stream("POST", f"/api/trips/{trip}/chat/stream", json={"message": "hi"}) as resp:
        body = "".join(resp.iter_text())
    assert "event: error" in body and "model down" not in body  # no internals leaked


def test_document_upload_extracts_text(client, svc, trip):
    resp = client.post(f"/api/trips/{trip}/documents", files={"file": ("../../hotel notes.txt", b"Check-in 3pm", "text/plain")})
    assert resp.status_code == 200
    assert svc.uploads == [(trip, "hotel notes.txt", "Check-in 3pm")]  # path parts stripped


@pytest.mark.parametrize("name, data, status", [("virus.exe", b"MZ", 422), ("big.txt", b"x" * (5 * 2**20 + 1), 413)])
def test_document_upload_rejects_bad_input(client, svc, trip, name, data, status):
    assert client.post(f"/api/trips/{trip}/documents", files={"file": (name, data)}).status_code == status
    assert svc.uploads == []
