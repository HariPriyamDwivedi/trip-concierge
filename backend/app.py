"""Trip Concierge API (FastAPI). The UI is the separate app in frontend/.

Routes, all under /api:
  GET  /api/health                  liveness
  GET  /api/sessions/{session_id}   messages (with cited sources), trip board, documents
  POST /api/chat                    {session_id, message} -> {reply, sources, trip}
  POST /api/upload                  multipart: session_id, file -> {filename, chars, documents}
  PUT  /api/sessions/{session_id}/connectors/{connector_id}   {connected} -> connectors

`create_app(service=...)` takes the object that does the work (default: the ADK
ConciergeRunner); injecting a fake keeps the HTTP layer testable without an API key.

Run it:  uvicorn backend.app:app --port 8000
"""

import re
from pathlib import Path
from typing import Any

from fastapi import APIRouter, FastAPI, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field

from trip_concierge.documents import MAX_UPLOAD_BYTES, extract_text

# Session ids name storage folders for uploads, so keep them to a safe alphabet.
SESSION_ID_PATTERN = r"^[A-Za-z0-9_-]{1,64}$"


def _check_session_id(session_id: str) -> str:
    if not re.fullmatch(SESSION_ID_PATTERN, session_id):
        raise HTTPException(422, "invalid session_id")
    return session_id


class ChatIn(BaseModel):
    session_id: str = Field(pattern=SESSION_ID_PATTERN)
    message: str = Field(min_length=1, max_length=4000)


class Source(BaseModel):
    kind: str  # file | guide | web
    label: str
    url: str | None = None


class ConnectorIn(BaseModel):
    connected: bool


class ChatOut(BaseModel):
    reply: str
    sources: list[Source]
    trip: dict[str, Any]


def create_app(service: Any = None) -> FastAPI:
    app = FastAPI(title="Trip Concierge API")
    if service is None:
        from .agent_runner import ConciergeRunner

        service = ConciergeRunner()
    api = APIRouter(prefix="/api")

    @api.get("/health")
    async def health() -> dict:
        return {"ok": True}

    @api.get("/sessions/{session_id}")
    async def get_session(session_id: str) -> dict:
        return await service.view(_check_session_id(session_id))

    @api.put("/sessions/{session_id}/connectors/{connector_id}")
    async def set_connector(session_id: str, connector_id: str, body: ConnectorIn) -> list[dict]:
        try:
            return await service.set_connector(_check_session_id(session_id), connector_id, body.connected)
        except KeyError:
            raise HTTPException(404, f"unknown connector {connector_id!r}") from None

    @api.post("/chat", response_model=ChatOut)
    async def chat(body: ChatIn) -> dict:
        return await service.chat(body.session_id, body.message)

    @api.post("/upload")
    async def upload(file: UploadFile, session_id: str = Form(...)) -> dict:
        _check_session_id(session_id)
        name = re.sub(r"[^\w.\- ]", "_", Path(file.filename or "").name)[:100]
        if not name.strip("._ "):
            raise HTTPException(422, "missing file name")
        data = await file.read(MAX_UPLOAD_BYTES + 1)
        if len(data) > MAX_UPLOAD_BYTES:
            raise HTTPException(413, f"file too large (max {MAX_UPLOAD_BYTES // 2**20} MB)")
        try:
            text = extract_text(name, data)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        return await service.upload(session_id, name, text)

    app.include_router(api)
    return app


app = create_app()
