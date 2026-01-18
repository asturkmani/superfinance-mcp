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
from helpers.portfolio import load_portfolios
from helpers.classification import get_classification, get_option_display_label
from tools.snaptrade import get_snaptrade_client


def get_base_url() -> str:
    """Get the base URL for chart links."""
    if os.getenv("FLY_APP_NAME"):
        return f"https://{os.getenv('FLY_APP_NAME')}.fly.dev"
    return f"http://localhost:{os.getenv('PORT', '8080')}"


def _collect_portfolio_data(reporting_currency: Optional[str] = None) -> tuple[list[dict], dict]:
    """
    Collect holdings data from all sources (SnapTrade + manual portfolios).

    Returns:
        (holdings_data, fx_cache) - List of holdings and FX cache used
    """
    holdings_data = []
    fx_cache = {}

    # Get SnapTrade holdings
    snaptrade_client = get_snaptrade_client()
    if snaptrade_client:
        user_id = os.getenv("SNAPTRADE_USER_ID")
        user_secret = os.getenv("SNAPTRADE_USER_SECRET")

        if user_id and user_secret:
            try:
                accounts = snaptrade_client.account_information.list_user_accounts(
                    user_id=user_id, user_secret=user_secret
                )
                accounts = accounts.body if hasattr(accounts, 'body') else accounts

                for account in accounts:
                    if hasattr(account, 'to_dict'):
                        account = account.to_dict()

                    account_id = account.get("id")
                    brokerage_name = account.get("institution_name", "Unknown Brokerage")
                    if not account_id:
                        continue

                    try:
                        holdings = snaptrade_client.account_information.get_user_holdings(
                            account_id=account_id, user_id=user_id, user_secret=user_secret
                        )
                        holdings = holdings.body if hasattr(holdings, 'body') else holdings
                        if hasattr(holdings, 'to_dict'):
                            holdings = holdings.to_dict()

                        # Process stock positions
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
                                classification = get_classification(ticker, desc)
                                holdings_data.append({
                                    "symbol": ticker,
                                    "ticker_label": ticker or desc or "Unknown",
                                    "name": classification.get("name", ticker or desc),
                                    "category": classification.get("category", "Other"),
                                    "brokerage": brokerage_name,
                                    "value": market_value,
                                })

                        # Process options positions
                        for opt in holdings.get("option_positions", []):
                            if hasattr(opt, 'to_dict'):
                                opt = opt.to_dict()

                            sym_wrap = opt.get("symbol", {})
                            if hasattr(sym_wrap, 'to_dict'):
                                sym_wrap = sym_wrap.to_dict()
                            opt_sym = sym_wrap.get("option_symbol", {})
                            if hasattr(opt_sym, 'to_dict'):
                                opt_sym = opt_sym.to_dict()
                            underlying = opt_sym.get("underlying_symbol", {})
                            if hasattr(underlying, 'to_dict'):
                                underlying = underlying.to_dict()
                            curr_obj = underlying.get("currency", {})
                            if hasattr(curr_obj, 'to_dict'):
                                curr_obj = curr_obj.to_dict()
                            curr = curr_obj.get("code") if isinstance(curr_obj, dict) else None

                            units = opt.get("units") or 0
                            price = opt.get("price") or 0
                            multiplier = 100 if not opt_sym.get("is_mini_option") else 10

                            market_value = abs(units * price * multiplier) if price and units else 0

                            # Convert to reporting currency if specified
                            if reporting_currency and curr and curr != reporting_currency and market_value:
                                fx = get_fx_rate_cached(curr, reporting_currency, fx_cache)
                                if fx:
                                    market_value = market_value * fx

                            if market_value > 0:
                                underlying_sym = underlying.get("symbol", "???")
                                underlying_desc = underlying.get("description")
                                classification = get_classification(underlying_sym, underlying_desc)

                                opt_label = get_option_display_label({
                                    "underlying": underlying_sym,
                                    "strike_price": opt_sym.get("strike_price"),
                                    "option_type": opt_sym.get("option_type"),
                                    "expiration_date": opt_sym.get("expiration_date"),
                                })

                                holdings_data.append({
                                    "symbol": opt_sym.get("ticker", opt_label),
                                    "ticker_label": opt_label,
                                    "name": classification.get("name", underlying_sym),
                                    "category": classification.get("category", "Other"),
                                    "brokerage": brokerage_name,
                                    "value": market_value,
                                })

                        # Process cash balances
                        for bal in holdings.get("balances", []):
                            if hasattr(bal, 'to_dict'):
                                bal = bal.to_dict()

                            curr = bal.get("currency", {})
                            if hasattr(curr, 'to_dict'):
                                curr = curr.to_dict()
                            curr_code = curr.get("code") if isinstance(curr, dict) else None

                            cash_val = bal.get("cash") or 0
                            if curr_code and cash_val > 0:
                                if reporting_currency and curr_code != reporting_currency:
                                    fx = get_fx_rate_cached(curr_code, reporting_currency, fx_cache)
                                    if fx:
                                        cash_val = cash_val * fx

                                holdings_data.append({
                                    "symbol": "Cash",
                                    "ticker_label": "Cash",
                                    "name": "Cash",
                                    "category": "Cash",
                                    "brokerage": brokerage_name,
                                    "value": cash_val,
                                })

                    except Exception:
                        continue
            except Exception:
                pass

    # Get manual portfolios
    try:
        portfolios = load_portfolios()

        for pid, portfolio in portfolios.get("portfolios", {}).items():
            portfolio_name = portfolio.get("name", "Private Holdings")

            for pos in portfolio.get("positions", []):
                symbol = pos.get("symbol")
                name = pos.get("name")
                units = pos.get("units", 0)
                curr = pos.get("currency", "USD")
                manual_price = pos.get("manual_price")

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
                    classification = get_classification(symbol, name)
                    holdings_data.append({
                        "symbol": symbol,
                        "ticker_label": symbol or name or "Unknown",
                        "name": classification.get("name", name or symbol),
                        "category": classification.get("category", "Other"),
                        "brokerage": portfolio_name,
                        "value": market_value,
                    })
    except Exception:
        pass

    return holdings_data, fx_cache


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

            if not holdings_data:
                return json.dumps({
                    "error": "No holdings data found",
                    "hint": "Connect a brokerage with add_portfolio(type='synced') or create manual portfolios with add_portfolio(type='manual')"
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
            display_currency = currency or "USD"

            html = generate_portfolio_page_html(
                holdings=holdings_data,
                grouped_data=grouped_data,
                total_value=total_value,
                currency=display_currency,
                theme=theme,
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
                "total_value": round(total_value, 2),
                "holdings_count": len(holdings_data),
                "groupings": {
                    "ticker": len(grouped_data["ticker"]),
                    "name": len(grouped_data["name"]),
                    "category": len(grouped_data["category"]),
                    "brokerage": len(grouped_data["brokerage"]),
                },
                "expires_in": "24 hours",
            }, indent=2)
