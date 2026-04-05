"""SuperFinance MCP Server - Main entry point."""

import os
from pathlib import Path

from fastmcp import FastMCP
from dotenv import load_dotenv

# Load environment variables from .env file (for local development)
env_path = Path(__file__).parent / '.env'
if env_path.exists():
    load_dotenv(env_path)

from tools.__init___v2 import register_all_tools_v2

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
- **register**: Create a new SnapTrade user
- **connect**: Get URL to connect a brokerage account
- **accounts**: List connected brokerage accounts
- **holdings**: Get holdings for a specific account

Examples:
```
snaptrade(action="register", user_id="my-user-123")
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

        # Create the MCP app (Starlette-based)
        app = yfinance_server.http_app()

        # Add a simple health check endpoint
        from starlette.responses import JSONResponse
        from starlette.routing import Route

        async def health_check(request):
            return JSONResponse({
                "status": "ok",
                "service": "superfinance",
                "mcp": "/mcp (POST)",
            })

        app.routes.insert(0, Route("/health", health_check))

        print("MCP protocol available at /mcp")

        # Run with uvicorn
        import uvicorn
        uvicorn.run(app, host="0.0.0.0", port=port)
    else:
        # Local development - use stdio
        print("Starting SuperFinance MCP server with stdio transport")
        yfinance_server.run()
