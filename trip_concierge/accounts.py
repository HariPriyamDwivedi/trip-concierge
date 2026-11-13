"""Signed-in Google / Microsoft accounts behind the Mail and Calendar connectors.

The traveller signs in per connector with the smallest scope that connector needs:
  Calendar: Google `calendar.freebusy` (free/busy only) or Microsoft `Calendars.Read`
  Mail:     Google `gmail.send` or Microsoft `Mail.Send` (send only, no inbox access)

Tokens are encrypted with ENCRYPTION_KEY (a Fernet key) and kept in the trip's ADK
session state under `account_<connector>`; they are never returned to the browser.
Access tokens are refreshed when they are about to expire. HTTP goes through an
injectable transport so everything here is testable without network.
"""

import base64
import hashlib
import json
import os
import secrets
import time
import urllib.parse
import urllib.request
from typing import Any, Callable, Optional

from .oauth import OAuthConfig, build_authorization_url, exchange_code_for_token, refresh_access_token

STATE_PREFIX = "account_"
_OPENID = "openid email"


def _microsoft_base() -> str:
    tenant = os.getenv("MICROSOFT_TENANT_ID") or "common"
    return f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0"


PROVIDERS: dict[str, dict] = {
    "google": {
        "label": "Google",
        "client_env": ("GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET"),
        "auth": lambda: "https://accounts.google.com/o/oauth2/v2/auth",
        "token": lambda: "https://oauth2.googleapis.com/token",
        "scopes": {
            "calendar": f"{_OPENID} https://www.googleapis.com/auth/calendar.freebusy",
            "mail": f"{_OPENID} https://www.googleapis.com/auth/gmail.send",
        },
    },
    "microsoft": {
        "label": "Microsoft",
        "client_env": ("MICROSOFT_CLIENT_ID", "MICROSOFT_CLIENT_SECRET"),
        "auth": lambda: f"{_microsoft_base()}/authorize",
        "token": lambda: f"{_microsoft_base()}/token",
        "scopes": {
            "calendar": f"{_OPENID} offline_access Calendars.Read",
            "mail": f"{_OPENID} offline_access Mail.Send",
        },
    },
}


def redirect_uri() -> str:
    # Registered in the Google and Azure apps; nginx forwards it to /api/oauth/callback.
    return os.getenv("OAUTH_REDIRECT_URI", "http://localhost:8080/oauth/callback")


def available_providers() -> list[str]:
    """Providers whose client credentials and the encryption key are configured."""
    if not os.getenv("ENCRYPTION_KEY"):
        return []
    return [p for p, c in PROVIDERS.items() if all(os.getenv(v) for v in c["client_env"])]


def _config(provider: str, connector: str) -> OAuthConfig:
    p = PROVIDERS[provider]
    cid, secret = (os.environ[v] for v in p["client_env"])
    return OAuthConfig(
        client_id=cid,
        client_secret=secret,
        redirect_uri=redirect_uri(),
        auth_endpoint=p["auth"](),
        token_endpoint=p["token"](),
        scope=p["scopes"][connector],
    )


# ── Sign-in ───────────────────────────────────────────────────────────────


def start(provider: str, connector: str) -> dict:
    """Begin sign-in: the provider URL plus the one-time state and PKCE verifier to keep."""
    if provider not in available_providers():
        raise ValueError(f"{provider} sign-in is not configured on this server")
    state = secrets.token_urlsafe(32)
    verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    url = build_authorization_url(_config(provider, connector), state)
    url += "&" + urllib.parse.urlencode({"code_challenge": challenge, "code_challenge_method": "S256"})
    return {"url": url, "state": state, "verifier": verifier}


def _account_name(token: dict) -> str:
    """Email from the id_token (it came straight from the token endpoint over TLS)."""
    try:
        payload = token["id_token"].split(".")[1]
        claims = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
        return claims.get("email") or claims.get("preferred_username") or "connected account"
    except Exception:
        return "connected account"


def finish(provider: str, connector: str, code: str, verifier: str, *, transport=None) -> dict:
    """Exchange the authorization code; returns the account record to store."""
    cfg = _config(provider, connector)
    kwargs = {"transport": transport} if transport else {}
    token = exchange_code_for_token(cfg, code, code_verifier=verifier, **kwargs)
    if "access_token" not in token:
        raise ValueError(token.get("error_description") or token.get("error") or "sign-in failed")
    return {
        "provider": provider,
        "account": _account_name(token),
        "access_token": token["access_token"],
        "refresh_token": token.get("refresh_token"),
        "expires_at": time.time() + int(token.get("expires_in", 3600)),
    }


# ── Storage ───────────────────────────────────────────────────────────────


def _fernet():
    from cryptography.fernet import Fernet

    return Fernet(os.environ["ENCRYPTION_KEY"].encode())


def seal(record: dict) -> str:
    return _fernet().encrypt(json.dumps(record).encode()).decode()


def unseal(blob: str) -> dict:
    return json.loads(_fernet().decrypt(blob.encode()))


def account_view(state: dict, connector: str) -> Optional[dict]:
    """What the UI may see about a connector's account: provider and email, no tokens."""
    blob = state.get(STATE_PREFIX + connector)
    if not blob:
        return None
    try:
        rec = unseal(blob)
    except Exception:  # key changed or data damaged: treat as not connected
        return None
    return {"provider": rec["provider"], "label": PROVIDERS[rec["provider"]]["label"], "account": rec["account"]}


def access_token(state: Any, connector: str, *, transport=None) -> Optional[tuple[str, str, str]]:
    """(provider, access_token, account) for a connector, refreshing if near expiry.

    `state` is the tool context's session state; a refreshed token is written back.
    """
    blob = state.get(STATE_PREFIX + connector)
    if not blob:
        return None
    rec = unseal(blob)
    if rec["expires_at"] - time.time() < 60 and rec.get("refresh_token"):
        kwargs = {"transport": transport} if transport else {}
        new = refresh_access_token(_config(rec["provider"], connector), rec["refresh_token"], **kwargs)
        if "access_token" not in new:
            raise RuntimeError(f"{rec['provider']} sign-in expired; reconnect the {connector} connector")
        rec.update(
            access_token=new["access_token"],
            refresh_token=new.get("refresh_token") or rec["refresh_token"],
            expires_at=time.time() + int(new.get("expires_in", 3600)),
        )
        state[STATE_PREFIX + connector] = seal(rec)
    return rec["provider"], rec["access_token"], rec["account"]


# ── Provider API calls ────────────────────────────────────────────────────

# transport(method, url, token, json_body | None) -> parsed JSON response ({} if empty)
ApiTransport = Callable[[str, str, str, Optional[dict]], dict]


def api_request(method: str, url: str, token: str, body: Optional[dict] = None) -> dict:
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode() if body is not None else None,
        method=method,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=20) as resp:  # noqa: S310 - fixed provider endpoints
        raw = resp.read()
    return json.loads(raw) if raw else {}
