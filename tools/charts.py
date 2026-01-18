"""Chart generation tools for SuperFinance MCP server."""

import json
import os
import uuid
from typing import Optional

import cache
from helpers.chart_templates import (
    generate_tradingview_chart_html,
    generate_chartjs_pie_html,
    generate_treemap_html,
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
        include: str = "all",
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
            include: What to include - "all", "stocks", "options", "private", or comma-separated combo (e.g., "stocks,options")
            group_by: How to group data - "holding" (by ticker/name), "type" (stocks/options/private), or "asset_type"
            chart_type: "pie", "donut", or "treemap" (heatmap-style)
            theme: "dark" or "light"
            reporting_currency: Currency for value conversion (e.g., "USD", "GBP"). Uses native currencies if not specified.

        Returns:
            JSON with chart URL and metadata
        """
        # Parse include filter
        valid_types = {"all", "stocks", "options", "private"}
        include_types = set()
        for t in include.lower().split(","):
            t = t.strip()
            if t in valid_types:
                include_types.add(t)

        if not include_types:
            include_types = {"all"}

        if "all" in include_types:
            include_types = {"stocks", "options", "private"}

        if group_by not in ["holding", "type", "asset_type"]:
            return json.dumps({
                "error": f"Invalid group_by '{group_by}'",
                "valid_options": ["holding", "type", "asset_type"]
            })

        if chart_type not in ["pie", "donut", "treemap"]:
            chart_type = "donut"

        if theme not in ["dark", "light"]:
            theme = "dark"

        # Collect holdings data
        holdings_data = []
        fx_cache = {}

        try:
            # Get SnapTrade holdings
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

                            # Process stock positions
                            if "stocks" in include_types:
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
                                            "type": "Stocks",
                                            "asset_type": "stock",
                                        })

                            # Process options positions
                            if "options" in include_types:
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
                                        opt_type = opt_sym.get("option_type", "").upper()
                                        underlying_sym = underlying.get("symbol", "???")
                                        strike = opt_sym.get("strike_price", "")
                                        label = f"{underlying_sym} {strike}{opt_type[0] if opt_type else ''}"

                                        holdings_data.append({
                                            "label": label,
                                            "value": market_value,
                                            "type": "Options",
                                            "asset_type": "option",
                                        })

                        except Exception:
                            continue

            # Get manual portfolios (private investments)
            if "private" in include_types:
                portfolios = load_portfolios()

                for pid, portfolio in portfolios.get("portfolios", {}).items():
                    for pos in portfolio.get("positions", []):
                        symbol = pos.get("symbol")
                        name = pos.get("name")
                        units = pos.get("units", 0)
                        curr = pos.get("currency", "USD")
                        manual_price = pos.get("manual_price")
                        asset_type = pos.get("asset_type", "private")

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
                                "type": "Private",
                                "asset_type": asset_type,
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
            for item in holdings_data:
                label = item["label"]
                grouped[label] = grouped.get(label, 0) + item["value"]
        elif group_by == "type":
            for item in holdings_data:
                pos_type = item.get("type", "Other")
                grouped[pos_type] = grouped.get(pos_type, 0) + item["value"]
        elif group_by == "asset_type":
            for item in holdings_data:
                asset_type = item.get("asset_type", "other")
                grouped[asset_type] = grouped.get(asset_type, 0) + item["value"]

        # Convert to chart data format and sort by value descending
        chart_data = [
            {"label": label, "value": round(value, 2)}
            for label, value in sorted(grouped.items(), key=lambda x: x[1], reverse=True)
        ]

        # Generate title
        currency_suffix = f" ({reporting_currency})" if reporting_currency else ""
        include_str = ", ".join(sorted(include_types))
        if group_by == "holding":
            title = f"Portfolio Holdings{currency_suffix}"
        elif group_by == "type":
            title = f"Portfolio by Type{currency_suffix}"
        else:
            title = f"Portfolio by Asset Type{currency_suffix}"

        # Generate chart HTML
        if chart_type == "treemap":
            html = generate_treemap_html(
                data=chart_data,
                title=title,
                theme=theme,
            )
        else:
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
            "include": list(include_types),
            "group_by": group_by,
            "chart_type": chart_type,
            "theme": theme,
            "reporting_currency": reporting_currency,
            "total_value": round(total_value, 2),
            "holdings_count": len(chart_data),
            "expires_in": "24 hours",
        }, indent=2)

    @server.tool()
    def portfolio_page(
        theme: str = "dark",
        reporting_currency: Optional[str] = None,
    ) -> str:
        """
        Generate an interactive portfolio dashboard page.

        Features:
        - Toggle between pie chart and treemap (heatmap) views
        - Group by: ticker, consolidated name, category, or brokerage
        - AI-powered category classification (Technology, Memory, Commodities, etc.)
        - Live prices from Yahoo Finance
        - Currency conversion support

        Returns a URL to the interactive dashboard. Expires after 24 hours.

        Args:
            theme: "dark" or "light"
            reporting_currency: Currency code (e.g., "USD", "GBP") for value conversion.
                              Uses native currencies if not specified.

        Returns:
            JSON with chart URL and metadata
        """
        if theme not in ["dark", "light"]:
            theme = "dark"

        # Collect all holdings data
        holdings_data = []
        fx_cache = {}

        try:
            # Get SnapTrade holdings
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
                                    # Get classification
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

                                    # Get classification based on underlying
                                    classification = get_classification(underlying_sym, underlying_desc)

                                    # Build option display label
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
                                    # Convert to reporting currency if specified
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

            # Get manual portfolios
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
                        # Get classification
                        classification = get_classification(symbol, name)

                        holdings_data.append({
                            "symbol": symbol,
                            "ticker_label": symbol or name or "Unknown",
                            "name": classification.get("name", name or symbol),
                            "category": classification.get("category", "Other"),
                            "brokerage": portfolio_name,
                            "value": market_value,
                        })

        except Exception as e:
            return json.dumps({"error": f"Failed to fetch holdings: {str(e)}"})

        if not holdings_data:
            return json.dumps({
                "error": "No holdings data found",
                "hint": "Make sure you have connected brokerage accounts or created manual portfolios"
            })

        # Build grouped data for all dimensions
        def group_by_field(data, field):
            grouped = {}
            for item in data:
                key = item.get(field, "Unknown")
                grouped[key] = grouped.get(key, 0) + item.get("value", 0)
            # Sort by value descending and convert to list format
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
        currency = reporting_currency or "USD"

        # Generate HTML
        html = generate_portfolio_page_html(
            holdings=holdings_data,
            grouped_data=grouped_data,
            total_value=total_value,
            currency=currency,
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

        return json.dumps({
            "success": True,
            "url": chart_url,
            "theme": theme,
            "reporting_currency": reporting_currency,
            "total_value": round(total_value, 2),
            "currency": currency,
            "holdings_count": len(holdings_data),
            "groupings": {
                "ticker": len(grouped_data["ticker"]),
                "name": len(grouped_data["name"]),
                "category": len(grouped_data["category"]),
                "brokerage": len(grouped_data["brokerage"]),
            },
            "expires_in": "24 hours",
        }, indent=2)
