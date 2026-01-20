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

Financial data, portfolio management, and visualization tools.

## Portfolio Management (Unified)

Single interface for both manual portfolios and synced brokerage accounts:

- list_portfolios(type): List all portfolios. Filter by "all", "manual", or "synced".
- get_portfolio(id): Get positions in any portfolio with live prices.
- add_portfolio(name, type): Create manual portfolio or connect brokerage (returns OAuth URL).
- delete_portfolio(id): Delete manual portfolio or disconnect brokerage.
- add_position(portfolio_id, symbol, units, cost): Add position to manual portfolio.
- update_position(portfolio_id, position_id, ...): Update position in manual portfolio.
- remove_position(portfolio_id, position_id): Remove position from manual portfolio.
- sync_portfolio(id): Force refresh synced portfolio from brokerage.
- get_transactions(portfolio_id, start, end): Get transaction history (synced only).

Manual portfolios: User-managed, supports private equity (.PVT suffix), manual pricing.
Synced portfolios: Read-only positions from connected brokerages via SnapTrade.

## Liabilities Tracking

Track debts for net worth calculations:

- list_liabilities(): List all liabilities with total balance.
- add_liability(name, balance, type?, interest_rate?, currency?, notes?): Add mortgage, loan, credit card, etc.
- update_liability(liability_id, ...): Update balance or other details.
- remove_liability(liability_id): Remove a liability.

Types: mortgage, auto_loan, credit_card, student_loan, personal_loan, line_of_credit, other.

## Classification Management

Override AI-generated classifications for custom groupings:

- list_categories(): List available categories (Technology, Memory, Commodities, etc.)
- list_classifications(category?): List all symbol→name/category mappings.
- update_classifications(updates): Batch update symbols. Each update has: symbol, name?, category?
- add_categories(categories): Add multiple new categories.

Use update_classifications() to:
- Group related tickers: [{"symbol": "GOOG", "name": "Google"}, {"symbol": "GOOGL", "name": "Google"}]
- Change categories: [{"symbol": "IREN", "category": "AI Infrastructure"}]
- Batch updates for efficiency

## Visualization

Single chart() tool for all visualizations:

- chart(type="portfolio"): Interactive dashboard with pie/treemap toggle, groupings by ticker/name/category/brokerage.
  Shows Assets/Liabilities toggle when liabilities exist, with Net Worth summary in header.
- chart(type="price", tickers="AAPL"): TradingView chart with live market data.
- chart(type="price", tickers="AAPL,MSFT,GOOG"): Compare multiple tickers.

Charts return URLs that expire after 24 hours.

## Aggregate View

- list_all_holdings(currency): Unified view of ALL positions from ALL sources with live prices and AI-classified categories.

## Market Data (Yahoo Finance)

- get_stock_info: Company info for one or more tickers (comma-separated).
- get_historical_stock_prices: Historical OHLCV data.
- get_fx_rate: Currency exchange rates.
- get_option_chain: Options data with Greeks.
- get_option_expiration_dates: Available option expirations.
- get_recommendations: Analyst recommendations.
- get_financial_statement: Income, balance sheet, cash flow.
- get_holder_info: Institutional holders, insider activity.
- get_stock_actions: Dividends and splits.
- get_yahoo_finance_news: News for a ticker.

## Cache Management

- refresh_cache(type): Force refresh prices, fx rates, holdings, or all.
- get_cache_status: Check cache health and refresh times.
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

        # Add health check route
        app.routes.insert(0, Route("/", health_check))
        app.routes.insert(1, Route("/health", health_check))
        # Add chart serving route
        app.routes.insert(2, Route("/charts/{chart_id}", serve_chart))

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
