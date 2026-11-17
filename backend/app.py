"""Trip Concierge API (FastAPI). The UI is the separate app in frontend/.

Everything except /api/health, /api/seasonal and the auth routes needs a signed-in
user (HttpOnly cookie, or `Authorization: Bearer <token>`), and every trip route
checks the trip belongs to that user (else 404).

Auth & profile
  POST  /api/auth/request-code {identifier}    email a 6-digit code (identifier = email or user ID)
  POST  /api/auth/verify {identifier, code}    sign in (sets the session cookie)
  POST  /api/auth/logout
  GET   /api/me   PATCH /api/me {name, username, home_city, timezone}
Trips
  GET   /api/trips                             your trips, newest first (upcoming / past)
  POST  /api/trips {title?}                    start a trip
  GET   /api/trips/{id}                        messages, board, documents, connectors, alerts
  PATCH /api/trips/{id} {title}
  POST  /api/trips/{id}/chat | /chat/stream    {message}; the stream is server-sent events
  POST  /api/trips/{id}/documents              text/PDF the agent can search (RAG)
  POST  /api/trips/{id}/items   DELETE /api/trips/{id}/items/{item_id}
  PUT   /api/trips/{id}/connectors/{c} {connected}
  DELETE /api/trips/{id}/accounts/{provider}    sign out of Google/Microsoft (Mail + Calendar)
  PUT   /api/trips/{id}/mail-from {provider}    which connected mailbox sends
  GET   /api/oauth/{provider}/start?trip_id=    one sign-in for Mail + Calendar
  GET   /api/oauth/callback
Memories
  POST  /api/media (multipart)   GET /api/media?trip_id=&kind=   PATCH/DELETE /api/media/{id}
  GET   /api/media/{id}/{original|thumb}       file (local storage) or redirect (S3)
  GET   /api/places                            map pins: places with photos/videos
Public
  GET   /api/health   GET /api/seasonal?when=November

Run it:  uvicorn backend.app:app --port 8000
"""

import datetime as dt
import json
import logging
import re
import secrets
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlencode
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, FastAPI, Form, HTTPException, Request, Response, UploadFile
from fastapi.responses import FileResponse, RedirectResponse, StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from trip_concierge.documents import MAX_UPLOAD_BYTES, extract_text
from trip_concierge.seasons import seasonal_destinations

from . import auth
from .db import Database, Media, Trip, User, utcnow
from .media import geocode, media_json, places, save_upload
from .storage import LocalStorage, make_storage

log = logging.getLogger("trip_concierge.api")


# ── Request bodies ──────────────────────────────────────────────────────────


class LoginIn(BaseModel):
    identifier: str = Field(min_length=3, max_length=254)  # email or user ID


class VerifyIn(BaseModel):
    identifier: str = Field(min_length=3, max_length=254)
    code: str = Field(min_length=6, max_length=6, pattern=r"^\d{6}$")


class ProfileIn(BaseModel):
    name: Optional[str] = Field(default=None, max_length=80)
    username: Optional[str] = Field(default=None, max_length=30)
    home_city: Optional[str] = Field(default=None, max_length=80)
    timezone: Optional[str] = Field(default=None, max_length=64)


class TripIn(BaseModel):
    title: Optional[str] = Field(default=None, max_length=120)


class ChatIn(BaseModel):
    message: str = Field(min_length=1, max_length=4000)


class ItemIn(BaseModel):
    kind: str
    title: str = Field(min_length=1, max_length=120)
    starts_at: str = Field(min_length=10, max_length=25)
    ends_at: Optional[str] = Field(default=None, max_length=25)
    from_place: Optional[str] = Field(default=None, max_length=80)
    to_place: Optional[str] = Field(default=None, max_length=80)
    reference: Optional[str] = Field(default=None, max_length=40)
    start_tz: Optional[str] = Field(default=None, max_length=64)
    end_tz: Optional[str] = Field(default=None, max_length=64)


class ConnectorIn(BaseModel):
    connected: bool


class MailFromIn(BaseModel):
    provider: str = Field(max_length=20)


class MediaPatch(BaseModel):
    caption: Optional[str] = Field(default=None, max_length=2000)
    place: Optional[str] = Field(default=None, max_length=120)
    trip_id: Optional[str] = Field(default=None, max_length=40)


# ── Dependencies ────────────────────────────────────────────────────────────


async def current_user(request: Request) -> User:
    user = await auth.user_for_token(request.app.state.db, auth.session_token(request))
    if user is None:
        raise HTTPException(401, "sign in first")
    return user


async def owned_trip(trip_id: str, request: Request, user: User = Depends(current_user)) -> Trip:
    async with request.app.state.db.session() as s:
        trip = await s.get(Trip, trip_id)
    if trip is None or trip.user_id != user.id:
        raise HTTPException(404, "trip not found")
    return trip


def _valid_tz(name: str) -> str:
    try:
        return ZoneInfo(name).key
    except (ZoneInfoNotFoundError, ValueError):
        raise HTTPException(422, f"unknown time zone {name!r}") from None


def user_json(u: User) -> dict:
    return {"id": u.id, "username": u.username, "email": u.email, "name": u.name, "home_city": u.home_city, "timezone": u.timezone,
            "created_at": u.created_at.isoformat() if u.created_at else None}


def _aware(value: Optional[dt.datetime]) -> Optional[dt.datetime]:
    return value.replace(tzinfo=dt.timezone.utc) if value and value.tzinfo is None else value


def trip_json(t: Trip, media_count: int = 0) -> dict:
    now = utcnow()
    start, end = _aware(t.starts_at), _aware(t.ends_at) or _aware(t.starts_at)
    status = (
        "planning" if start is None
        else "upcoming" if start > now
        else "ongoing" if end and end >= now - dt.timedelta(days=1)
        else "past"
    )
    return {"id": t.id, "title": t.title, "status": status, "media_count": media_count,
            "starts_at": start.isoformat() if start else None, "ends_at": end.isoformat() if end else None,
            "created_at": t.created_at.isoformat(), "updated_at": _aware(t.updated_at).isoformat()}


def _sse(kind: str, data: dict) -> str:
    return f"event: {kind}\ndata: {json.dumps(data)}\n\n"


def create_app(service: Any = None, db: Optional[Database] = None, storage: Any = None, code_sender=None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        await app.state.db.create_tables()
        yield

    app = FastAPI(title="Trip Concierge API", lifespan=lifespan)
    if service is None:
        from .agent_runner import ConciergeRunner

        service = ConciergeRunner()
    app.state.db = db or Database()
    app.state.storage = storage or make_storage()
    app.state.code_sender = code_sender if code_sender is not None else auth.send_code_email
    api = APIRouter(prefix="/api")
    DB = app.state.db
    STORE = app.state.storage

    async def sync_trip(trip: Trip, board: dict) -> None:
        """Keep the trip list in step with the board: title from the city, dates from bookings."""
        items = board.get("items") or []
        async with DB.session() as s:
            row = await s.get(Trip, trip.id)
            if board.get("city") and row.title in ("New trip", ""):
                row.title = f"{board['city']} trip"
            if items:
                def when(value):
                    return dt.datetime.fromisoformat(value.replace("Z", "+00:00"))

                starts = [when(i["starts_utc"]) for i in items if i.get("starts_utc")]
                ends = [when(i.get("ends_utc") or i["starts_utc"]) for i in items if i.get("starts_utc")]
                if starts:
                    row.starts_at, row.ends_at = min(starts), max(ends)
            row.updated_at = utcnow()
            await s.commit()

    # ── Public ──────────────────────────────────────────────────────────────

    @api.get("/health")
    async def health() -> dict:
        return {"ok": True}

    @api.get("/seasonal")
    async def seasonal(when: str) -> dict:
        result = seasonal_destinations(when)
        if "error" in result:
            raise HTTPException(422, result["error"])
        return result

    # ── Auth & profile ──────────────────────────────────────────────────────

    @api.post("/auth/request-code")
    async def request_code(body: LoginIn) -> dict:
        await auth.request_code(DB, body.identifier, sender=app.state.code_sender)
        return {"ok": True}  # same answer whether or not an account exists

    @api.post("/auth/verify")
    async def verify(body: VerifyIn, request: Request, response: Response) -> dict:
        user, token = await auth.verify_code(DB, body.identifier, body.code)
        response.set_cookie(
            auth.COOKIE, token, max_age=int(auth.SESSION_TTL.total_seconds()), httponly=True,
            samesite="lax", secure=request.url.scheme == "https", path="/",
        )
        return {"user": user_json(user)}

    @api.post("/auth/logout")
    async def logout(request: Request, response: Response) -> dict:
        await auth.sign_out(DB, auth.session_token(request))
        response.delete_cookie(auth.COOKIE, path="/")
        return {"ok": True}

    @api.get("/me")
    async def me(user: User = Depends(current_user)) -> dict:
        async with DB.session() as s:
            trips = await s.scalar(select(func.count()).select_from(Trip).where(Trip.user_id == user.id))
            media = await s.scalar(select(func.count()).select_from(Media).where(Media.user_id == user.id))
            located = (await s.execute(select(Media).where(Media.user_id == user.id, Media.lat.is_not(None)))).scalars().all()
        return {"user": user_json(user), "stats": {"trips": trips, "memories": media, "places": len(places(located))}}

    @api.patch("/me")
    async def update_me(body: ProfileIn, user: User = Depends(current_user)) -> dict:
        async with DB.session() as s:
            row = await s.get(User, user.id)
            if body.name is not None:
                row.name = body.name.strip() or None
            if body.username is not None and body.username.strip().lower() != row.username:
                handle = body.username.strip().lower()
                if not auth.USERNAME.fullmatch(handle):
                    raise HTTPException(422, "user ID: 3-30 letters, digits, _ or . (not at the ends)")
                if await s.scalar(select(User.id).where(User.username == handle)):
                    raise HTTPException(409, "that user ID is taken")
                row.username = handle
            if body.home_city is not None:
                row.home_city = body.home_city.strip() or None
            if body.timezone is not None:
                row.timezone = _valid_tz(body.timezone)
            await s.commit()
            latest = (await s.execute(select(Trip).where(Trip.user_id == user.id).order_by(Trip.updated_at.desc()).limit(1))).scalar_one_or_none()
        if body.timezone is not None and latest:
            await service.set_user_timezone(user.id, latest.id, row.timezone)  # ADK user state, all trips
        return {"user": user_json(row)}

    # ── Trips ───────────────────────────────────────────────────────────────

    @api.get("/trips")
    async def list_trips(user: User = Depends(current_user)) -> list[dict]:
        async with DB.session() as s:
            rows = (await s.execute(select(Trip).where(Trip.user_id == user.id).order_by(Trip.updated_at.desc()))).scalars().all()
            counts = dict((await s.execute(
                select(Media.trip_id, func.count()).where(Media.user_id == user.id).group_by(Media.trip_id)
            )).all())
        return [trip_json(t, counts.get(t.id, 0)) for t in rows]

    @api.post("/trips")
    async def create_trip(body: TripIn, user: User = Depends(current_user)) -> dict:
        trip = Trip(id="trip-" + secrets.token_hex(8), user_id=user.id, title=(body.title or "New trip").strip()[:120])
        async with DB.session() as s:
            s.add(trip)
            await s.commit()
        await service.set_user_timezone(user.id, trip.id, user.timezone)  # also creates the ADK session
        return trip_json(trip)

    @api.get("/trips/{trip_id}")
    async def get_trip(trip: Trip = Depends(owned_trip)) -> dict:
        return {"trip_meta": trip_json(trip), **await service.view(trip.user_id, trip.id)}

    @api.patch("/trips/{trip_id}")
    async def rename_trip(body: TripIn, trip: Trip = Depends(owned_trip)) -> dict:
        async with DB.session() as s:
            row = await s.get(Trip, trip.id)
            row.title = (body.title or row.title).strip()[:120] or row.title
            row.updated_at = utcnow()
            await s.commit()
        return trip_json(row)

    @api.post("/trips/{trip_id}/chat")
    async def chat(body: ChatIn, trip: Trip = Depends(owned_trip)) -> dict:
        result = await service.chat(trip.user_id, trip.id, body.message)
        await sync_trip(trip, result["trip"])
        return result

    @api.post("/trips/{trip_id}/chat/stream")
    async def chat_stream(body: ChatIn, trip: Trip = Depends(owned_trip)) -> StreamingResponse:
        async def events():
            try:
                async for item in service.chat_stream(trip.user_id, trip.id, body.message):
                    kind = item.pop("type")
                    if kind == "done":
                        await sync_trip(trip, item["trip"])
                    yield _sse(kind, item)
            except Exception:
                log.exception("chat stream failed")
                yield _sse("error", {"message": "The concierge hit an error. Please try again."})

        # X-Accel-Buffering stops nginx from holding the stream back.
        return StreamingResponse(events(), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    @api.post("/trips/{trip_id}/documents")
    async def upload_document(file: UploadFile, trip: Trip = Depends(owned_trip)) -> dict:
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
        return await service.upload(trip.user_id, trip.id, name, text)

    @api.post("/trips/{trip_id}/items")
    async def add_item(body: ItemIn, trip: Trip = Depends(owned_trip)) -> dict:
        fields = body.model_dump()
        if not fields["start_tz"]:  # no zone given: the user's home zone, not UTC
            async with DB.session() as s:
                fields["start_tz"] = (await s.get(User, trip.user_id)).timezone
        try:
            result = await service.add_item(trip.user_id, trip.id, **fields)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        await sync_trip(trip, result["trip"])
        return result

    @api.delete("/trips/{trip_id}/items/{item_id}")
    async def remove_item(item_id: str, trip: Trip = Depends(owned_trip)) -> dict:
        try:
            result = await service.remove_item(trip.user_id, trip.id, item_id)
        except KeyError:
            raise HTTPException(404, "no such item") from None
        await sync_trip(trip, result["trip"])
        return result

    @api.put("/trips/{trip_id}/connectors/{connector_id}")
    async def set_connector(connector_id: str, body: ConnectorIn, trip: Trip = Depends(owned_trip)) -> list[dict]:
        try:
            return await service.set_connector(trip.user_id, trip.id, connector_id, body.connected)
        except KeyError:
            raise HTTPException(404, f"unknown connector {connector_id!r}") from None

    @api.delete("/trips/{trip_id}/accounts/{provider}")
    async def disconnect(provider: str, trip: Trip = Depends(owned_trip)) -> dict:
        try:
            return await service.disconnect_account(trip.user_id, trip.id, provider)
        except KeyError:
            raise HTTPException(404, f"unknown provider {provider!r}") from None

    @api.put("/trips/{trip_id}/mail-from")
    async def mail_from(body: MailFromIn, trip: Trip = Depends(owned_trip)) -> dict:
        try:
            return await service.set_mail_from(trip.user_id, trip.id, body.provider)
        except KeyError:
            raise HTTPException(422, "that account isn't connected") from None

    @api.get("/oauth/{provider}/start")
    async def oauth_start(provider: str, trip_id: str, request: Request,
                          user: User = Depends(current_user)) -> RedirectResponse:
        trip = await owned_trip(trip_id, request, user)
        try:
            url = service.oauth_start(user.id, trip.id, provider)
        except KeyError:
            raise HTTPException(404, "unknown provider") from None
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        return RedirectResponse(url, status_code=302)

    @api.get("/oauth/callback")
    async def oauth_callback(state: str = "", code: str = "", error: str = "", error_description: str = "") -> RedirectResponse:
        # Back to the app (same origin via nginx) with the outcome in the query string.
        if error or not code:
            result = {"oauth": "error", "message": error_description or error or "sign-in cancelled"}
        else:
            try:
                result = {"oauth": "connected", **await service.oauth_finish(state, code)}
            except Exception as exc:
                log.warning("oauth callback failed: %s", exc)
                result = {"oauth": "error", "message": str(exc)[:200]}
        return RedirectResponse("/?" + urlencode(result), status_code=302)

    # ── Memories (photos, videos, files) ────────────────────────────────────

    async def owned_media(media_id: str, user: User) -> Media:
        async with DB.session() as s:
            m = await s.get(Media, media_id)
        if m is None or m.user_id != user.id:
            raise HTTPException(404, "not found")
        return m

    @api.post("/media")
    async def upload_media(
        request: Request,
        file: UploadFile,
        trip_id: Optional[str] = Form(None),
        caption: Optional[str] = Form(None),
        place: Optional[str] = Form(None),
        lat: Optional[float] = Form(None),
        lng: Optional[float] = Form(None),
        taken_at: Optional[str] = Form(None),
        user: User = Depends(current_user),
    ) -> dict:
        if trip_id:
            await owned_trip(trip_id, request, user)
        if (lat is None) != (lng is None) or (lat is not None and not (-90 <= lat <= 90 and -180 <= lng <= 180)):
            raise HTTPException(422, "lat and lng must be given together and be valid coordinates")
        when = None
        if taken_at:
            try:
                when = dt.datetime.fromisoformat(taken_at.replace("Z", "+00:00"))
            except ValueError:
                raise HTTPException(422, "taken_at must be ISO 8601") from None
            if when.tzinfo is None:
                when = when.replace(tzinfo=ZoneInfo(user.timezone))  # wall clock in the user's zone
        try:
            m = await save_upload(DB, STORE, user_id=user.id, upload=file, trip_id=trip_id, caption=caption,
                                  place=place, lat=lat, lng=lng, taken_at=when)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        return media_json(m, STORE)

    @api.get("/media")
    async def list_media(trip_id: Optional[str] = None, kind: Optional[str] = None, place: Optional[str] = None,
                         user: User = Depends(current_user)) -> list[dict]:
        q = select(Media).where(Media.user_id == user.id)
        if trip_id:
            q = q.where(Media.trip_id == trip_id)
        if kind:
            q = q.where(Media.kind == kind)
        if place:
            q = q.where(func.lower(Media.place) == place.strip().lower())
        q = q.order_by(func.coalesce(Media.taken_at, Media.created_at).desc()).limit(1000)
        async with DB.session() as s:
            rows = (await s.execute(q)).scalars().all()
        return [media_json(m, STORE) for m in rows]

    @api.patch("/media/{media_id}")
    async def update_media(media_id: str, body: MediaPatch, request: Request, user: User = Depends(current_user)) -> dict:
        await owned_media(media_id, user)
        if body.trip_id:
            await owned_trip(body.trip_id, request, user)
        coords = await geocode(DB, body.place) if body.place else None
        async with DB.session() as s:
            m = await s.get(Media, media_id)
            if body.caption is not None:
                m.caption = body.caption.strip() or None
            if body.place is not None:
                m.place = body.place.strip() or None
                if coords:
                    m.lat, m.lng = coords
            if body.trip_id is not None:
                m.trip_id = body.trip_id or None
            await s.commit()
        return media_json(m, STORE)

    @api.delete("/media/{media_id}")
    async def delete_media(media_id: str, user: User = Depends(current_user)) -> dict:
        m = await owned_media(media_id, user)
        for key in filter(None, (m.storage_key, m.thumb_key)):
            STORE.delete(key)
        async with DB.session() as s:
            await s.delete(await s.get(Media, media_id))
            await s.commit()
        return {"ok": True}

    @api.get("/media/{media_id}/{variant}")
    async def media_file(media_id: str, variant: str, user: User = Depends(current_user)):
        m = await owned_media(media_id, user)
        key = m.thumb_key if variant == "thumb" else m.storage_key if variant == "original" else None
        if not key:
            raise HTTPException(404, "not found")
        ctype = "image/jpeg" if variant == "thumb" else m.content_type
        if isinstance(STORE, LocalStorage):
            return FileResponse(STORE.open(key), media_type=ctype, filename=m.filename, content_disposition_type="inline")
        return RedirectResponse(STORE.url(key, m.id, variant, m.filename, ctype), status_code=302)

    @api.get("/places")
    async def list_places(user: User = Depends(current_user)) -> list[dict]:
        async with DB.session() as s:
            rows = (await s.execute(select(Media).where(Media.user_id == user.id, Media.lat.is_not(None)))).scalars().all()
        by_id = {m.id: m for m in rows}
        pins = places(rows)
        for p in pins:  # a cover picture for the map popup
            cover = next((by_id[i] for i in p["media_ids"] if by_id[i].thumb_key), None)
            p["cover_url"] = STORE.url(cover.thumb_key, cover.id, "thumb", cover.filename, "image/jpeg") if cover else None
        return pins

    app.include_router(api)
    return app


app = create_app()
