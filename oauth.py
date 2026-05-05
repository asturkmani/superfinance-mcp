"""Minimal OAuth 2.1 + Dynamic Client Registration shim.

Bridges OAuth-only MCP clients (Perplexity, ChatGPT) to our existing
URL-token auth model. The "access_token" returned is the user's existing
SuperFinance token — same credential, OAuth-shaped wrapper.

Endpoints:
  GET  /.well-known/oauth-protected-resource   (RFC 9728)
  GET  /.well-known/oauth-authorization-server (RFC 8414)
  POST /register                                (RFC 7591 DCR)
  GET  /authorize                               (login form)
  POST /authorize                               (issues auth code)
  POST /token                                   (exchanges code for token)
"""

import base64
import hashlib
import secrets
import time
from typing import Callable

from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse, RedirectResponse


# In-memory auth code store: code -> {user_token, code_challenge, expires_at, redirect_uri}
# Codes are short-lived (10 minutes) and single-use. In-memory is fine because
# losing them on restart only affects the small window of in-flight authorizations.
_auth_codes: dict = {}

CODE_TTL_SECONDS = 600  # 10 minutes


def _base_url(request: Request) -> str:
    host = request.headers.get("host", "localhost")
    scheme = "https" if "fly.dev" in host else request.url.scheme
    return f"{scheme}://{host}"


def _purge_expired_codes() -> None:
    now = time.time()
    expired = [k for k, v in _auth_codes.items() if v["expires_at"] < now]
    for k in expired:
        _auth_codes.pop(k, None)


async def oauth_protected_resource(request: Request) -> JSONResponse:
    """RFC 9728 — protected resource metadata."""
    base = _base_url(request)
    return JSONResponse({
        "resource": f"{base}/mcp",
        "authorization_servers": [base],
        "bearer_methods_supported": ["header"],
        "scopes_supported": ["mcp"],
    })


async def oauth_authorization_server(request: Request) -> JSONResponse:
    """RFC 8414 — authorization server metadata."""
    base = _base_url(request)
    return JSONResponse({
        "issuer": base,
        "authorization_endpoint": f"{base}/authorize",
        "token_endpoint": f"{base}/token",
        "registration_endpoint": f"{base}/register",
        "response_types_supported": ["code"],
        "grant_types_supported": ["authorization_code"],
        "code_challenge_methods_supported": ["S256"],
        "token_endpoint_auth_methods_supported": ["none"],
        "scopes_supported": ["mcp"],
    })


async def oauth_register(request: Request) -> JSONResponse:
    """RFC 7591 — dynamic client registration. Returns a canned client_id."""
    try:
        body = await request.json()
    except Exception:
        body = {}
    return JSONResponse({
        "client_id": "superfinance-mcp",
        "client_id_issued_at": int(time.time()),
        "redirect_uris": body.get("redirect_uris", []),
        "grant_types": ["authorization_code"],
        "response_types": ["code"],
        "token_endpoint_auth_method": "none",
        "scope": "mcp",
    }, status_code=201)


_AUTHORIZE_HTML = """<!DOCTYPE html>
<html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Authorize SuperFinance</title>
<style>
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
       background: #0a0a0a; color: #e0e0e0; min-height: 100vh;
       display: flex; align-items: center; justify-content: center; padding: 16px; }
.card { background: #151515; border: 1px solid #2a2a2a; border-radius: 12px;
        padding: 40px; max-width: 440px; width: 100%; }
h1 { font-size: 22px; margin-bottom: 8px; color: #fff; }
.sub { color: #888; font-size: 14px; margin-bottom: 28px; line-height: 1.5; }
label { display: block; font-size: 13px; color: #aaa; margin-bottom: 6px; }
input[type="email"] { width: 100%; padding: 10px 14px; font-size: 15px;
       background: #0a0a0a; border: 1px solid #333; border-radius: 8px;
       color: #fff; outline: none; margin-bottom: 20px; }
input[type="email"]:focus { border-color: #4f8ff7; }
button { width: 100%; padding: 12px; font-size: 15px; font-weight: 600;
         background: #4f8ff7; color: #fff; border: none; border-radius: 8px;
         cursor: pointer; }
button:hover { background: #3a7be0; }
.err { color: #f87171; font-size: 13px; margin-top: -10px; margin-bottom: 14px; }
</style>
</head><body>
<div class="card">
<h1>Authorize access</h1>
<p class="sub">A client wants to connect to your SuperFinance MCP server.
Enter your email to continue. New users will be registered automatically.</p>
<form method="post" action="/authorize">
<input type="hidden" name="redirect_uri" value="__REDIRECT_URI__">
<input type="hidden" name="state" value="__STATE__">
<input type="hidden" name="code_challenge" value="__CODE_CHALLENGE__">
<input type="hidden" name="code_challenge_method" value="__CODE_CHALLENGE_METHOD__">
<input type="hidden" name="client_id" value="__CLIENT_ID__">
__ERROR__
<label for="email">Email address</label>
<input type="email" id="email" name="email" placeholder="you@example.com" required autofocus>
<button type="submit">Authorize</button>
</form>
</div>
</body></html>"""


def _html_escape(s: str) -> str:
    return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")\
        .replace('"', "&quot;").replace("'", "&#x27;")


def _render_authorize(request: Request, error: str = "") -> HTMLResponse:
    qp = dict(request.query_params)
    redirect_uri = _html_escape(qp.get("redirect_uri", ""))
    state = _html_escape(qp.get("state", ""))
    code_challenge = _html_escape(qp.get("code_challenge", ""))
    code_challenge_method = _html_escape(qp.get("code_challenge_method", ""))
    client_id = _html_escape(qp.get("client_id", ""))
    err_html = f'<div class="err">{_html_escape(error)}</div>' if error else ""
    html = (_AUTHORIZE_HTML
            .replace("__REDIRECT_URI__", redirect_uri)
            .replace("__STATE__", state)
            .replace("__CODE_CHALLENGE__", code_challenge)
            .replace("__CODE_CHALLENGE_METHOD__", code_challenge_method)
            .replace("__CLIENT_ID__", client_id)
            .replace("__ERROR__", err_html))
    return HTMLResponse(html)


async def oauth_authorize_get(request: Request) -> HTMLResponse:
    """Render the login page with OAuth params preserved as hidden fields."""
    qp = request.query_params
    if not qp.get("redirect_uri"):
        return HTMLResponse("Missing redirect_uri", status_code=400)
    return _render_authorize(request)


def _verify_pkce_s256(code_verifier: str, code_challenge: str) -> bool:
    """Verify PKCE S256: base64url(sha256(code_verifier)) == code_challenge."""
    if not code_verifier or not code_challenge:
        return False
    digest = hashlib.sha256(code_verifier.encode("ascii")).digest()
    expected = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return secrets.compare_digest(expected, code_challenge)


def make_authorize_post(find_or_create_user: Callable[[str], str]):
    """Factory for POST /authorize handler. Closure captures user-creation fn."""

    async def handler(request: Request):
        form = await request.form()
        email = (form.get("email") or "").strip().lower()
        redirect_uri = form.get("redirect_uri", "")
        state = form.get("state", "")
        code_challenge = form.get("code_challenge", "")
        code_challenge_method = form.get("code_challenge_method", "")

        # Build a request-like object for the error renderer
        class _ReqShim:
            def __init__(self, qp):
                self.query_params = qp
        shim = _ReqShim({
            "redirect_uri": redirect_uri, "state": state,
            "code_challenge": code_challenge,
            "code_challenge_method": code_challenge_method,
        })

        if not email or "@" not in email:
            return _render_authorize(shim, "Please enter a valid email address.")
        if not redirect_uri:
            return HTMLResponse("Missing redirect_uri", status_code=400)
        if code_challenge and code_challenge_method.upper() != "S256":
            return _render_authorize(shim, "Only S256 code_challenge_method is supported.")

        try:
            user_token = find_or_create_user(email)
        except Exception as e:
            return _render_authorize(shim, f"Could not create account: {e}")

        _purge_expired_codes()
        code = secrets.token_urlsafe(32)
        _auth_codes[code] = {
            "user_token": user_token,
            "code_challenge": code_challenge,
            "expires_at": time.time() + CODE_TTL_SECONDS,
            "redirect_uri": redirect_uri,
        }

        sep = "&" if "?" in redirect_uri else "?"
        url = f"{redirect_uri}{sep}code={code}"
        if state:
            url += f"&state={state}"
        return RedirectResponse(url=url, status_code=302)

    return handler


async def oauth_token(request: Request) -> JSONResponse:
    """Exchange auth code for access token."""
    # OAuth clients send form-urlencoded by default; some send JSON. Accept both.
    form_data: dict = {}
    try:
        form = await request.form()
        form_data = dict(form)
    except Exception:
        pass
    if not form_data:
        try:
            form_data = await request.json()
        except Exception:
            return JSONResponse({"error": "invalid_request"}, status_code=400)

    if form_data.get("grant_type") != "authorization_code":
        return JSONResponse({"error": "unsupported_grant_type"}, status_code=400)

    code = form_data.get("code")
    code_verifier = form_data.get("code_verifier", "")
    redirect_uri = form_data.get("redirect_uri", "")

    _purge_expired_codes()
    record = _auth_codes.pop(code, None)  # single-use
    if not record:
        return JSONResponse({
            "error": "invalid_grant",
            "error_description": "code not found or already used",
        }, status_code=400)

    if record["expires_at"] < time.time():
        return JSONResponse({
            "error": "invalid_grant",
            "error_description": "code expired",
        }, status_code=400)

    if record["redirect_uri"] != redirect_uri:
        return JSONResponse({
            "error": "invalid_grant",
            "error_description": "redirect_uri mismatch",
        }, status_code=400)

    # If the original /authorize had a PKCE challenge, the verifier must match.
    if record["code_challenge"]:
        if not _verify_pkce_s256(code_verifier, record["code_challenge"]):
            return JSONResponse({
                "error": "invalid_grant",
                "error_description": "PKCE verification failed",
            }, status_code=400)

    return JSONResponse({
        "access_token": record["user_token"],
        "token_type": "Bearer",
        "scope": "mcp",
    })


def extract_bearer_token(headers: list) -> str | None:
    """Pull a bearer token from ASGI headers list. Returns None if absent."""
    for name, value in headers:
        if name.decode("latin-1").lower() == "authorization":
            v = value.decode("latin-1")
            if v.lower().startswith("bearer "):
                return v[7:].strip()
    return None
