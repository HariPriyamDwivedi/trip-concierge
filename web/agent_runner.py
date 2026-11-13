"""Session-aware ADK runner for the web layer.

Wraps the Phase 5 concierge agent in an InMemoryRunner and keeps one ADK session
per web client id, so a browser conversation has continuity. Isolated here so the
FastAPI layer depends on a small async `reply` callable, not on ADK directly.
"""

from google.adk.runners import InMemoryRunner
from google.genai import types

from trip_concierge.concierge_agent import root_agent

APP = "trip_concierge_web"


class ConciergeRunner:
    def __init__(self) -> None:
        self._runner = InMemoryRunner(agent=root_agent, app_name=APP)
        self._sessions: dict[str, str] = {}

    async def _session_for(self, client_id: str) -> str:
        if client_id not in self._sessions:
            session = await self._runner.session_service.create_session(
                app_name=APP, user_id=client_id
            )
            self._sessions[client_id] = session.id
        return self._sessions[client_id]

    async def reply(self, client_id: str, message: str) -> str:
        """Run one turn and return the agent's combined text reply."""
        session_id = await self._session_for(client_id)
        content = types.Content(role="user", parts=[types.Part(text=message)])
        parts: list[str] = []
        async for event in self._runner.run_async(
            user_id=client_id, session_id=session_id, new_message=content
        ):
            if event.content and event.content.parts:
                parts.extend(p.text for p in event.content.parts if p.text)
        return "".join(parts).strip()
