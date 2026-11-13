"""Session-aware ADK runner for the web layer.

Wraps the Phase 5 concierge agent in an ADK Runner and keeps one ADK session per
web client id, so a browser conversation has continuity. Isolated here so the
FastAPI layer depends on a small async `reply` callable, not on ADK directly.

Sessions are stored in the database at SESSION_DB_URL (e.g. Postgres, see
compose.yaml) so conversations survive restarts; unset, they live in memory.
Uploaded files are stored as ADK artifacts of the session under UPLOAD_DIR, where
the agent's search_my_documents tool reads them.
"""

import os
from pathlib import Path

from google.adk.artifacts import BaseArtifactService, FileArtifactService
from google.adk.runners import Runner
from google.adk.sessions import BaseSessionService, InMemorySessionService
from google.genai import types

from trip_concierge.concierge_agent import root_agent

APP = "trip_concierge_web"
_DEFAULT_UPLOAD_DIR = Path(__file__).resolve().parent.parent / "uploads"


def make_session_service(db_url: str | None = None) -> BaseSessionService:
    db_url = db_url if db_url is not None else os.getenv("SESSION_DB_URL")
    if not db_url:
        return InMemorySessionService()
    # Imported lazily: needs sqlalchemy + a driver (asyncpg for postgresql+asyncpg://).
    from google.adk.sessions import DatabaseSessionService

    return DatabaseSessionService(db_url=db_url)


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

    async def upload(self, client_id: str, filename: str, text: str) -> dict:
        """Store an uploaded file's text where this session's agent can search it."""
        session_id = await self._session_for(client_id)
        version = await self._artifacts.save_artifact(
            app_name=APP,
            user_id=client_id,
            session_id=session_id,
            filename=filename,
            artifact=types.Part.from_bytes(data=text.encode(), mime_type="text/plain"),
        )
        return {"filename": filename, "chars": len(text), "version": version}

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
