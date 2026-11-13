"""The concierge service behind the API: runs turns and builds the trip view.

Wraps the web concierge agent in an ADK Runner with one session per client id.
Sessions (messages + trip-board state) are stored in the database at
SESSION_DB_URL (Postgres in compose) and survive restarts; unset, they live in
memory. Uploaded files are ADK artifacts of the session under UPLOAD_DIR.

Everything the frontend shows is derived from the stored session, so a reload
gets the same conversation, sources and trip board back.
"""

import asyncio
import os
import time
import uuid
from pathlib import Path
from typing import AsyncIterator

from google.adk.agents.run_config import RunConfig, StreamingMode
from google.adk.artifacts import BaseArtifactService, FileArtifactService
from google.adk.events import Event, EventActions
from google.adk.runners import Runner
from google.adk.sessions import BaseSessionService, InMemorySessionService
from google.genai import types

from trip_concierge import accounts
from trip_concierge.concierge_agent import root_agent
from trip_concierge.connectors import CONNECTORS, STATE_PREFIX, connectors_view
from trip_concierge.timeline import ITEMS_KEY, new_item, notifications, with_item
from trip_concierge.trip_board import trip_view

APP = "trip_concierge_web"
_DEFAULT_UPLOAD_DIR = Path(__file__).resolve().parent.parent / "uploads"
_SIGN_IN_TTL = 600  # seconds a started OAuth sign-in stays valid


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
        # OAuth sign-ins in progress, by one-time state. In memory: a sign-in started
        # before a restart must be retried (shortcut: one API process; use a shared
        # store if the API ever runs as several replicas).
        self._pending: dict[str, dict] = {}

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
            return {"messages": [], "trip": {}, "documents": documents, "connectors": connectors_view({}), "notifications": []}
        trip = trip_view(session.state)
        return {
            "messages": turns_from_events(session.events),
            "trip": trip,
            "documents": documents,
            "connectors": connectors_view(session.state),
            "notifications": notifications(trip.get("items", []), trip.get("reminders", [])),
        }

    async def add_item(self, client_id: str, **fields) -> dict:
        """Add a timeline item (raises ValueError on bad input); returns {trip, notifications}."""
        item = new_item(**fields)
        session = await self._sessions.get_session(app_name=APP, user_id=client_id, session_id=client_id)
        items = (session.state.get(ITEMS_KEY, []) if session else [])
        await self._update_state(client_id, {ITEMS_KEY: with_item(items, item)})
        view = await self.view(client_id)
        return {"trip": view["trip"], "notifications": view["notifications"]}

    async def remove_item(self, client_id: str, item_id: str) -> dict:
        session = await self._sessions.get_session(app_name=APP, user_id=client_id, session_id=client_id)
        items = session.state.get(ITEMS_KEY, []) if session else []
        if not any(i["id"] == item_id for i in items):
            raise KeyError(item_id)
        await self._update_state(client_id, {ITEMS_KEY: [i for i in items if i["id"] != item_id]})
        view = await self.view(client_id)
        return {"trip": view["trip"], "notifications": view["notifications"]}

    async def _update_state(self, client_id: str, delta: dict) -> None:
        """Record a state-only event: stored with the session, shows no chat message."""
        await self._session_for(client_id)
        session = await self._sessions.get_session(
            app_name=APP, user_id=client_id, session_id=client_id
        )
        await self._sessions.append_event(
            session,
            Event(
                author="user",
                invocation_id=f"state-{uuid.uuid4().hex}",
                actions=EventActions(state_delta=delta),
            ),
        )

    async def set_connector(self, client_id: str, connector_id: str, connected: bool) -> list[dict]:
        """Turn a connector on or off for this trip; returns all connectors."""
        if connector_id not in CONNECTORS:
            raise KeyError(connector_id)
        await self._update_state(client_id, {STATE_PREFIX + connector_id: connected})
        return (await self.view(client_id))["connectors"]

    # ── OAuth sign-in for connectors ─────────────────────────────────────────

    def oauth_start(self, client_id: str, connector_id: str, provider: str) -> str:
        """Provider sign-in URL; remembers the one-time state for the callback."""
        if connector_id not in CONNECTORS or provider not in accounts.PROVIDERS:
            raise KeyError(f"{provider}/{connector_id}")
        now = time.time()
        for key in [k for k, v in self._pending.items() if v["expires"] < now]:
            del self._pending[key]
        flow = accounts.start(provider, connector_id)
        self._pending[flow["state"]] = {
            "client_id": client_id,
            "connector": connector_id,
            "provider": provider,
            "verifier": flow["verifier"],
            "expires": now + _SIGN_IN_TTL,
        }
        return flow["url"]

    async def oauth_finish(self, state: str, code: str) -> dict:
        """Complete sign-in from the provider callback; returns {connector, account}."""
        flow = self._pending.pop(state, None)  # one-time: a replayed state is rejected
        if not flow or flow["expires"] < time.time():
            raise ValueError("sign-in link expired or already used; please try again")
        record = await asyncio.to_thread(
            accounts.finish, flow["provider"], flow["connector"], code, flow["verifier"]
        )
        await self._update_state(
            flow["client_id"],
            {
                accounts.STATE_PREFIX + flow["connector"]: accounts.seal(record),
                STATE_PREFIX + flow["connector"]: True,  # signing in switches the connector on
            },
        )
        return {"connector": flow["connector"], "account": record["account"]}

    async def disconnect_account(self, client_id: str, connector_id: str) -> list[dict]:
        """Forget the signed-in account (tokens deleted) and switch the connector off."""
        if connector_id not in CONNECTORS:
            raise KeyError(connector_id)
        await self._update_state(
            client_id, {accounts.STATE_PREFIX + connector_id: None, STATE_PREFIX + connector_id: False}
        )
        return (await self.view(client_id))["connectors"]

    async def chat_stream(self, client_id: str, message: str) -> AsyncIterator[dict]:
        """Run one turn, yielding progress as it happens:

        {"type": "tool", "name"}   the agent started a tool call
        {"type": "delta", "text"}  the next piece of reply text
        {"type": "done", "reply", "sources", "trip"}   final, read back from the session
        """
        session_id = await self._session_for(client_id)
        content = types.Content(role="user", parts=[types.Part(text=message)])
        streamed = False  # text already sent as partial chunks for the current response
        async for event in self._runner.run_async(
            user_id=client_id,
            session_id=session_id,
            new_message=content,
            run_config=RunConfig(streaming_mode=StreamingMode.SSE),
        ):
            if not event.partial:  # a streamed call shows up in the partial and final event
                for call in event.get_function_calls():
                    yield {"type": "tool", "name": call.name}
            parts = (event.content.parts if event.content else None) or []
            text = "".join(p.text for p in parts if p.text and not p.thought)
            if event.partial:
                streamed = True
                if text:
                    yield {"type": "delta", "text": text}
            else:
                # The final event of a streamed response repeats its whole text.
                if text and not streamed:
                    yield {"type": "delta", "text": text}
                streamed = False
        view = await self.view(client_id)
        last = next(
            (m for m in reversed(view["messages"]) if m["role"] == "assistant"),
            {"text": "", "sources": []},
        )
        yield {
            "type": "done",
            "reply": last["text"],
            "sources": last["sources"],
            "trip": view["trip"],
            "notifications": view["notifications"],
        }

    async def chat(self, client_id: str, message: str) -> dict:
        """Run one turn; return the reply (with its cited sources) and the updated board."""
        async for item in self.chat_stream(client_id, message):
            if item["type"] == "done":
                return {k: item[k] for k in ("reply", "sources", "trip", "notifications")}
        raise RuntimeError("turn ended without a result")

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
