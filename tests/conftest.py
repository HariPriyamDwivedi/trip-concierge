"""Shared fixtures: an API client signed in through the real email-code flow.

Each app gets its own SQLite database and local media folder; the "mailbox"
captures sign-in codes instead of sending email.
"""

import pytest
from fastapi.testclient import TestClient

from backend.app import create_app
from backend.db import Database
from backend.storage import LocalStorage


class Mailbox(list):
    def __call__(self, email, code):
        self.append((email, code))

    def code_for(self, email):
        return [c for e, c in self if e == email.strip().lower()][-1]


def sign_in(client, email="ana@example.test"):
    assert client.post("/api/auth/request-code", json={"identifier": email}).status_code == 200
    resp = client.post("/api/auth/verify", json={"identifier": email, "code": client.mailbox.code_for(email)})
    assert resp.status_code == 200, resp.text
    return resp.json()["user"]


@pytest.fixture
def make_client(tmp_path):
    opened = []

    def _make(service=None, *, signed_in=True, email="ana@example.test", app=None):
        if app is None:
            app = create_app(
                service=service,
                db=Database(f"sqlite+aiosqlite:///{tmp_path}/app-{len(opened)}.db"),
                storage=LocalStorage(tmp_path / "media"),
                code_sender=Mailbox(),
            )
        client = TestClient(app)
        client.__enter__()  # runs startup (creates tables)
        opened.append(client)
        client.mailbox = app.state.code_sender
        client.user = sign_in(client, email) if signed_in else None
        return client

    yield _make
    for c in opened:
        c.__exit__(None, None, None)

