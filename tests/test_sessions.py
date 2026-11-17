"""Web session storage: in-memory by default, a database when SESSION_DB_URL is set,
and a client's session is found again by a fresh runner (i.e. after a restart).
No API key needed — only the session service is exercised, never the LLM.
"""

import asyncio

import pytest
from google.adk.sessions import InMemorySessionService

from backend.agent_runner import APP, ConciergeRunner, make_session_service


def test_defaults_to_in_memory(monkeypatch):
    monkeypatch.delenv("SESSION_DB_URL", raising=False)
    assert isinstance(make_session_service(), InMemorySessionService)


def test_session_for_is_idempotent():
    runner = ConciergeRunner(InMemorySessionService())
    first = asyncio.run(runner._session_for("u1", "trip-abc"))
    again = asyncio.run(runner._session_for("u1", "trip-abc"))
    assert first == again == "trip-abc"


def test_session_survives_new_runner(tmp_path):
    pytest.importorskip("aiosqlite")  # sqlite stands in for Postgres here
    url = f"sqlite+aiosqlite:///{tmp_path / 'sessions.db'}"

    async def scenario():
        await ConciergeRunner(make_session_service(url))._session_for("u1", "trip-abc")
        # A second runner on the same database = the web app after a restart.
        fresh = make_session_service(url)
        await ConciergeRunner(fresh)._session_for("u1", "trip-abc")  # must not re-create
        found = await fresh.get_session(app_name=APP, user_id="u1", session_id="trip-abc")
        listed = await fresh.list_sessions(app_name=APP, user_id="u1")
        return found, listed

    found, listed = asyncio.run(scenario())
    assert found is not None
    assert len(listed.sessions) == 1
