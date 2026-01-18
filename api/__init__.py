"""REST API module - FastAPI routes for SuperFinance."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routes import stocks, snaptrade, holdings, portfolios, cache as cache_routes


def create_api_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="SuperFinance API",
        description="""
REST API for financial data aggregation.

## Features

- **Stocks**: Yahoo Finance data (prices, info, news, financials, options)
- **SnapTrade**: Brokerage integration (accounts, holdings, transactions)
- **Holdings**: Unified portfolio view across all sources
- **Portfolios**: Manual portfolio management for private investments
- **Cache**: Cache management and status

## Authentication

SnapTrade endpoints require user credentials. You can either:
- Pass `user_id` and `user_secret` as query parameters
- Set `SNAPTRADE_USER_ID` and `SNAPTRADE_USER_SECRET` environment variables
        """,
        version="1.0.0",
        docs_url="/api/docs",
        redoc_url="/api/redoc",
        openapi_url="/api/openapi.json"
    )

    # Configure CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # Configure for production
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Include routers
    app.include_router(stocks.router, prefix="/api/stocks", tags=["Stocks"])
    app.include_router(snaptrade.router, prefix="/api/snaptrade", tags=["SnapTrade"])
    app.include_router(holdings.router, prefix="/api/holdings", tags=["Holdings"])
    app.include_router(portfolios.router, prefix="/api/portfolios", tags=["Portfolios"])
    app.include_router(cache_routes.router, prefix="/api/cache", tags=["Cache"])

    @app.get("/api", tags=["Health"])
    async def api_root():
        """API health check and info."""
        return {
            "name": "SuperFinance API",
            "version": "1.0.0",
            "docs": "/api/docs",
            "openapi": "/api/openapi.json"
        }

    return app
