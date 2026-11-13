"""FastAPI backend + static chat UI for the trip concierge.

`create_app(reply=...)` takes the async reply callable, which defaults to the ADK
concierge runner. Injecting a fake reply keeps the HTTP layer testable without a
Gemini API key.

Run it:  uvicorn web.app:app --port 8000   then open http://localhost:8000
"""

from pathlib import Path
from typing import Awaitable, Callable, Optional

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

_STATIC = Path(__file__).resolve().parent / "static"

# reply(client_id, message) -> agent's text answer
ReplyFn = Callable[[str, str], Awaitable[str]]


class ChatIn(BaseModel):
    message: str
    session_id: str = "web"


class ChatOut(BaseModel):
    reply: str


def create_app(reply: Optional[ReplyFn] = None) -> FastAPI:
    app = FastAPI(title="Trip Concierge")

    if reply is None:
        from .agent_runner import ConciergeRunner

        reply = ConciergeRunner().reply
    app.state.reply = reply

    @app.get("/")
    async def index() -> FileResponse:
        return FileResponse(_STATIC / "index.html")

    @app.post("/chat", response_model=ChatOut)
    async def chat(body: ChatIn) -> ChatOut:
        text = await app.state.reply(body.session_id, body.message)
        return ChatOut(reply=text)

    app.mount("/static", StaticFiles(directory=_STATIC), name="static")
    return app


app = create_app()
