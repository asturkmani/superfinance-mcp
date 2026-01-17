"""SuperFinance MCP Server - Main entry point."""

import os
from pathlib import Path

from fastmcp import FastMCP
from dotenv import load_dotenv

import cache
import refresh
from tools import register_all_tools

# Load environment variables from .env file (for local development)
env_path = Path(__file__).parent / '.env'
if env_path.exists():
    load_dotenv(env_path)


# Initialize FastMCP server
yfinance_server = FastMCP(
    "superfinance",
    instructions="""
# SuperFinance MCP Server

This server provides financial data from Yahoo Finance, brokerage integration via SnapTrade, and manual portfolio management for private investments.

## Yahoo Finance Tools
- get_historical_stock_prices: Get historical OHLCV data for a ticker symbol
- get_stock_info: Get comprehensive stock information (price, metrics, company info)
- get_yahoo_finance_news: Get news for a given ticker symbol
- get_stock_actions: Get stock dividends and stock splits
- get_financial_statement: Get income statement, balance sheet, or cash flow
- get_holder_info: Get major holders, institutional holders, insider transactions
- get_option_expiration_dates: Get available options expiration dates
- get_option_chain: Get options chain for a ticker, expiration date, and type
- get_recommendations: Get analyst recommendations or upgrades/downgrades
- get_fx_rate: Get current foreign exchange rate between two currencies

## Unified Holdings
- list_all_holdings: Get all holdings from both SnapTrade brokerage accounts AND manual portfolios with live Yahoo Finance prices

## SnapTrade Tools (Brokerage Integration)
- snaptrade_register_user: Register a new user for brokerage connections
- snaptrade_get_connection_url: Get URL for user to connect brokerage accounts
- snaptrade_list_accounts: List all connected brokerage accounts
- snaptrade_get_holdings: Get holdings for a specific account
- snaptrade_get_transactions: Get transaction history
- snaptrade_disconnect_account: Remove a brokerage connection
- snaptrade_refresh_account: Trigger manual refresh of holdings data

## Manual Portfolio Tools (Private Investments)
For tracking private equity, real estate, and other investments not in connected brokerages:
- manual_create_portfolio: Create a new portfolio for private investments
- manual_add_position: Add a position (with optional Yahoo Finance ticker or manual price)
- manual_update_position: Update units, cost, price, or other position details
- manual_remove_position: Remove a position from a portfolio
- manual_delete_portfolio: Delete an entire portfolio
- manual_list_portfolios: List all portfolios with summary info
- manual_get_portfolio: Get portfolio with live prices from Yahoo Finance

For private companies like SpaceX, use secondary market tickers (e.g., STRB for Starbase) or set a manual_price.

## Cache Management Tools
Data is cached in Redis to reduce API calls and improve response times:
- refresh_cache: Force refresh cached data (prices, fx rates, holdings, or all)
- get_cache_status: Check cache health, last refresh times, and tracked symbols

Cache refresh schedules:
- Stock prices: Every 5 minutes
- FX rates: Every 5 minutes
- Holdings: Daily at 6 AM UTC
""",
)

# Register all tools from modules
register_all_tools(yfinance_server)


if __name__ == "__main__":
    # For local testing, use stdio
    # For remote deployment, use HTTP transport

    # Check if we're running in Fly.io or remote environment
    if os.getenv("FLY_APP_NAME") or os.getenv("PORT"):
        # Remote deployment - use HTTP
        port = int(os.getenv("PORT", "8080"))
        print(f"Starting SuperFinance MCP server on HTTP at 0.0.0.0:{port}")

        # Start background scheduler for cache refresh if cache is available
        if cache.is_cache_available():
            print("Redis cache available, starting background scheduler...")
            refresh.start_scheduler()
        else:
            print("Redis cache not available, background refresh disabled")

        # Create the MCP app
        app = yfinance_server.http_app()

        # Add a simple health check endpoint for Fly.io
        from starlette.responses import JSONResponse
        from starlette.routing import Route

        async def health_check(request):
            cache_status = "ok" if cache.is_cache_available() else "unavailable"
            scheduler_status = refresh.get_scheduler_status()
            return JSONResponse({
                "status": "ok",
                "service": "superfinance-mcp",
                "cache": cache_status,
                "scheduler": scheduler_status
            })

        # Add health check route
        app.routes.insert(0, Route("/", health_check))
        app.routes.insert(1, Route("/health", health_check))

        # Run with uvicorn
        import uvicorn
        uvicorn.run(app, host="0.0.0.0", port=port)
    else:
        # Local development - use stdio
        print("Starting SuperFinance MCP server with stdio transport")
        yfinance_server.run()
