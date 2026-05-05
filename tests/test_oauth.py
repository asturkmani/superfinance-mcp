"""Tests for the minimal OAuth 2.1 + DCR shim."""

import base64
import hashlib
import sys
from pathlib import Path

import pytest
from starlette.applications import Starlette
from starlette.routing import Route
from starlette.testclient import TestClient

sys.path.insert(0, str(Path(__file__).parent.parent))

from oauth import (  # noqa: E402
    _auth_codes,
    extract_bearer_token,
    make_authorize_post,
    oauth_authorization_server,
    oauth_authorize_get,
    oauth_protected_resource,
    oauth_register,
    oauth_token,
)


@pytest.fixture()
def fake_user_factory():
    """Returns a stub find_or_create that maps email -> deterministic token."""
    def factory(email: str) -> str:
        return f"tok-for-{email}"
    return factory


@pytest.fixture()
def app(fake_user_factory):
    """Build a test Starlette app with all OAuth routes."""
    _auth_codes.clear()
    return Starlette(routes=[
        Route("/.well-known/oauth-protected-resource", oauth_protected_resource),
        Route("/.well-known/oauth-authorization-server", oauth_authorization_server),
        Route("/register", oauth_register, methods=["POST"]),
        Route("/authorize", oauth_authorize_get, methods=["GET"]),
        Route("/authorize", make_authorize_post(fake_user_factory), methods=["POST"]),
        Route("/token", oauth_token, methods=["POST"]),
    ])


@pytest.fixture()
def client(app):
    return TestClient(app)


def _pkce_pair() -> tuple[str, str]:
    """Generate (verifier, S256 challenge)."""
    verifier = "abc123" * 8  # 48 chars, well within RFC bounds
    digest = hashlib.sha256(verifier.encode()).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
    return verifier, challenge


# ---------------------------------------------------------------------------

class TestMetadata:

    def test_protected_resource(self, client):
        r = client.get("/.well-known/oauth-protected-resource")
        assert r.status_code == 200
        body = r.json()
        assert "resource" in body
        assert "authorization_servers" in body
        assert "Bearer" in body["bearer_methods_supported"][0] or \
               body["bearer_methods_supported"] == ["header"]

    def test_authorization_server(self, client):
        r = client.get("/.well-known/oauth-authorization-server")
        assert r.status_code == 200
        body = r.json()
        for key in ("issuer", "authorization_endpoint", "token_endpoint",
                    "registration_endpoint", "code_challenge_methods_supported"):
            assert key in body
        assert "S256" in body["code_challenge_methods_supported"]
        assert "authorization_code" in body["grant_types_supported"]


class TestRegister:

    def test_register_returns_canned_client(self, client):
        r = client.post("/register", json={
            "redirect_uris": ["https://perplexity.ai/callback"],
            "grant_types": ["authorization_code"],
        })
        assert r.status_code == 201
        body = r.json()
        assert body["client_id"] == "superfinance-mcp"
        assert body["redirect_uris"] == ["https://perplexity.ai/callback"]

    def test_register_no_body(self, client):
        r = client.post("/register")
        assert r.status_code == 201


class TestAuthorize:

    def test_get_renders_form(self, client):
        r = client.get("/authorize", params={
            "redirect_uri": "https://perplexity.ai/cb",
            "state": "xyz",
            "code_challenge": "abc",
            "code_challenge_method": "S256",
            "client_id": "superfinance-mcp",
        })
        assert r.status_code == 200
        assert "Authorize" in r.text
        # Hidden fields are populated
        assert "https://perplexity.ai/cb" in r.text
        assert "xyz" in r.text

    def test_get_requires_redirect_uri(self, client):
        r = client.get("/authorize")
        assert r.status_code == 400

    def test_get_html_escapes_query_params(self, client):
        # Defend against XSS via state/redirect_uri
        r = client.get("/authorize", params={
            "redirect_uri": "https://x.com/cb",
            "state": '"><script>alert(1)</script>',
        })
        assert r.status_code == 200
        assert "<script>alert(1)</script>" not in r.text
        assert "&lt;script&gt;" in r.text or "&#x27;" in r.text or "&quot;" in r.text

    def test_post_redirects_with_code(self, client):
        verifier, challenge = _pkce_pair()
        r = client.post("/authorize", data={
            "email": "test@example.com",
            "redirect_uri": "https://perplexity.ai/cb",
            "state": "abc",
            "code_challenge": challenge,
            "code_challenge_method": "S256",
        }, follow_redirects=False)
        assert r.status_code == 302
        loc = r.headers["location"]
        assert loc.startswith("https://perplexity.ai/cb?code=")
        assert "state=abc" in loc

    def test_post_invalid_email(self, client):
        r = client.post("/authorize", data={
            "email": "not-an-email",
            "redirect_uri": "https://perplexity.ai/cb",
            "state": "x",
        })
        # Re-renders the form, doesn't redirect
        assert r.status_code == 200
        assert "valid email" in r.text.lower()

    def test_post_rejects_non_s256(self, client):
        r = client.post("/authorize", data={
            "email": "test@example.com",
            "redirect_uri": "https://x.com/cb",
            "code_challenge": "abc",
            "code_challenge_method": "plain",
        })
        assert r.status_code == 200
        assert "S256" in r.text


class TestToken:

    def _start_flow(self, client) -> tuple[str, str, str]:
        """Run /authorize to get a code; returns (code, verifier, redirect_uri)."""
        verifier, challenge = _pkce_pair()
        redirect_uri = "https://perplexity.ai/cb"
        r = client.post("/authorize", data={
            "email": "test@example.com",
            "redirect_uri": redirect_uri,
            "state": "abc",
            "code_challenge": challenge,
            "code_challenge_method": "S256",
        }, follow_redirects=False)
        loc = r.headers["location"]
        # extract ?code=...
        code = loc.split("code=", 1)[1].split("&", 1)[0]
        return code, verifier, redirect_uri

    def test_full_exchange(self, client):
        code, verifier, redirect_uri = self._start_flow(client)
        r = client.post("/token", data={
            "grant_type": "authorization_code",
            "code": code,
            "code_verifier": verifier,
            "redirect_uri": redirect_uri,
        })
        assert r.status_code == 200
        body = r.json()
        assert body["access_token"] == "tok-for-test@example.com"
        assert body["token_type"] == "Bearer"

    def test_code_is_single_use(self, client):
        code, verifier, redirect_uri = self._start_flow(client)
        first = client.post("/token", data={
            "grant_type": "authorization_code",
            "code": code, "code_verifier": verifier, "redirect_uri": redirect_uri,
        })
        assert first.status_code == 200
        # Reuse must fail
        second = client.post("/token", data={
            "grant_type": "authorization_code",
            "code": code, "code_verifier": verifier, "redirect_uri": redirect_uri,
        })
        assert second.status_code == 400
        assert second.json()["error"] == "invalid_grant"

    def test_pkce_mismatch(self, client):
        code, _verifier, redirect_uri = self._start_flow(client)
        r = client.post("/token", data={
            "grant_type": "authorization_code",
            "code": code,
            "code_verifier": "wrong-verifier",
            "redirect_uri": redirect_uri,
        })
        assert r.status_code == 400
        assert r.json()["error"] == "invalid_grant"

    def test_redirect_uri_mismatch(self, client):
        code, verifier, _ = self._start_flow(client)
        r = client.post("/token", data={
            "grant_type": "authorization_code",
            "code": code, "code_verifier": verifier,
            "redirect_uri": "https://attacker.com/cb",
        })
        assert r.status_code == 400

    def test_unknown_code(self, client):
        r = client.post("/token", data={
            "grant_type": "authorization_code",
            "code": "nonexistent",
            "redirect_uri": "https://perplexity.ai/cb",
        })
        assert r.status_code == 400

    def test_unsupported_grant_type(self, client):
        r = client.post("/token", data={
            "grant_type": "client_credentials",
            "code": "x", "redirect_uri": "y",
        })
        assert r.status_code == 400
        assert r.json()["error"] == "unsupported_grant_type"

    def test_accepts_json_body(self, client):
        code, verifier, redirect_uri = self._start_flow(client)
        r = client.post("/token", json={
            "grant_type": "authorization_code",
            "code": code, "code_verifier": verifier, "redirect_uri": redirect_uri,
        })
        assert r.status_code == 200


class TestBearerExtraction:

    def test_extract_bearer(self):
        headers = [(b"authorization", b"Bearer abc123")]
        assert extract_bearer_token(headers) == "abc123"

    def test_extract_bearer_case_insensitive(self):
        headers = [(b"Authorization", b"bearer XYZ")]
        assert extract_bearer_token(headers) == "XYZ"

    def test_no_authorization_header(self):
        headers = [(b"content-type", b"application/json")]
        assert extract_bearer_token(headers) is None

    def test_non_bearer_scheme(self):
        headers = [(b"authorization", b"Basic dXNlcjpwYXNz")]
        assert extract_bearer_token(headers) is None
