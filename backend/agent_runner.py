"""The concierge service behind the API: runs turns and builds the trip view.

Wraps the web concierge agent in an ADK Runner with one session per client id.
Sessions (messages + trip-board state) are stored in the database at
SESSION_DB_URL (Postgres in compose) and survive restarts; unset, they live in
memory. Uploaded files are ADK artifacts of the session under UPLOAD_DIR.

Everything the frontend shows is derived from the stored session, so a reload
gets the same conversation, sources and trip board back.
"""

import os
import uuid
from pathlib import Path

from google.adk.artifacts import BaseArtifactService, FileArtifactService
from google.adk.events import Event, EventActions
from google.adk.runners import Runner
from google.adk.sessions import BaseSessionService, InMemorySessionService
from google.genai import types

from trip_concierge.concierge_agent import root_agent
from trip_concierge.connectors import CONNECTORS, STATE_PREFIX, connectors_view
from trip_concierge.trip_board import trip_view

APP = "trip_concierge_web"
_DEFAULT_UPLOAD_DIR = Path(__file__).resolve().parent.parent / "uploads"


def make_session_service(db_url: str | None = None) -> BaseSessionService:
    db_url = db_url if db_url is not None else os.getenv("SESSION_DB_URL")
    if not db_url:
        return InMemorySessionService()
    # Imported lazily: needs sqlalchemy + a driver (asyncpg for postgresql+asyncpg://).
    from google.adk.sessions import DatabaseSessionService

    return DatabaseSessionService(db_url=db_url)


def _retrieved(name: str, response: dict) -> list[dict]:
    """Sources a retrieval tool returned: {kind: file|guide|web, label, url?}."""
    if name == "search_my_documents":
        return [{"kind": "file", "label": p["source"]} for p in response.get("passages", [])]
    if name == "search_guides":  # returns a list, which ADK wraps as {"result": [...]}
        return [{"kind": "guide", "label": p["source"]} for p in response.get("result", [])]
    if name == "web_search":
        return [
            {"kind": "web", "label": r.get("title") or r["url"], "url": r["url"]}
            for r in response.get("results", [])
        ]
    return []


def turns_from_events(events: list) -> list[dict]:
    """Chat messages from stored ADK events.

    One user message per user event; one assistant message per invocation with its
    text and the retrieved sources it actually cites (label or URL in the reply).
    """
    turns: list[dict] = []
    current: dict | None = None
    for ev in events:
        parts = (ev.content.parts if ev.content else None) or []
        if ev.author == "user":
            text = "".join(p.text for p in parts if p.text)
            if text:
                turns.append({"role": "user", "text": text})
            current = None
            continue
        if current is None or current["_inv"] != ev.invocation_id:
            current = {"role": "assistant", "text": "", "_found": [], "_inv": ev.invocation_id}
            turns.append(current)
        for p in parts:
            if p.function_response and isinstance(p.function_response.response, dict):
                current["_found"] += _retrieved(p.function_response.name, p.function_response.response)
            elif p.text and not p.thought:
                current["text"] += p.text

    messages = []
    for t in turns:
        if t["role"] == "user":
            messages.append(t)
            continue
        text = t["text"].strip()
        if not text:
            continue
        cited, seen = [], set()
        for s in t["_found"]:
            key = (s["kind"], s.get("url") or s["label"])
            if key not in seen and (s.get("url") or s["label"]) in text:
                seen.add(key)
                cited.append(s)
        messages.append({"role": "assistant", "text": text, "sources": cited})
    return messages


class ConciergeRunner:
    def __init__(
        self,
        session_service: BaseSessionService | None = None,
        artifact_service: BaseArtifactService | None = None,
    ) -> None:
        self._sessions = session_service or make_session_service()
        self._artifacts = artifact_service or FileArtifactService(
            os.getenv("UPLOAD_DIR") or _DEFAULT_UPLOAD_DIR
        )
        self._runner = Runner(
            app_name=APP,
            agent=root_agent,
            session_service=self._sessions,
            artifact_service=self._artifacts,
        )

    async def _session_for(self, client_id: str) -> str:
        # The client id doubles as the session id, so a stored session is found
        # again after a restart without keeping any mapping in memory.
        if not await self._sessions.get_session(
            app_name=APP, user_id=client_id, session_id=client_id
        ):
            await self._sessions.create_session(
                app_name=APP, user_id=client_id, session_id=client_id
            )
        return client_id

    async def view(self, client_id: str) -> dict:
        """The whole conversation: messages, trip board and uploaded documents."""
        session = await self._sessions.get_session(
            app_name=APP, user_id=client_id, session_id=client_id
        )
        documents = await self._artifacts.list_artifact_keys(
            app_name=APP, user_id=client_id, session_id=client_id
        )
        if session is None:
            return {"messages": [], "trip": {}, "documents": documents, "connectors": connectors_view({})}
        return {
            "messages": turns_from_events(session.events),
            "trip": trip_view(session.state),
            "documents": documents,
            "connectors": connectors_view(session.state),
        }

    async def set_connector(self, client_id: str, connector_id: str, connected: bool) -> list[dict]:
        """Turn a connector on or off for this trip; returns all connectors."""
        if connector_id not in CONNECTORS:
            raise KeyError(connector_id)
        await self._session_for(client_id)
        session = await self._sessions.get_session(
            app_name=APP, user_id=client_id, session_id=client_id
        )
        # A state-only event: recorded with the session, shows no chat message.
        await self._sessions.append_event(
            session,
            Event(
                author="user",
                invocation_id=f"connector-{uuid.uuid4().hex}",
                actions=EventActions(state_delta={STATE_PREFIX + connector_id: connected}),
            ),
        )
        return (await self.view(client_id))["connectors"]

    async def chat(self, client_id: str, message: str) -> dict:
        """Run one turn; return the reply (with its cited sources) and the updated board."""
        session_id = await self._session_for(client_id)
        content = types.Content(role="user", parts=[types.Part(text=message)])
        async for _ in self._runner.run_async(
            user_id=client_id, session_id=session_id, new_message=content
        ):
            pass  # everything is recorded on the session; read it back below
        view = await self.view(client_id)
        last = next(
            (m for m in reversed(view["messages"]) if m["role"] == "assistant"),
            {"text": "", "sources": []},
        )
        return {"reply": last["text"], "sources": last["sources"], "trip": view["trip"]}

    async def upload(self, client_id: str, filename: str, text: str) -> dict:
        """Store an uploaded file's text where this session's agent can search it."""
        session_id = await self._session_for(client_id)
        await self._artifacts.save_artifact(
            app_name=APP,
            user_id=client_id,
            session_id=session_id,
            filename=filename,
            artifact=types.Part.from_bytes(data=text.encode(), mime_type="text/plain"),
        )
        documents = await self._artifacts.list_artifact_keys(
            app_name=APP, user_id=client_id, session_id=session_id
        )
        return {"filename": filename, "chars": len(text), "documents": documents}
