"""App data in SQL: users, sign-in, trips and media (memories).

Conversations and trip-board state stay in ADK's own session tables; these `tc_*`
tables hold what ADK doesn't: who the user is, which trips they own, and their
photos/videos/files. Times are stored as UTC instants (timestamptz); each user
has an IANA time zone for display.

Uses APP_DB_URL, else SESSION_DB_URL (the compose Postgres), else a local SQLite
file. Tables are created on startup (shortcut: no migrations yet; add Alembic
before the schema changes in production).
"""

import datetime as dt
import os
import uuid
from pathlib import Path
from typing import Optional

from sqlalchemy import BigInteger, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

_LOCAL_DB = Path(__file__).resolve().parent.parent / "trip_concierge.db"


def utcnow() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def new_id() -> str:
    return uuid.uuid4().hex


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "tc_users"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    email: Mapped[str] = mapped_column(String(254), unique=True, index=True)
    # Public user ID (handle) you can sign in with instead of the email; lowercase.
    username: Mapped[Optional[str]] = mapped_column(String(30), unique=True, index=True)
    name: Mapped[Optional[str]] = mapped_column(String(80))
    home_city: Mapped[Optional[str]] = mapped_column(String(80))
    timezone: Mapped[str] = mapped_column(String(64), default="UTC")  # IANA, e.g. Asia/Kolkata
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_login_at: Mapped[Optional[dt.datetime]] = mapped_column(DateTime(timezone=True))


class LoginCode(Base):
    """The pending one-time code for an email (only its hash is stored)."""

    __tablename__ = "tc_login_codes"
    email: Mapped[str] = mapped_column(String(254), primary_key=True)
    code_hash: Mapped[str] = mapped_column(String(64))
    expires_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True))
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    sent_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    window_start: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    sends_in_window: Mapped[int] = mapped_column(Integer, default=1)


class AuthSession(Base):
    """A signed-in browser. The cookie holds the token; only its hash is stored."""

    __tablename__ = "tc_auth_sessions"
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("tc_users.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    expires_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True))


class Trip(Base):
    """A trip the user owns; its id is also the ADK session id."""

    __tablename__ = "tc_trips"
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("tc_users.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(120), default="New trip")
    starts_at: Mapped[Optional[dt.datetime]] = mapped_column(DateTime(timezone=True))
    ends_at: Mapped[Optional[dt.datetime]] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Media(Base):
    """A photo, video or other file the user keeps as a memory."""

    __tablename__ = "tc_media"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("tc_users.id", ondelete="CASCADE"), index=True)
    trip_id: Mapped[Optional[str]] = mapped_column(ForeignKey("tc_trips.id", ondelete="SET NULL"), index=True)
    storage_key: Mapped[str] = mapped_column(String(300))
    thumb_key: Mapped[Optional[str]] = mapped_column(String(300))
    filename: Mapped[str] = mapped_column(String(200))
    content_type: Mapped[str] = mapped_column(String(120))
    size: Mapped[int] = mapped_column(BigInteger)
    kind: Mapped[str] = mapped_column(String(10))  # photo | video | audio | file
    caption: Mapped[Optional[str]] = mapped_column(Text)
    place: Mapped[Optional[str]] = mapped_column(String(120))
    lat: Mapped[Optional[float]] = mapped_column(Float)
    lng: Mapped[Optional[float]] = mapped_column(Float)
    taken_at: Mapped[Optional[dt.datetime]] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class GeoCache(Base):
    """Place name -> coordinates, so each name is looked up once."""

    __tablename__ = "tc_geocache"
    query: Mapped[str] = mapped_column(String(160), primary_key=True)
    lat: Mapped[Optional[float]] = mapped_column(Float)
    lng: Mapped[Optional[float]] = mapped_column(Float)
    label: Mapped[Optional[str]] = mapped_column(String(200))


def db_url() -> str:
    return os.getenv("APP_DB_URL") or os.getenv("SESSION_DB_URL") or f"sqlite+aiosqlite:///{_LOCAL_DB}"


class Database:
    def __init__(self, url: Optional[str] = None) -> None:
        self.engine: AsyncEngine = create_async_engine(url or db_url())
        self.session = async_sessionmaker(self.engine, expire_on_commit=False, class_=AsyncSession)

    async def create_tables(self) -> None:
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
