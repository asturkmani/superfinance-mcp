"""Chart generation tools for SuperFinance MCP server."""

import json
import os
import uuid
from typing import Optional

import cache
from helpers.chart_templates import generate_tradingview_chart_html, generate_chartjs_pie_html
from helpers.pricing import get_live_price, get_fx_rate_cached
from helpers.portfolio import load_portfolios
from tools.snaptrade import get_snaptrade_client


def get_base_url() -> str:
    """Get the base URL for chart links."""
    if os.getenv("FLY_APP_NAME"):
        return f"https://{os.getenv('FLY_APP_NAME')}.fly.dev"
    return f"http://localhost:{os.getenv('PORT', '8080')}"


def register_chart_tools(server):
    """Register chart tools with the server."""

    @server.tool()
    def stock_chart(
        tickers: str,
        interval: str = "D",
        theme: str = "dark",
        show_details: bool = True,
    ) -> str:
        """
        Generate an interactive stock chart using TradingView.

        Returns a URL to view the chart. Chart expires after 24 hours.
        TradingView fetches live market data automatically.

        Args:
            tickers: Single ticker or comma-separated (e.g., "AAPL" or "AAPL,MSFT,GOOG"). Max ~5 for readability.
            interval: Chart interval - 1, 5, 15, 30, 60 (minutes) or D (daily), W (weekly), M (monthly)
            theme: "dark" or "light"
            show_details: Show volume and side toolbar (default True)

        Returns:
            JSON with chart URL and metadata
        """
        # Parse and validate tickers
        ticker_list = [t.strip().upper() for t in tickers.split(",") if t.strip()]

        if not ticker_list:
            return json.dumps({"error": "No valid tickers provided"})

        if len(ticker_list) > 5:
            return json.dumps({
                "error": "Too many tickers. Maximum 5 for chart readability.",
                "provided": len(ticker_list)
            })

        # Validate interval
        valid_intervals = ["1", "5", "15", "30", "60", "D", "W", "M"]
        if interval not in valid_intervals:
            return json.dumps({
                "error": f"Invalid interval '{interval}'",
                "valid_intervals": valid_intervals
            })

        # Validate theme
        if theme not in ["dark", "light"]:
            theme = "dark"

        # Generate chart HTML
        html = generate_tradingview_chart_html(
            tickers=ticker_list,
            interval=interval,
            theme=theme,
            show_details=show_details,
        )

        # Generate unique chart ID and cache
        chart_id = str(uuid.uuid4())[:8]

        if not cache.is_cache_available():
            return json.dumps({
                "error": "Chart caching unavailable. Redis not configured.",
                "hint": "Charts require Redis for storage. Set UPSTASH_REDIS_REST_URL and UPSTASH_REDIS_REST_TOKEN."
            })

        if not cache.cache_chart(chart_id, html):
            return json.dumps({"error": "Failed to cache chart"})

        base_url = get_base_url()
        chart_url = f"{base_url}/charts/{chart_id}"

        return json.dumps({
            "success": True,
            "url": chart_url,
            "tickers": ticker_list,
            "interval": interval,
            "theme": theme,
            "expires_in": "24 hours",
            "note": "Chart uses TradingView widget which fetches live data automatically"
        }, indent=2)

    @server.tool()
    def portfolio_composition_chart(
        source: str = "all",
        portfolio_id: Optional[str] = None,
        group_by: str = "holding",
        chart_type: str = "donut",
        theme: str = "dark",
        reporting_currency: Optional[str] = None,
    ) -> str:
        """
        Generate a portfolio composition chart showing holdings breakdown.

        Returns a URL to view the chart. Chart expires after 24 hours.
        Data is fetched from your connected brokerage accounts and/or manual portfolios.

        Args:
            source: "snaptrade" (brokerage only), "manual" (manual portfolios only), or "all" (both)
            portfolio_id: Specific manual portfolio ID (optional, only used when source includes "manual")
            group_by: How to group data - "holding" (by ticker/name), "sector", or "asset_type"
            chart_type: "pie" or "donut"
            theme: "dark" or "light"
            reporting_currency: Currency for value conversion (e.g., "USD", "GBP"). Uses native currencies if not specified.

        Returns:
            JSON with chart URL and metadata
        """
        # Validate inputs
        if source not in ["snaptrade", "manual", "all"]:
            return json.dumps({
                "error": f"Invalid source '{source}'",
                "valid_sources": ["snaptrade", "manual", "all"]
            })

        if group_by not in ["holding", "sector", "asset_type"]:
            return json.dumps({
                "error": f"Invalid group_by '{group_by}'",
                "valid_options": ["holding", "sector", "asset_type"]
            })

        if chart_type not in ["pie", "donut"]:
            chart_type = "donut"

        if theme not in ["dark", "light"]:
            theme = "dark"

        # Collect holdings data
        holdings_data = []
        fx_cache = {}

        try:
            # Get SnapTrade holdings if requested
            if source in ["snaptrade", "all"]:
                snaptrade_client = get_snaptrade_client()
                if snaptrade_client:
                    user_id = os.getenv("SNAPTRADE_USER_ID")
                    user_secret = os.getenv("SNAPTRADE_USER_SECRET")

                    if user_id and user_secret:
                        accounts = snaptrade_client.account_information.list_user_accounts(
                            user_id=user_id, user_secret=user_secret
                        )
                        accounts = accounts.body if hasattr(accounts, 'body') else accounts

                        for account in accounts:
                            if hasattr(account, 'to_dict'):
                                account = account.to_dict()

                            account_id = account.get("id")
                            if not account_id:
                                continue

                            try:
                                holdings = snaptrade_client.account_information.get_user_holdings(
                                    account_id=account_id, user_id=user_id, user_secret=user_secret
                                )
                                holdings = holdings.body if hasattr(holdings, 'body') else holdings
                                if hasattr(holdings, 'to_dict'):
                                    holdings = holdings.to_dict()

                                for pos in holdings.get("positions", []):
                                    if hasattr(pos, 'to_dict'):
                                        pos = pos.to_dict()

                                    sym_data = pos.get("symbol", {})
                                    if hasattr(sym_data, 'to_dict'):
                                        sym_data = sym_data.to_dict()

                                    # Handle nested symbol
                                    if "symbol" in sym_data and isinstance(sym_data["symbol"], dict):
                                        inner = sym_data["symbol"]
                                        ticker = inner.get("symbol")
                                        desc = inner.get("description")
                                        curr = inner.get("currency", {}).get("code") if isinstance(inner.get("currency"), dict) else None
                                    else:
                                        ticker = sym_data.get("symbol")
                                        desc = sym_data.get("description")
                                        curr = sym_data.get("currency", {}).get("code") if isinstance(sym_data.get("currency"), dict) else None

                                    units = pos.get("units") or 0
                                    price = pos.get("price")

                                    # Get live price
                                    if ticker:
                                        live_data = get_live_price(ticker)
                                        if live_data.get("price"):
                                            price = live_data["price"]

                                    market_value = (units * price) if price and units else 0

                                    # Convert to reporting currency if specified
                                    if reporting_currency and curr and curr != reporting_currency and market_value:
                                        fx = get_fx_rate_cached(curr, reporting_currency, fx_cache)
                                        if fx:
                                            market_value = market_value * fx

                                    if market_value > 0:
                                        holdings_data.append({
                                            "label": ticker or desc or "Unknown",
                                            "value": market_value,
                                            "source": "snaptrade",
                                            "asset_type": "stock",
                                            "sector": None,  # Would need additional API call to get sector
                                        })

                            except Exception:
                                continue

            # Get manual portfolios if requested
            if source in ["manual", "all"]:
                portfolios = load_portfolios()

                for pid, portfolio in portfolios.get("portfolios", {}).items():
                    # Filter by portfolio_id if specified
                    if portfolio_id and pid != portfolio_id:
                        continue

                    for pos in portfolio.get("positions", []):
                        symbol = pos.get("symbol")
                        name = pos.get("name")
                        units = pos.get("units", 0)
                        curr = pos.get("currency", "USD")
                        manual_price = pos.get("manual_price")
                        asset_type = pos.get("asset_type", "other")

                        # Get live price
                        price = None
                        if symbol:
                            live_data = get_live_price(symbol)
                            if live_data.get("price"):
                                price = live_data["price"]

                        if price is None and manual_price:
                            price = manual_price

                        market_value = (units * price) if units and price else 0

                        # Convert to reporting currency if specified
                        if reporting_currency and curr and curr != reporting_currency and market_value:
                            fx = get_fx_rate_cached(curr, reporting_currency, fx_cache)
                            if fx:
                                market_value = market_value * fx

                        if market_value > 0:
                            holdings_data.append({
                                "label": symbol or name or "Unknown",
                                "value": market_value,
                                "source": "manual",
                                "asset_type": asset_type,
                                "sector": None,
                            })

        except Exception as e:
            return json.dumps({"error": f"Failed to fetch holdings: {str(e)}"})

        if not holdings_data:
            return json.dumps({
                "error": "No holdings data found",
                "hint": "Make sure you have connected brokerage accounts or created manual portfolios"
            })

        # Group data based on group_by parameter
        grouped = {}
        if group_by == "holding":
            # Group by ticker/name (combine duplicate tickers)
            for item in holdings_data:
                label = item["label"]
                if label in grouped:
                    grouped[label] += item["value"]
                else:
                    grouped[label] = item["value"]
        elif group_by == "asset_type":
            for item in holdings_data:
                asset_type = item.get("asset_type") or "other"
                if asset_type in grouped:
                    grouped[asset_type] += item["value"]
                else:
                    grouped[asset_type] = item["value"]
        elif group_by == "sector":
            # Group by sector (if available, otherwise use "Unknown")
            for item in holdings_data:
                sector = item.get("sector") or "Unknown"
                if sector in grouped:
                    grouped[sector] += item["value"]
                else:
                    grouped[sector] = item["value"]

        # Convert to chart data format and sort by value descending
        chart_data = [
            {"label": label, "value": round(value, 2)}
            for label, value in sorted(grouped.items(), key=lambda x: x[1], reverse=True)
        ]

        # Generate title
        currency_suffix = f" ({reporting_currency})" if reporting_currency else ""
        if group_by == "holding":
            title = f"Portfolio Holdings{currency_suffix}"
        elif group_by == "asset_type":
            title = f"Portfolio by Asset Type{currency_suffix}"
        else:
            title = f"Portfolio by Sector{currency_suffix}"

        # Generate chart HTML
        html = generate_chartjs_pie_html(
            data=chart_data,
            title=title,
            chart_type="doughnut" if chart_type == "donut" else "pie",
            theme=theme,
        )

        # Generate unique chart ID and cache
        chart_id = str(uuid.uuid4())[:8]

        if not cache.is_cache_available():
            return json.dumps({
                "error": "Chart caching unavailable. Redis not configured.",
                "hint": "Charts require Redis for storage. Set UPSTASH_REDIS_REST_URL and UPSTASH_REDIS_REST_TOKEN."
            })

        if not cache.cache_chart(chart_id, html):
            return json.dumps({"error": "Failed to cache chart"})

        base_url = get_base_url()
        chart_url = f"{base_url}/charts/{chart_id}"

        # Calculate total value
        total_value = sum(item["value"] for item in chart_data)

        return json.dumps({
            "success": True,
            "url": chart_url,
            "source": source,
            "group_by": group_by,
            "chart_type": chart_type,
            "theme": theme,
            "reporting_currency": reporting_currency,
            "total_value": round(total_value, 2),
            "holdings_count": len(chart_data),
            "expires_in": "24 hours",
        }, indent=2)
