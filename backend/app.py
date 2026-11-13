"""Trip Concierge API (FastAPI). The UI is the separate app in frontend/.

Routes, all under /api:
  GET  /api/health                  liveness
  GET  /api/sessions/{session_id}   messages (with cited sources), trip board, documents
  POST /api/chat                    {session_id, message} -> {reply, sources, trip}
  POST /api/chat/stream             same body; server-sent events: tool, delta, done | error
  POST /api/upload                  multipart: session_id, file -> {filename, chars, documents}
  PUT  /api/sessions/{session_id}/connectors/{connector_id}   {connected} -> connectors
  DELETE /api/sessions/{session_id}/connectors/{connector_id}/account   sign out
  POST /api/sessions/{session_id}/items     add a train/flight/bus/stay/activity -> {trip, notifications}
  DELETE /api/sessions/{session_id}/items/{item_id}
  GET  /api/seasonal?when=November  destinations in season (and to avoid) for a month or season
  GET  /api/oauth/{provider}/start?session_id=&connector=   redirect to Google/Microsoft
  GET  /api/oauth/callback          provider redirect target (nginx maps /oauth/callback here)

`create_app(service=...)` takes the object that does the work (default: the ADK
ConciergeRunner); injecting a fake keeps the HTTP layer testable without an API key.

Run it:  uvicorn backend.app:app --port 8000
"""

import json
import logging
import re
from pathlib import Path
from typing import Any

from fastapi import APIRouter, FastAPI, Form, HTTPException, UploadFile
from fastapi.responses import RedirectResponse, StreamingResponse
from urllib.parse import urlencode
from pydantic import BaseModel, Field

from trip_concierge.documents import MAX_UPLOAD_BYTES, extract_text
from trip_concierge.seasons import seasonal_destinations

log = logging.getLogger("trip_concierge.api")

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


class ItemIn(BaseModel):
    kind: str
    title: str = Field(min_length=1, max_length=120)
    starts_at: str = Field(min_length=10, max_length=25)
    ends_at: str | None = Field(default=None, max_length=25)
    from_place: str | None = Field(default=None, max_length=80)
    to_place: str | None = Field(default=None, max_length=80)
    reference: str | None = Field(default=None, max_length=40)


class ConnectorIn(BaseModel):
    connected: bool


class ChatOut(BaseModel):
    reply: str
    sources: list[Source]
    trip: dict[str, Any]
    notifications: list[dict[str, Any]] = []


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

    @api.post("/sessions/{session_id}/items")
    async def add_item(session_id: str, body: ItemIn) -> dict:
        try:
            return await service.add_item(_check_session_id(session_id), **body.model_dump())
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc

    @api.delete("/sessions/{session_id}/items/{item_id}")
    async def remove_item(session_id: str, item_id: str) -> dict:
        try:
            return await service.remove_item(_check_session_id(session_id), item_id)
        except KeyError:
            raise HTTPException(404, "no such item") from None

    @api.get("/seasonal")
    async def seasonal(when: str) -> dict:
        result = seasonal_destinations(when)
        if "error" in result:
            raise HTTPException(422, result["error"])
        return result

    @api.delete("/sessions/{session_id}/connectors/{connector_id}/account")
    async def disconnect(session_id: str, connector_id: str) -> list[dict]:
        try:
            return await service.disconnect_account(_check_session_id(session_id), connector_id)
        except KeyError:
            raise HTTPException(404, f"unknown connector {connector_id!r}") from None

    @api.get("/oauth/{provider}/start")
    async def oauth_start(provider: str, session_id: str, connector: str) -> RedirectResponse:
        try:
            url = service.oauth_start(_check_session_id(session_id), connector, provider)
        except KeyError:
            raise HTTPException(404, "unknown provider or connector") from None
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        return RedirectResponse(url, status_code=302)

    @api.get("/oauth/callback")
    async def oauth_callback(
        state: str = "", code: str = "", error: str = "", error_description: str = ""
    ) -> RedirectResponse:
        # Back to the app (same origin via nginx) with the outcome in the query string.
        if error or not code:
            result = {"oauth": "error", "message": error_description or error or "sign-in cancelled"}
        else:
            try:
                done = await service.oauth_finish(state, code)
                result = {"oauth": "connected", **done}
            except Exception as exc:
                log.warning("oauth callback failed: %s", exc)
                result = {"oauth": "error", "message": str(exc)[:200]}
        return RedirectResponse("/?" + urlencode(result), status_code=302)

    @api.post("/chat", response_model=ChatOut)
    async def chat(body: ChatIn) -> dict:
        return await service.chat(body.session_id, body.message)

    @api.post("/chat/stream")
    async def chat_stream(body: ChatIn) -> StreamingResponse:
        async def events():
            try:
                async for item in service.chat_stream(body.session_id, body.message):
                    kind = item.pop("type")
                    yield f"event: {kind}\ndata: {json.dumps(item)}\n\n"
            except Exception:
                log.exception("chat stream failed")
                msg = "The concierge hit an error. Please try again."
                yield f"event: error\ndata: {json.dumps({'message': msg})}\n\n"

        # X-Accel-Buffering stops nginx from holding the stream back.
        return StreamingResponse(
            events(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

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
