"""OAuth helper tests: authorization URL and token exchange (no network/creds)."""

from urllib.parse import parse_qs, urlparse

from trip_concierge.oauth import (
    OAuthConfig,
    build_authorization_url,
    exchange_code_for_token,
)

CONFIG = OAuthConfig(client_id="cid", client_secret="secret", redirect_uri="http://cb")


def test_authorization_url_has_required_params():
    url = build_authorization_url(CONFIG, state="xyz")
    q = parse_qs(urlparse(url).query)
    assert q["response_type"] == ["code"]
    assert q["client_id"] == ["cid"]
    assert q["redirect_uri"] == ["http://cb"]
    assert q["state"] == ["xyz"]
    assert q["scope"] == [CONFIG.scope]


def test_exchange_code_posts_correct_fields():
    seen = {}

    def fake_transport(url, fields):
        seen["url"] = url
        seen["fields"] = fields
        return {"access_token": "tok", "refresh_token": "ref"}

    token = exchange_code_for_token(CONFIG, "the-code", transport=fake_transport)
    assert token["access_token"] == "tok"
    assert seen["url"] == CONFIG.token_endpoint
    assert seen["fields"]["grant_type"] == "authorization_code"
    assert seen["fields"]["code"] == "the-code"
    assert seen["fields"]["client_secret"] == "secret"
