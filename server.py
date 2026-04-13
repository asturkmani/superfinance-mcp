"""SuperFinance MCP Server - Main entry point."""

import json
import os
from pathlib import Path

from fastmcp import FastMCP
from dotenv import load_dotenv

# Load environment variables from .env file (for local development)
env_path = Path(__file__).parent / '.env'
if env_path.exists():
    load_dotenv(env_path)

from tools.__init___v2 import register_all_tools_v2
from tools.v2_snaptrade import get_snaptrade_client
from users import create_user, get_user, get_user_by_email, current_user_token

# Initialize FastMCP server
yfinance_server = FastMCP(
    "superfinance",
    instructions="""
# SuperFinance MCP Server

Financial data and brokerage integration tools.

## Tools (3 tools)

### 1. market — Yahoo Finance market data

**market(action, tickers, ...)**: Get stock and financial data.

Actions:
- **profile**: Company info, metrics, key stats
- **history**: Historical OHLCV data (period: 1d,5d,1mo,3mo,6mo,1y,2y,5y,10y,ytd,max)
- **quote**: Current price and trading info
- **fx**: Foreign exchange rates
- **actions**: Dividends and stock splits
- **financials**: Income statement, balance sheet, cash flow
- **holders**: Major, institutional, mutual fund holders
- **recommendations**: Analyst recommendations
- **news**: Latest news

Examples:
```
market(action="quote", tickers="AAPL,MSFT")
market(action="history", tickers="AAPL", period="1y")
market(action="profile", tickers="AAPL")
market(action="fx", from_currency="GBP", to_currency="USD")
market(action="financials", ticker="AAPL", financial_type="income_stmt")
```

### 2. options — Yahoo Finance options data

**options(action, ticker, ...)**: Get options chains and analysis.

Actions:
- **chain**: Get option chain for a specific expiration date
- **analyze**: Get options summary with Greeks for nearest expirations

Examples:
```
options(action="chain", ticker="AAPL", expiration_date="2024-06-21", option_type="calls")
options(action="analyze", ticker="AAPL")
```

### 3. snaptrade — Brokerage account management

**snaptrade(action, ...)**: Create accounts and pull holdings via SnapTrade.

Actions:
- **connect**: Get URL to connect a brokerage account
- **accounts**: List connected brokerage accounts
- **holdings**: Get holdings for a specific account

Your SnapTrade credentials are automatically loaded from your user profile.

Examples:
```
snaptrade(action="connect")
snaptrade(action="accounts")
snaptrade(action="holdings", account_id="abc-123")
```
""",
)

# Register all tools
register_all_tools_v2(yfinance_server)


if __name__ == "__main__":
    # Check if we're running in Fly.io or remote environment
    if os.getenv("FLY_APP_NAME") or os.getenv("PORT"):
        port = int(os.getenv("PORT", "8080"))
        print(f"Starting SuperFinance server on HTTP at 0.0.0.0:{port}")

        from starlette.applications import Starlette
        from starlette.responses import JSONResponse, HTMLResponse
        from starlette.requests import Request
        from starlette.routing import Route, Mount
        from starlette.middleware import Middleware
        from starlette.middleware.base import BaseHTTPMiddleware

        def _build_mcp_url(request, token):
            host = request.headers.get("host", f"localhost:{port}")
            scheme = "https" if "fly.dev" in host else request.url.scheme
            return f"{scheme}://{host}/{token}/mcp"

        # --- Signup page ---
        SIGNUP_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>SuperFinance</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
         background: #0a0a0a; color: #e0e0e0; min-height: 100vh;
         display: flex; align-items: center; justify-content: center; }
  .card { background: #151515; border: 1px solid #2a2a2a; border-radius: 12px;
          padding: 40px; max-width: 440px; width: 100%; }
  h1 { font-size: 24px; margin-bottom: 8px; color: #fff; }
  .sub { color: #888; font-size: 14px; margin-bottom: 28px; }
  label { display: block; font-size: 13px; color: #aaa; margin-bottom: 6px; }
  input[type="email"] { width: 100%; padding: 10px 14px; font-size: 15px;
         background: #0a0a0a; border: 1px solid #333; border-radius: 8px;
         color: #fff; outline: none; margin-bottom: 20px; }
  input[type="email"]:focus { border-color: #4f8ff7; }
  button { width: 100%; padding: 12px; font-size: 15px; font-weight: 600;
           background: #4f8ff7; color: #fff; border: none; border-radius: 8px;
           cursor: pointer; }
  button:hover { background: #3a7be0; }
  .result { margin-top: 24px; padding: 16px; border-radius: 8px;
            font-size: 14px; line-height: 1.6; display: none; }
  .result.success { background: #0d2818; border: 1px solid #1a4d2e; }
  .result.error { background: #2d1215; border: 1px solid #5c2228; }
  .mcp-url { word-break: break-all; font-family: monospace; font-size: 13px;
             background: #0a0a0a; padding: 10px; border-radius: 6px;
             margin-top: 8px; user-select: all; color: #7ec8e3; }
  .copy-btn { margin-top: 8px; padding: 6px 12px; font-size: 12px;
              background: #333; border: 1px solid #555; border-radius: 6px;
              color: #ccc; cursor: pointer; width: auto; }
  .copy-btn:hover { background: #444; }
  .spinner { display: none; }
  .spinner.show { display: inline-block; }
</style>
</head>
<body>
<div class="card">
  <h1>SuperFinance</h1>
  <p class="sub">Connect your brokerage accounts to Claude via MCP.</p>
  <div id="signup-form">
    <label for="email">Email address</label>
    <input type="email" id="email" name="email" placeholder="you@example.com" required>
    <button type="button" id="submit-btn">Get my MCP link</button>
  </div>
  <div class="result" id="result"></div>
</div>
<script>
document.getElementById("submit-btn").addEventListener("click", async () => {
  const btn = document.getElementById("submit-btn");
  const result = document.getElementById("result");
  const email = document.getElementById("email").value.trim();
  if (!email || !email.includes("@")) { return; }
  btn.textContent = "Working...";
  btn.disabled = true;
  result.style.display = "none";
  try {
    const resp = await fetch("/signup", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({email})
    });
    const data = await resp.json();
    if (data.mcp_url) {
      const isNew = data.new_account;
      result.className = "result success";
      result.innerHTML = (isNew
        ? "<strong>Account created!</strong>"
        : "<strong>Welcome back!</strong>") + " Here is your MCP link:"
        + '<div class="mcp-url" id="mcp-url">' + data.mcp_url + '</div>'
        + '<button class="copy-btn" id="copy-btn">Copy to clipboard</button>'
        + '<p style="margin-top:12px;color:#888;font-size:13px;">Add this URL as a remote MCP server in Claude Desktop or claude.ai.</p>';
      document.getElementById("copy-btn").addEventListener("click", function() {
        navigator.clipboard.writeText(document.getElementById("mcp-url").textContent);
        this.textContent = "Copied!";
      });
    } else {
      result.className = "result error";
      result.textContent = data.error || "Something went wrong.";
    }
    result.style.display = "block";
  } catch (err) {
    result.className = "result error";
    result.textContent = "Network error: " + err.message;
    result.style.display = "block";
  } finally {
    btn.textContent = "Get my MCP link";
    btn.disabled = false;
  }
});
</script>
</body>
</html>"""

        async def signup_page(request: Request):
            return HTMLResponse(SIGNUP_HTML)

        async def signup_handler(request: Request):
            """POST /signup — create or find user by email."""
            try:
                body = await request.json()
            except Exception:
                return JSONResponse({"error": "Invalid JSON body"}, status_code=400)

            email = (body.get("email") or "").strip().lower()
            if not email or "@" not in email:
                return JSONResponse({"error": "A valid email is required"}, status_code=400)

            # Check if user already exists
            existing = get_user_by_email(email)
            if existing:
                token, _ = existing
                return JSONResponse({
                    "new_account": False,
                    "mcp_url": _build_mcp_url(request, token),
                })

            # Register new user with SnapTrade
            client = get_snaptrade_client()
            if not client:
                return JSONResponse({"error": "SnapTrade not configured on server"}, status_code=500)

            # Use email as the SnapTrade user_id (unique per user)
            snaptrade_user_id = email
            try:
                response = client.authentication.register_snap_trade_user(user_id=snaptrade_user_id)
                data = response.body if hasattr(response, 'body') else response
                if hasattr(data, 'to_dict'):
                    data = data.to_dict()
                user_secret = (
                    data.get("userSecret") if isinstance(data, dict)
                    else getattr(data, 'user_secret', None)
                )
            except Exception as e:
                return JSONResponse(
                    {"error": f"Registration failed: {e}"},
                    status_code=400,
                )

            if not user_secret:
                return JSONResponse({"error": "No user_secret returned"}, status_code=500)

            token = create_user(email, snaptrade_user_id, user_secret)

            return JSONResponse({
                "new_account": True,
                "mcp_url": _build_mcp_url(request, token),
            })

        async def health_check(request: Request):
            return JSONResponse({
                "status": "ok",
                "service": "superfinance",
            })

        # --- Middleware to extract user token from /{token}/mcp paths ---
        class UserTokenMiddleware(BaseHTTPMiddleware):
            async def dispatch(self, request, call_next):
                path = request.url.path
                # Match /{token}/mcp or /{token}/mcp/...
                parts = path.strip("/").split("/")
                if len(parts) >= 2 and parts[1] == "mcp":
                    token = parts[0]
                    user = get_user(token)
                    if user:
                        tok = current_user_token.set(token)
                        try:
                            response = await call_next(request)
                        finally:
                            current_user_token.reset(tok)
                        return response
                    else:
                        return JSONResponse(
                            {"error": "Invalid token. Register at POST /register first."},
                            status_code=401,
                        )
                return await call_next(request)

        # --- Build the app ---
        # Get the MCP ASGI app from FastMCP
        mcp_app = yfinance_server.http_app(path="/mcp")

        # Create a wrapper that mounts MCP under /{token}/mcp
        async def mcp_proxy(request: Request):
            """Forward /{token}/mcp requests to the MCP app."""
            # Strip the token prefix so the MCP app sees /mcp
            token = request.path_params["token"]
            scope = dict(request.scope)
            original_path = scope["path"]
            # Rewrite path: /{token}/mcp/... -> /mcp/...
            scope["path"] = original_path[len(f"/{token}"):]
            if not scope["path"]:
                scope["path"] = "/"

            async def receive():
                return await request._receive()

            response_started = False
            response_headers = None
            body_parts = []

            async def send(message):
                nonlocal response_started, response_headers
                if message["type"] == "http.response.start":
                    response_started = True
                    response_headers = message
                elif message["type"] == "http.response.body":
                    body_parts.append(message.get("body", b""))

            await mcp_app(scope, receive, send)

            from starlette.responses import Response
            if response_headers:
                headers = dict(response_headers.get("headers", []))
                return Response(
                    content=b"".join(body_parts),
                    status_code=response_headers.get("status", 200),
                    headers={
                        k.decode() if isinstance(k, bytes) else k:
                        v.decode() if isinstance(v, bytes) else v
                        for k, v in response_headers.get("headers", [])
                    },
                )
            return Response(content=b"".join(body_parts))

        app = Starlette(
            routes=[
                Route("/", signup_page),
                Route("/signup", signup_handler, methods=["POST"]),
                Route("/health", health_check),
                Route("/{token}/mcp", mcp_proxy, methods=["GET", "POST"]),
                # Also mount the raw MCP app for admin/env-var usage
                Mount("/mcp", app=mcp_app),
            ],
            middleware=[Middleware(UserTokenMiddleware)],
        )

        print("Signup page: /")
        print("Per-user MCP: /{token}/mcp")
        print("Admin MCP: /mcp")

        import uvicorn
        uvicorn.run(app, host="0.0.0.0", port=port)
    else:
        # Local development - use stdio
        print("Starting SuperFinance MCP server with stdio transport")
        yfinance_server.run()
