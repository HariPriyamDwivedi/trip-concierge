"""Generic OAuth 2.0 authorization-code helper (Google defaults).

Pure-stdlib, with an injectable HTTP transport so the token exchange is testable
without real credentials or network. This module only obtains tokens — it never
sends mail or reads a calendar — and only when you configure real client
credentials via the environment. It is opt-in: the rest of the app defaults to a
local stub and never calls this.
"""

import json
import os
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
        "access_type": "offline",
        "prompt": "consent",
    }
    return f"{config.auth_endpoint}?{urllib.parse.urlencode(params)}"


def _post_form(url: str, fields: dict) -> dict:
    body = urllib.parse.urlencode(fields).encode()
    req = urllib.request.Request(url, data=body, method="POST")
    with urllib.request.urlopen(req) as resp:  # noqa: S310 - fixed token endpoint
        return json.loads(resp.read().decode())


def exchange_code_for_token(
    config: OAuthConfig, code: str, *, transport: Transport = _post_form
) -> dict:
    """Exchange an authorization code for an access/refresh token."""
    return transport(
        config.token_endpoint,
        {
            "client_id": config.client_id,
            "client_secret": config.client_secret,
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": config.redirect_uri,
        },
    )


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
