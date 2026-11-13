"""FastAPI backend + static chat UI for the trip concierge.

`create_app(reply=..., upload=...)` takes the async callables that answer a chat
turn and store an uploaded file; both default to the ADK concierge runner.
Injecting fakes keeps the HTTP layer testable without a Gemini API key.

Run it:  uvicorn web.app:app --port 8000   then open http://localhost:8000
"""

import re
from pathlib import Path
from typing import Awaitable, Callable, Optional

from fastapi import FastAPI, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from trip_concierge.documents import MAX_UPLOAD_BYTES, extract_text

_STATIC = Path(__file__).resolve().parent / "static"
# Session ids name storage folders for uploads, so keep them to a safe alphabet.
_SESSION_ID = re.compile(r"[A-Za-z0-9_-]{1,64}")

# reply(client_id, message) -> agent's text answer
ReplyFn = Callable[[str, str], Awaitable[str]]
# upload(client_id, filename, extracted_text) -> what was stored
UploadFn = Callable[[str, str, str], Awaitable[dict]]


class ChatIn(BaseModel):
    message: str
    session_id: str = "web"


class ChatOut(BaseModel):
    reply: str


def create_app(reply: Optional[ReplyFn] = None, upload: Optional[UploadFn] = None) -> FastAPI:
    app = FastAPI(title="Trip Concierge")

    if reply is None or upload is None:
        from .agent_runner import ConciergeRunner

        runner = ConciergeRunner()
        reply = reply or runner.reply
        upload = upload or runner.upload
    app.state.reply = reply
    app.state.upload = upload

    @app.get("/")
    async def index() -> FileResponse:
        return FileResponse(_STATIC / "index.html")

    @app.post("/chat", response_model=ChatOut)
    async def chat(body: ChatIn) -> ChatOut:
        text = await app.state.reply(body.session_id, body.message)
        return ChatOut(reply=text)

    @app.post("/upload")
    async def upload_file(file: UploadFile, session_id: str = Form("web")) -> dict:
        if not _SESSION_ID.fullmatch(session_id):
            raise HTTPException(422, "invalid session_id")
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
        return await app.state.upload(session_id, name, text)

    app.mount("/static", StaticFiles(directory=_STATIC), name="static")
    return app


app = create_app()
