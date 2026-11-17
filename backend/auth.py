"""Email one-time-code sign-in and browser sessions.

Flow: POST /api/auth/request-code {identifier} emails a 6-digit code; POST
/api/auth/verify {identifier, code} signs in (creating the account on first use)
and sets an HttpOnly session cookie. The identifier is the email or the user ID
(handle) of an existing account; the code always goes to the account's email. Codes and session tokens are stored only as
keyed hashes. Limits: code valid 10 min, 5 wrong tries per code, a resend at most
every 30 s and 5 per 15 min per email. Responses never reveal whether an account
exists.

For local testing, DEV_FIXED_OTP=123456 makes every code that value — honoured
only while no SMTP_HOST is set (i.e. never where real email goes out).

Delivery: SMTP when SMTP_HOST is set; otherwise (local dev) the code is written to
the API log — never returned by the API.
"""

import datetime as dt
import hashlib
import hmac
import logging
import os
import re
import secrets
import smtplib
import ssl
from email.message import EmailMessage
from typing import Optional

from fastapi import HTTPException, Request
from sqlalchemy import delete, select

from .db import AuthSession, Database, LoginCode, User, utcnow

log = logging.getLogger("trip_concierge.auth")

COOKIE = "tc_session"
# One message for every failed check, so it never reveals whether an account exists.
BAD_CODE = "That code isn't right or has expired. Check the email or user ID and request a new code."
CODE_TTL = dt.timedelta(minutes=10)
SESSION_TTL = dt.timedelta(days=30)
MAX_ATTEMPTS = 5
RESEND_COOLDOWN = dt.timedelta(seconds=30)
SEND_WINDOW = dt.timedelta(minutes=15)
MAX_SENDS = 5
_EMAIL = re.compile(r"[^@\s]{1,64}@[^@\s]+\.[A-Za-z]{2,}")
USERNAME = re.compile(r"[a-z0-9](?:[a-z0-9_.]{1,28}[a-z0-9])")
# Keyed hashing so a leaked table can't be brute-forced offline. Falls back to a
# per-process key in dev (codes and sessions then die with the process).
_SECRET = (os.getenv("AUTH_SECRET") or os.getenv("ENCRYPTION_KEY") or secrets.token_hex(32)).encode()


def dev_fixed_code() -> Optional[str]:
    """The fixed test code, if enabled and safe (6 digits, no real email sender)."""
    code = (os.getenv("DEV_FIXED_OTP") or "").strip()
    if not code or os.getenv("SMTP_HOST"):
        return None
    if not re.fullmatch(r"\d{6}", code):
        raise RuntimeError("DEV_FIXED_OTP must be exactly 6 digits")
    return code


if dev_fixed_code():
    log.warning("DEV_FIXED_OTP is on: every sign-in code is %s. Local testing only.", dev_fixed_code())


def _hash(*parts: str) -> str:
    return hmac.new(_SECRET, "\x00".join(parts).encode(), hashlib.sha256).hexdigest()


def normalize_email(email: str) -> str:
    email = email.strip().lower()
    if len(email) > 254 or not _EMAIL.fullmatch(email):
        raise HTTPException(422, "enter a valid email address")
    return email


async def resolve_identifier(db: Database, identifier: str) -> Optional[str]:
    """Email for an email or user ID; None for an unknown user ID (never revealed)."""
    ident = identifier.strip().lower()
    if "@" in ident:
        return normalize_email(ident)
    if not USERNAME.fullmatch(ident):
        raise HTTPException(422, "enter your email or user ID")
    async with db.session() as s:
        return await s.scalar(select(User.email).where(User.username == ident))


async def unique_username(s, email: str) -> str:
    base = re.sub(r"[^a-z0-9_.]", "", email.split("@")[0].lower()).strip("._")[:24] or "traveller"
    base = base if len(base) >= 3 else f"{base}_tc"
    candidate = base
    while await s.scalar(select(User.id).where(User.username == candidate)):
        candidate = f"{base}{secrets.randbelow(10**4):04d}"
    return candidate


def _aware(value: dt.datetime) -> dt.datetime:
    return value if value.tzinfo else value.replace(tzinfo=dt.timezone.utc)  # SQLite drops the zone


def send_code_email(email: str, code: str) -> None:
    if not os.getenv("SMTP_HOST"):
        masked = email[0] + "***@" + email.split("@")[1]
        log.warning("DEV sign-in code for %s: %s  (set SMTP_HOST to email it)", masked, code)
        return
    msg = EmailMessage()
    msg["To"] = email
    msg["From"] = os.getenv("SMTP_FROM", "Trip Concierge <no-reply@example.com>")
    msg["Subject"] = f"{code} is your Trip Concierge sign-in code"
    msg.set_content(
        f"Your Trip Concierge sign-in code is {code}.\n\n"
        "It expires in 10 minutes. If you didn't ask for it, ignore this email."
    )
    with smtplib.SMTP(os.environ["SMTP_HOST"], int(os.getenv("SMTP_PORT", "587")), timeout=20) as s:
        s.starttls(context=ssl.create_default_context())
        if os.getenv("SMTP_USER"):
            s.login(os.environ["SMTP_USER"], os.environ["SMTP_PASSWORD"])
        s.send_message(msg)


async def request_code(db: Database, identifier: str, *, sender=send_code_email) -> None:
    email = await resolve_identifier(db, identifier)
    if email is None:
        return  # unknown user ID: answer exactly as if a code was sent
    now = utcnow()
    code = dev_fixed_code() or f"{secrets.randbelow(10**6):06d}"
    async with db.session() as s:
        row = await s.get(LoginCode, email)
        if row:
            if now - _aware(row.sent_at) < RESEND_COOLDOWN:
                raise HTTPException(429, "please wait a few seconds before asking for another code")
            if now - _aware(row.window_start) > SEND_WINDOW:
                row.window_start, row.sends_in_window = now, 0
            if row.sends_in_window >= MAX_SENDS:
                raise HTTPException(429, "too many codes requested; try again in 15 minutes")
            row.sends_in_window += 1
        else:
            row = LoginCode(email=email, window_start=now, sends_in_window=1)
            s.add(row)
        row.code_hash, row.expires_at, row.attempts, row.sent_at = _hash(email, code), now + CODE_TTL, 0, now
        await s.commit()
    sender(email, code)


async def verify_code(db: Database, identifier: str, code: str) -> tuple[User, str]:
    """Check the code; returns (user, session token). Creates the user on first sign-in."""
    email = await resolve_identifier(db, identifier)
    if email is None:
        raise HTTPException(400, BAD_CODE)
    now = utcnow()
    async with db.session() as s:
        row = await s.get(LoginCode, email)
        if not row or _aware(row.expires_at) < now or row.attempts >= MAX_ATTEMPTS:
            raise HTTPException(400, BAD_CODE)
        if not hmac.compare_digest(row.code_hash, _hash(email, code.strip())):
            row.attempts += 1
            await s.commit()
            raise HTTPException(400, BAD_CODE)
        await s.delete(row)  # one-time
        user = (await s.execute(select(User).where(User.email == email))).scalar_one_or_none()
        if user is None:
            user = User(email=email, name=email.split("@")[0], username=await unique_username(s, email))
            s.add(user)
            await s.flush()
        user.last_login_at = now
        token = secrets.token_urlsafe(32)
        s.add(AuthSession(token_hash=_hash("session", token), user_id=user.id, expires_at=now + SESSION_TTL))
        await s.commit()
        return user, token


async def user_for_token(db: Database, token: Optional[str]) -> Optional[User]:
    if not token:
        return None
    async with db.session() as s:
        sess = await s.get(AuthSession, _hash("session", token))
        if not sess or _aware(sess.expires_at) < utcnow():
            return None
        return await s.get(User, sess.user_id)


async def sign_out(db: Database, token: Optional[str]) -> None:
    if token:
        async with db.session() as s:
            await s.execute(delete(AuthSession).where(AuthSession.token_hash == _hash("session", token)))
            await s.commit()


def session_token(request: Request) -> Optional[str]:
    """Cookie for the browser; `Authorization: Bearer` for API clients."""
    auth = request.headers.get("authorization", "")
    return auth[7:] if auth.lower().startswith("bearer ") else request.cookies.get(COOKIE)
