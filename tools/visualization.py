"""Unified visualization tools.

Single chart() function for all visualizations:
- Portfolio dashboard (interactive with toggles)
- Price charts (TradingView embed)
"""

import json
import os
import uuid
from typing import Optional, Literal

import cache
from helpers.chart_templates import (
    generate_tradingview_chart_html,
    generate_portfolio_page_html,
)
from helpers.pricing import get_live_price, get_fx_rate_cached
from helpers.portfolio import load_liabilities
from helpers.classification import get_classification
from helpers.user_context import get_current_user_id
from db import queries


def get_base_url() -> str:
    """Get the base URL for chart links."""
    if os.getenv("FLY_APP_NAME"):
        return f"https://{os.getenv('FLY_APP_NAME')}.fly.dev"
    return f"http://localhost:{os.getenv('PORT', '8080')}"


def _collect_portfolio_data(reporting_currency: Optional[str] = None) -> tuple[list[dict], dict]:
    """
    Collect holdings data from SQLite.

    Returns:
        (holdings_data, fx_cache) - List of holdings and FX cache used
    """
    holdings_data = []
    fx_cache = {}

    try:
        user_id = get_current_user_id()
        accounts = queries.get_accounts_for_user(user_id)

        for account in accounts:
            account_id = account['id']
            account_name = account['name']
            is_manual = account.get('is_manual', False)
            
            # Get holdings for this account
            holdings = queries.get_holdings_for_account(account_id)
            
            for holding in holdings:
                symbol = holding.get('symbol')
                name = holding.get('name')
                units = holding.get('quantity', 0)
                curr = holding.get('currency', 'USD')
                stored_price = holding.get('current_price')
                asset_type = holding.get('asset_type')
                
                # Skip liabilities (they appear in _collect_liabilities_data)
                if asset_type == 'liability':
                    continue
                
                # Get live price
                price = None
                if symbol and symbol != "Cash":
                    live_data = get_live_price(symbol)
                    if live_data.get("price"):
                        price = live_data["price"]
                
                # Fall back to stored price
                if price is None and stored_price is not None:
                    price = stored_price
                
                market_value = (units * price) if units and price else 0
                
                # Convert to reporting currency if specified
                if reporting_currency and curr and curr != reporting_currency and market_value:
                    fx = get_fx_rate_cached(curr, reporting_currency, fx_cache)
                    if fx:
                        market_value = market_value * fx
                
                if market_value > 0:
                    classification = get_classification(symbol, name)
                    
                    # Determine brokerage/source label
                    brokerage_label = "Manual" if is_manual else account_name
                    
                    holdings_data.append({
                        "symbol": symbol,
                        "ticker_label": symbol or name or "Unknown",
                        "name": classification.get("name", name or symbol),
                        "category": classification.get("category", "Other"),
                        "brokerage": brokerage_label,
                        "value": market_value,
                    })
    
    except Exception as e:
        print(f"Error collecting portfolio data: {e}")

    return holdings_data, fx_cache


def _collect_liabilities_data(reporting_currency: Optional[str] = None) -> tuple[list[dict], float]:
    """
    Collect liabilities data for visualization.

    Returns:
        (liabilities_data, total) - List of liabilities for chart and total balance
    """
    liabilities_data = []
    fx_cache = {}

    try:
        liabilities = load_liabilities()

        for liability in liabilities:
            balance = liability.get("balance", 0)
            curr = liability.get("currency", "USD")

            # Convert to reporting currency if specified
            if reporting_currency and curr and curr != reporting_currency and balance:
                fx = get_fx_rate_cached(curr, reporting_currency, fx_cache)
                if fx:
                    balance = balance * fx

            if balance > 0:
                liabilities_data.append({
                    "label": liability.get("name", "Unknown"),
                    "value": balance,
                    "type": liability.get("type", "other"),
                    "interest_rate": liability.get("interest_rate"),
                })
    except Exception:
        pass

    # Sort by balance descending
    liabilities_data.sort(key=lambda l: l.get("value", 0), reverse=True)

    total = sum(l.get("value", 0) for l in liabilities_data)

    return liabilities_data, total


def register_visualization_tools(server):
    """Register unified visualization tools with the server."""

    @server.tool()
    def chart(
        type: Literal["portfolio", "price"],
        tickers: Optional[str] = None,
        interval: str = "D",
        theme: str = "dark",
        currency: Optional[str] = None,
    ) -> str:
        """
        Generate a chart visualization. Returns a URL.

        PORTFOLIO CHARTS (type="portfolio"):
          Interactive dashboard showing all holdings from manual portfolios and brokerages.
          Features pie/treemap toggle and grouping by: ticker, name, category, brokerage.

          Example: chart(type="portfolio")
          Example: chart(type="portfolio", currency="GBP")

        PRICE CHARTS (type="price"):
          TradingView chart for one or more tickers with live market data.
          Requires: tickers parameter.

          Example: chart(type="price", tickers="AAPL")
          Example: chart(type="price", tickers="AAPL,MSFT,GOOG", interval="W")

        Args:
            type: "portfolio" for holdings dashboard, "price" for stock chart
            tickers: Comma-separated ticker symbols (required for price charts)
            interval: Chart interval for price charts - 1/5/15/30/60 (minutes) or D/W/M
            theme: "dark" or "light"
            currency: Reporting currency for portfolio charts (e.g., "USD", "GBP")

        Returns:
            JSON with chart URL and metadata
        """
        if theme not in ["dark", "light"]:
            theme = "dark"

        if not cache.is_cache_available():
            return json.dumps({
                "error": "Chart caching unavailable. Redis not configured.",
                "hint": "Charts require Redis for storage. Set UPSTASH_REDIS_REST_URL and UPSTASH_REDIS_REST_TOKEN."
            })

        if type == "price":
            # Price chart (TradingView)
            if not tickers:
                return json.dumps({
                    "error": "tickers parameter required for price charts",
                    "example": 'chart(type="price", tickers="AAPL")'
                })

            ticker_list = [t.strip().upper() for t in tickers.split(",") if t.strip()]

            if not ticker_list:
                return json.dumps({"error": "No valid tickers provided"})

            if len(ticker_list) > 5:
                return json.dumps({
                    "error": "Too many tickers. Maximum 5 for chart readability.",
                    "provided": len(ticker_list)
                })

            valid_intervals = ["1", "5", "15", "30", "60", "D", "W", "M"]
            if interval not in valid_intervals:
                return json.dumps({
                    "error": f"Invalid interval '{interval}'",
                    "valid_intervals": valid_intervals
                })

            html = generate_tradingview_chart_html(
                tickers=ticker_list,
                interval=interval,
                theme=theme,
                show_details=True,
            )

            chart_id = str(uuid.uuid4())[:8]
            if not cache.cache_chart(chart_id, html):
                return json.dumps({"error": "Failed to cache chart"})

            base_url = get_base_url()
            chart_url = f"{base_url}/charts/{chart_id}"

            return json.dumps({
                "success": True,
                "url": chart_url,
                "type": "price",
                "tickers": ticker_list,
                "interval": interval,
                "theme": theme,
                "expires_in": "24 hours",
            }, indent=2)

        else:
            # Portfolio dashboard
            holdings_data, _ = _collect_portfolio_data(currency)
            liabilities_data, liabilities_total = _collect_liabilities_data(currency)

            if not holdings_data and not liabilities_data:
                return json.dumps({
                    "error": "No holdings or liabilities data found",
                    "hint": "Connect a brokerage with add_portfolio(type='synced'), create manual portfolios with add_portfolio(type='manual'), or add liabilities with add_liability()"
                })

            # Build grouped data for all dimensions
            def group_by_field(data, field):
                grouped = {}
                for item in data:
                    key = item.get(field, "Unknown")
                    grouped[key] = grouped.get(key, 0) + item.get("value", 0)
                return [
                    {"label": label, "value": round(value, 2)}
                    for label, value in sorted(grouped.items(), key=lambda x: x[1], reverse=True)
                ]

            grouped_data = {
                "ticker": group_by_field(holdings_data, "ticker_label"),
                "name": group_by_field(holdings_data, "name"),
                "category": group_by_field(holdings_data, "category"),
                "brokerage": group_by_field(holdings_data, "brokerage"),
            }

            total_value = sum(item.get("value", 0) for item in holdings_data)
            net_worth = total_value - liabilities_total
            display_currency = currency or "USD"

            html = generate_portfolio_page_html(
                holdings=holdings_data,
                grouped_data=grouped_data,
                total_value=total_value,
                currency=display_currency,
                theme=theme,
                liabilities_data=liabilities_data,
                liabilities_total=liabilities_total,
            )

            chart_id = str(uuid.uuid4())[:8]
            if not cache.cache_chart(chart_id, html):
                return json.dumps({"error": "Failed to cache chart"})

            base_url = get_base_url()
            chart_url = f"{base_url}/charts/{chart_id}"

            return json.dumps({
                "success": True,
                "url": chart_url,
                "type": "portfolio",
                "theme": theme,
                "currency": display_currency,
                "total_assets": round(total_value, 2),
                "total_liabilities": round(liabilities_total, 2),
                "net_worth": round(net_worth, 2),
                "holdings_count": len(holdings_data),
                "liabilities_count": len(liabilities_data),
                "groupings": {
                    "ticker": len(grouped_data["ticker"]),
                    "name": len(grouped_data["name"]),
                    "category": len(grouped_data["category"]),
                    "brokerage": len(grouped_data["brokerage"]),
                },
                "expires_in": "24 hours",
            }, indent=2)
