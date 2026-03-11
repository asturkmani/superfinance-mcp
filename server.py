"""SuperFinance MCP Server - Main entry point."""

import os
from pathlib import Path

from fastmcp import FastMCP
from dotenv import load_dotenv

import cache
import refresh
from tools.__init___v2 import register_all_tools_v2

# Load environment variables from .env file (for local development)
env_path = Path(__file__).parent / '.env'
if env_path.exists():
    load_dotenv(env_path)


# Initialize FastMCP server
yfinance_server = FastMCP(
    "superfinance",
    instructions="""
# SuperFinance MCP Server

Financial data, account management, and visualization tools.

## Tool Overview (16 consolidated tools)

All tools use an `action` parameter to dispatch to specific operations:

1. **account** - Manage accounts (create|list|get|update|delete)
2. **holding** - Manage holdings (list|list_all|add|update|remove)
3. **transaction** - Manage transactions (list|add|delete)
4. **liability** - Manage liabilities (list|add|update|remove)
5. **classify** - Manage classifications (list_categories|list|add_categories|update)
6. **dashboard** - Manage dashboards (create|list|get|delete|add_widget|update_widget|remove_widget)
7. **chart** - Generate visualizations (portfolio|price)
8. **market** - Market data (profile|history|quote|fx|actions|financials|holders|recommendations|news)
9. **options** - Options data (chain|analyze)
10. **discover** - Search securities (search|lookup)
11. **analyze** - Analytics (technicals|risk|performance|ratios)
12. **portfolio** - Portfolio analytics (technicals|risk|performance|ratios|correlation|reconcile)
13. **sync** - SnapTrade sync (connect|status|sync_to_db|sync_accounts|sync_holdings|sync_transactions|refresh|disconnect)
14. **cache** - Cache management (status|refresh)
15. **token** - API tokens (create|list|revoke)
16. **calculate** - Python calculations

## Account Management

**account(action, ...)**: Manage accounts (portfolio buckets)
- create: Create manual account for tracking
- list: List all accounts (manual and synced)
- get: Get account details
- update: Update account name (manual only)
- delete: Delete account and all holdings/transactions

Examples:
```
account(action="create", name="Vanguard ISA", currency="GBP")
account(action="list")
account(action="delete", account_id="acc_123")
```

## Holdings Management

**holding(action, ...)**: Manage positions
- list: Get holdings for an account
- list_all: Get all holdings with live prices
- add: Add/update holding in manual account
- update: Update holding details
- remove: Remove holding

Examples:
```
holding(action="list", account_id="acc_123")
holding(action="list_all", reporting_currency="GBP")
holding(action="add", account_id="acc_123", symbol="AAPL", quantity=10)
```

## Transactions

**transaction(action, ...)**: Manage transactions
- list: Get transactions (by account or symbol)
- add: Add transaction to manual account
- delete: Delete transaction

Examples:
```
transaction(action="list", account_id="acc_123")
transaction(action="add", account_id="acc_123", symbol="AAPL", date="2024-01-15", transaction_type="buy", quantity=10, price=150.00)
```

## Liabilities

**liability(action, ...)**: Track debts
- list: List all liabilities
- add: Add mortgage, loan, credit card, etc.
- update: Update balance or details
- remove: Remove liability

Examples:
```
liability(action="list")
liability(action="add", name="Home Mortgage", balance=450000, type="mortgage", interest_rate=4.5)
```

## Classifications

**classify(action, ...)**: Manage categories and name mappings
- list_categories: List available categories
- list: List all classifications (filter by category)
- add_categories: Add new categories
- update: Update symbol classifications

Examples:
```
classify(action="list_categories")
classify(action="update", updates=[{"symbol": "IREN", "category": "AI Infrastructure"}])
```

## Dashboards

**dashboard(action, ...)**: Custom dashboards with widgets
- create: Create dashboard
- list: List all dashboards
- get: Get dashboard URL
- delete: Delete dashboard
- add_widget: Add widget (stock_chart, portfolio_pie, etc.)
- update_widget: Update widget config
- remove_widget: Remove widget

Examples:
```
dashboard(action="create", name="My Portfolio")
dashboard(action="add_widget", dashboard_id="dash_123", widget_type="portfolio_pie")
```

## Visualization

**chart(type, ...)**: Generate charts
- portfolio: Interactive dashboard (pie/treemap toggle)
- price: TradingView price charts

Examples:
```
chart(type="portfolio", currency="GBP")
chart(type="price", tickers="AAPL,MSFT")
```

## Market Data

**market(action, tickers, ...)**: Yahoo Finance data
- profile: Company info and metrics
- history: Historical OHLCV data
- quote: Current price
- fx: Exchange rates
- actions: Dividends and splits
- financials: Financial statements
- holders: Holder information
- recommendations: Analyst recommendations
- news: Latest news

Examples:
```
market(action="quote", tickers="AAPL,MSFT")
market(action="history", tickers="AAPL", period="1y")
market(action="fx", from_currency="GBP", to_currency="USD")
```

## Options

**options(action, ticker, ...)**: Options data
- chain: Get option chain for expiration
- analyze: Get options analysis with Greeks

Examples:
```
options(action="chain", ticker="AAPL", expiration_date="2024-06-21", option_type="calls")
options(action="analyze", ticker="AAPL")
```

## Discovery

**discover(action, ...)**: Search securities
- search: Search by sector, industry, country
- lookup: Get ticker details

Examples:
```
discover(action="search", type="equity", sector="Technology")
discover(action="lookup", ticker="AAPL")
```

## Analytics

**analyze(action, tickers, ...)**: Financial analysis
- technicals: RSI, MACD, Bollinger, EMA
- risk: VaR, CVaR, max drawdown, beta, Sharpe
- performance: CAGR, alpha
- ratios: P/E, ROE, debt ratios

Examples:
```
analyze(action="technicals", tickers="AAPL", indicators="rsi,macd")
analyze(action="risk", tickers="AAPL,MSFT", period="3y")
```

## Portfolio Analytics

**portfolio(action, ...)**: Portfolio-aware analytics
- technicals: Technical indicators for all positions
- risk: Risk metrics for all positions
- performance: Performance for all positions
- ratios: Financial ratios for all positions
- correlation: Correlation matrix
- reconcile: Reconcile holdings vs transactions

Examples:
```
portfolio(action="risk", period="3y")
portfolio(action="correlation")
portfolio(action="reconcile")
```

## SnapTrade Sync

**sync(action, ...)**: Brokerage integration
- connect: Get connection URL
- status: List connected accounts
- sync_to_db: Sync all to local database
- sync_accounts: List accounts
- sync_holdings: Get holdings for account
- sync_transactions: Get transactions
- refresh: Manual refresh
- disconnect: Remove connection

Examples:
```
sync(action="connect")
sync(action="sync_to_db")
sync(action="status")
```

## Cache & Tokens

**cache(action, ...)**: Cache management
- status: Get cache health
- refresh: Force refresh (prices|fx|holdings|all)

**token(action, ...)**: API tokens
- create: Create new token
- list: List tokens (masked)
- revoke: Revoke token

**calculate(expression)**: Execute Python calculations
- Math, numpy, pandas available
- Financial computations

Examples:
```
cache(action="status")
token(action="create", name="desktop")
calculate("sum([100, 200, 300])")
```
""",
)

# Register all tools from modules (V2 consolidated)
register_all_tools_v2(yfinance_server)


if __name__ == "__main__":
    # For local testing, use stdio
    # For remote deployment, use HTTP transport

    # Check if we're running in Fly.io or remote environment
    if os.getenv("FLY_APP_NAME") or os.getenv("PORT"):
        # Set up OAuth auth for HTTP mode (Claude Desktop requires OAuth 2.1)
        from auth import VaultOAuthProvider
        base_url = os.getenv("VAULT_BASE_URL", "https://superfinance-mcp.fly.dev")
        vault_oauth = VaultOAuthProvider(base_url=base_url)
        yfinance_server.auth = vault_oauth
        
        # Remote deployment - use HTTP
        port = int(os.getenv("PORT", "8080"))
        print(f"Starting SuperFinance server on HTTP at 0.0.0.0:{port}")

        # Start background scheduler for cache refresh if cache is available
        if cache.is_cache_available():
            print("Redis cache available, starting background scheduler...")
            refresh.start_scheduler()
        else:
            print("Redis cache not available, background refresh disabled")

        # Create the MCP app (Starlette-based)
        app = yfinance_server.http_app()

        # Add a simple health check endpoint for Fly.io
        from starlette.responses import JSONResponse, HTMLResponse
        from starlette.routing import Route, Mount

        async def landing_page(request):
            """Serve the landing page."""
            import pathlib
            html_path = pathlib.Path(__file__).parent / "static" / "index.html"
            if html_path.exists():
                return HTMLResponse(html_path.read_text())
            return JSONResponse({"error": "Landing page not found"}, status_code=404)

        async def health_check(request):
            cache_status = "ok" if cache.is_cache_available() else "unavailable"
            scheduler_status = refresh.get_scheduler_status()
            return JSONResponse({
                "status": "ok",
                "service": "superfinance",
                "mcp": "/mcp (POST)",
                "api": "/api/docs",
                "cache": cache_status,
                "scheduler": scheduler_status
            })

        async def serve_chart(request):
            """Serve cached chart HTML."""
            chart_id = request.path_params["chart_id"]
            html = cache.get_cached_chart(chart_id)
            if html:
                return HTMLResponse(html)
            return JSONResponse(
                {"error": "Chart expired or not found"},
                status_code=404
            )

        async def serve_dashboard(request):
            """GET /d/{dashboard_id} - Serve dashboard page."""
            from db import queries
            from helpers.dashboard_templates import generate_dashboard_html
            from helpers.widget_data import fetch_all_widget_data
            
            dashboard_id = request.path_params["dashboard_id"]
            dashboard = queries.get_dashboard(dashboard_id)
            if not dashboard:
                return JSONResponse({"error": "Dashboard not found"}, status_code=404)
            
            widgets = queries.list_widgets(dashboard_id)
            user_id = dashboard["user_id"]
            
            # Fetch real data for all widgets
            widget_data = await fetch_all_widget_data(widgets, user_id)
            
            html = generate_dashboard_html(dashboard, widgets, widget_data)
            return HTMLResponse(html)

        async def signup(request):
            """POST /signup - Create account and get MCP token."""
            from db import queries
            body = await request.json()
            email = body.get("email")
            name = body.get("name")
            password = body.get("password")
            
            if not email:
                return JSONResponse({"error": "email required"}, status_code=400)
            
            try:
                user_id, token = queries.signup_user(email, name, password)
                base = os.getenv("VAULT_BASE_URL", "https://superfinance-mcp.fly.dev")
                mcp_url = f"{base}/mcp/{token}"
                return JSONResponse({
                    "user_id": user_id,
                    "token": token,
                    "mcp_url": mcp_url,
                    "instructions": "Add this URL as your MCP server — no extra auth config needed",
                    "claude_desktop_config": {
                        "mcpServers": {
                            "vault": {
                                "url": mcp_url
                            }
                        }
                    }
                })
            except ValueError as e:
                return JSONResponse({"error": str(e)}, status_code=409)

        async def vault_login_page(request):
            """Serve the OAuth login page."""
            import pathlib
            html_path = pathlib.Path(__file__).parent / "static" / "login.html"
            if html_path.exists():
                return HTMLResponse(html_path.read_text())
            return JSONResponse({"error": "Login page not found"}, status_code=404)

        async def vault_auth_endpoint(request):
            """Handle login/signup from the OAuth login page."""
            from db import queries
            import hashlib
            
            body = await request.json()
            request_id = body.get("request_id")
            email = body.get("email")
            password = body.get("password")
            action = body.get("action", "login")
            name = body.get("name")
            
            if not request_id or not email or not password:
                return JSONResponse({"error": "Missing required fields"}, status_code=400)
            
            if action == "signup":
                # Create new user
                try:
                    user_id, _ = queries.signup_user(email, name, password)
                except ValueError as e:
                    return JSONResponse({"error": str(e)}, status_code=409)
            else:
                # Login — verify credentials
                user = queries.get_user_by_email(email)
                if not user:
                    return JSONResponse({"error": "Invalid email or password"}, status_code=401)
                
                pw_hash = hashlib.sha256(password.encode()).hexdigest()
                if user.get("password_hash") != pw_hash:
                    return JSONResponse({"error": "Invalid email or password"}, status_code=401)
                
                user_id = user["id"]
            
            # Complete the OAuth flow
            try:
                redirect_url = await vault_oauth.complete_authorization(request_id, user_id)
                return JSONResponse({"redirect_url": redirect_url})
            except Exception as e:
                return JSONResponse({"error": str(e)}, status_code=400)

        # Add routes
        app.routes.insert(0, Route("/", landing_page))
        app.routes.insert(1, Route("/health", health_check))
        app.routes.insert(2, Route("/vault-login", vault_login_page))
        app.routes.insert(3, Route("/vault-auth", vault_auth_endpoint, methods=["POST"]))
        # Add signup route
        app.routes.insert(2, Route("/signup", signup, methods=["POST"]))
        # Add chart serving route
        app.routes.insert(3, Route("/charts/{chart_id}", serve_chart))
        # Add dashboard serving route
        app.routes.insert(4, Route("/d/{dashboard_id}", serve_dashboard))

        # Mount the FastAPI REST API
        from api import create_api_app
        api_app = create_api_app()
        app.mount("/", api_app)  # Mount at root, FastAPI routes are prefixed with /api

        print("REST API available at /api/docs")
        print("MCP protocol available at /mcp")

        # Run with uvicorn
        import uvicorn
        uvicorn.run(app, host="0.0.0.0", port=port)
    else:
        # Local development - use stdio
        print("Starting SuperFinance MCP server with stdio transport")
        print("Note: REST API is only available in HTTP mode (set PORT env var)")
        yfinance_server.run()
