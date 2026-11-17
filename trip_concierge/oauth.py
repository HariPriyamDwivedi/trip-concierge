"""Generic OAuth 2.0 authorization-code helper (Google defaults).

Pure-stdlib, with an injectable HTTP transport so the token exchange is testable
without real credentials or network. This module only obtains tokens — it never
sends mail or reads a calendar — and only when you configure real client
credentials via the environment. It is opt-in: the rest of the app defaults to a
local stub and never calls this.
"""

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Callable

# A transport takes (token_endpoint, form_fields) and returns the parsed JSON.
Transport = Callable[[str, dict], dict]


@dataclass
class OAuthConfig:
    client_id: str
    client_secret: str
    redirect_uri: str = "http://localhost:8080/callback"
    auth_endpoint: str = "https://accounts.google.com/o/oauth2/v2/auth"
    token_endpoint: str = "https://oauth2.googleapis.com/token"
    scope: str = "https://www.googleapis.com/auth/calendar.readonly"
    # Google needs prompt=consent + access_type=offline to return a refresh token.
    # Microsoft must NOT get prompt=consent: it forces a consent screen, which tenants
    # that disallow user consent turn into "Approval required" even when an admin
    # already approved the app (it returns refresh tokens via offline_access instead).
    prompt: str | None = "consent"
    access_type: str | None = "offline"

    @classmethod
    def from_env(cls) -> "OAuthConfig":
        """Build config from OAUTH_* env vars. Raises if client creds are unset."""
        return cls(
            client_id=os.environ["OAUTH_CLIENT_ID"],
            client_secret=os.environ["OAUTH_CLIENT_SECRET"],
            redirect_uri=os.getenv("OAUTH_REDIRECT_URI", cls.redirect_uri),
        )


def build_authorization_url(config: OAuthConfig, state: str) -> str:
    """The URL to send the user to so they can grant access."""
    params = {
        "client_id": config.client_id,
        "redirect_uri": config.redirect_uri,
        "response_type": "code",
        "scope": config.scope,
        "state": state,
    }
    if config.access_type:
        params["access_type"] = config.access_type
    if config.prompt:
        params["prompt"] = config.prompt
    return f"{config.auth_endpoint}?{urllib.parse.urlencode(params)}"


def _post_form(url: str, fields: dict) -> dict:
    body = urllib.parse.urlencode(fields).encode()
    req = urllib.request.Request(url, data=body, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:  # noqa: S310 - fixed token endpoint
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:  # token errors come back as 400 + JSON {"error": ...}
        try:
            return json.loads(exc.read().decode())
        except ValueError:
            return {"error": f"HTTP {exc.code}"}


def exchange_code_for_token(
    config: OAuthConfig,
    code: str,
    *,
    code_verifier: str | None = None,
    transport: Transport = _post_form,
) -> dict:
    """Exchange an authorization code for an access/refresh token (PKCE verifier optional)."""
    fields = {
        "client_id": config.client_id,
        "client_secret": config.client_secret,
        "code": code,
        "grant_type": "authorization_code",
        "redirect_uri": config.redirect_uri,
    }
    if code_verifier:
        fields["code_verifier"] = code_verifier
    return transport(config.token_endpoint, fields)


def refresh_access_token(
    config: OAuthConfig, refresh_token: str, *, transport: Transport = _post_form
) -> dict:
    """Get a fresh access token from a stored refresh token."""
    return transport(
        config.token_endpoint,
        {
            "client_id": config.client_id,
            "client_secret": config.client_secret,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
        },
    )
