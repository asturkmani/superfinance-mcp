"""Unified holdings tool combining SnapTrade and manual portfolios."""

import json
import os
from typing import Optional

from helpers.pricing import get_live_price, get_fx_rate_cached
from helpers.portfolio import load_portfolios
from helpers.classification import get_classification, get_option_display_label
from tools.snaptrade import get_snaptrade_client


def register_holdings_tools(server):
    """Register holdings tools with the server."""

    @server.tool()
    def list_all_holdings(
        user_id: Optional[str] = None,
        user_secret: Optional[str] = None,
        reporting_currency: Optional[str] = None
    ) -> str:
        """
        Get all holdings from SnapTrade brokerage accounts and manual portfolios.

        Returns positions in their native instrument currency with totals summed per currency.
        If reporting_currency is specified, adds converted totals for unified view.

        Args:
            user_id: SnapTrade user ID (uses env var if not provided)
            user_secret: SnapTrade user secret (uses env var if not provided)
            reporting_currency: Optional currency code (e.g., "GBP") to convert all values

        Returns:
            JSON with:
            - totals: holdings, cash, value, cost_basis, unrealized_pnl (by currency)
            - accounts: list of accounts with their totals and positions
        """
        try:
            fx_cache = {}
            fx_rates_used = {}

            all_accounts = []

            # Grand totals by currency
            grand_holdings = {}
            grand_cash = {}
            grand_cost_basis = {}

            # Step 1: Get SnapTrade accounts
            accounts = []
            snaptrade_client = get_snaptrade_client()
            if snaptrade_client:
                user_id = user_id or os.getenv("SNAPTRADE_USER_ID")
                user_secret = user_secret or os.getenv("SNAPTRADE_USER_SECRET")
                if user_id and user_secret:
                    resp = snaptrade_client.account_information.list_user_accounts(
                        user_id=user_id, user_secret=user_secret
                    )
                    accounts = resp.body if hasattr(resp, 'body') else resp

            # Step 2: Process each SnapTrade account
            for account in accounts:
                if hasattr(account, 'to_dict'):
                    account = account.to_dict()

                account_id = account.get("id")
                if not account_id:
                    continue

                try:
                    resp = snaptrade_client.account_information.get_user_holdings(
                        account_id=account_id, user_id=user_id, user_secret=user_secret
                    )
                    holdings = resp.body if hasattr(resp, 'body') else resp
                    if hasattr(holdings, 'to_dict'):
                        holdings = holdings.to_dict()

                    # Get brokerage-reported value
                    bal = account.get("balance", {})
                    bal_total = bal.get("total", {}) if isinstance(bal, dict) else {}
                    brokerage_value = bal_total.get("amount")
                    brokerage_currency = bal_total.get("currency")

                    # Extract cash from balances
                    account_cash = {}
                    for b in holdings.get("balances", []):
                        if hasattr(b, 'to_dict'):
                            b = b.to_dict()
                        curr_obj = b.get("currency", {})
                        if hasattr(curr_obj, 'to_dict'):
                            curr_obj = curr_obj.to_dict()
                        curr = curr_obj.get("code") if isinstance(curr_obj, dict) else None
                        cash_val = b.get("cash") or 0
                        if curr and cash_val:
                            account_cash[curr] = account_cash.get(curr, 0) + cash_val
                            grand_cash[curr] = grand_cash.get(curr, 0) + cash_val

                    # Account totals
                    account_holdings = {}
                    account_cost_basis = {}

                    # Process positions
                    positions = []
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
                        snap_price = pos.get("price")
                        avg_cost = pos.get("average_purchase_price")

                        # Get live price
                        live_data = get_live_price(ticker) if ticker else {}
                        live_price = live_data.get("price")
                        price_source = live_data.get("source", "unknown")

                        price = live_price if live_price is not None else snap_price
                        market_value = (units * price) if price and units else None
                        cost_basis = (units * avg_cost) if avg_cost and units else None

                        pnl = None
                        pnl_pct = None
                        if market_value and cost_basis and cost_basis > 0:
                            pnl = market_value - cost_basis
                            pnl_pct = round((pnl / cost_basis) * 100, 2)

                        # Get classification (name + category)
                        classification = get_classification(ticker, desc)

                        pos_data = {
                            "symbol": ticker,
                            "description": desc,
                            "consolidated_name": classification.get("name", ticker or desc),
                            "category": classification.get("category", "Other"),
                            "units": round(units, 6) if units else 0,
                            "currency": curr,
                            "price": round(price, 4) if price else None,
                            "price_source": price_source,
                            "market_value": round(market_value, 2) if market_value else None,
                            "average_cost": round(avg_cost, 4) if avg_cost else None,
                            "cost_basis": round(cost_basis, 2) if cost_basis else None,
                            "unrealized_pnl": round(pnl, 2) if pnl else None,
                            "unrealized_pnl_pct": pnl_pct
                        }

                        # Track by currency
                        if curr and market_value:
                            account_holdings[curr] = account_holdings.get(curr, 0) + market_value
                            grand_holdings[curr] = grand_holdings.get(curr, 0) + market_value
                        if curr and cost_basis:
                            account_cost_basis[curr] = account_cost_basis.get(curr, 0) + cost_basis
                            grand_cost_basis[curr] = grand_cost_basis.get(curr, 0) + cost_basis

                        # Add converted if reporting_currency
                        if reporting_currency and curr and curr != reporting_currency and market_value:
                            fx = get_fx_rate_cached(curr, reporting_currency, fx_cache)
                            if fx:
                                fx_rates_used[f"{curr}_{reporting_currency}"] = fx
                                pos_data["converted"] = {
                                    "currency": reporting_currency,
                                    "market_value": round(market_value * fx, 2),
                                    "cost_basis": round(cost_basis * fx, 2) if cost_basis else None,
                                    "unrealized_pnl": round(pnl * fx, 2) if pnl else None
                                }

                        positions.append(pos_data)

                    # Process options
                    options = []
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
                        snap_price = opt.get("price")
                        avg_cost = opt.get("average_purchase_price")
                        multiplier = 100 if not opt_sym.get("is_mini_option") else 10

                        market_value = (units * snap_price * multiplier) if snap_price and units else None
                        cost_basis = (units * avg_cost) if avg_cost and units else None

                        pnl = None
                        pnl_pct = None
                        if market_value and cost_basis and cost_basis != 0:
                            pnl = market_value - cost_basis
                            pnl_pct = round((pnl / abs(cost_basis)) * 100, 2)

                        # Get classification based on underlying symbol
                        underlying_sym = underlying.get("symbol")
                        underlying_desc = underlying.get("description")
                        classification = get_classification(underlying_sym, underlying_desc)

                        opt_data = {
                            "type": "option",
                            "ticker": opt_sym.get("ticker"),
                            "underlying": underlying_sym,
                            "consolidated_name": classification.get("name", underlying_sym),
                            "category": classification.get("category", "Other"),
                            "option_type": opt_sym.get("option_type"),
                            "strike_price": opt_sym.get("strike_price"),
                            "expiration_date": opt_sym.get("expiration_date"),
                            "units": units,
                            "multiplier": multiplier,
                            "currency": curr,
                            "price": snap_price,
                            "market_value": round(market_value, 2) if market_value else None,
                            "average_cost": avg_cost,
                            "cost_basis": round(cost_basis, 2) if cost_basis else None,
                            "unrealized_pnl": round(pnl, 2) if pnl else None,
                            "unrealized_pnl_pct": pnl_pct
                        }

                        # Track by currency
                        if curr and market_value:
                            account_holdings[curr] = account_holdings.get(curr, 0) + market_value
                            grand_holdings[curr] = grand_holdings.get(curr, 0) + market_value
                        if curr and cost_basis:
                            account_cost_basis[curr] = account_cost_basis.get(curr, 0) + cost_basis
                            grand_cost_basis[curr] = grand_cost_basis.get(curr, 0) + cost_basis

                        # Add converted if reporting_currency
                        if reporting_currency and curr and curr != reporting_currency and market_value:
                            fx = get_fx_rate_cached(curr, reporting_currency, fx_cache)
                            if fx:
                                fx_rates_used[f"{curr}_{reporting_currency}"] = fx
                                opt_data["converted"] = {
                                    "currency": reporting_currency,
                                    "market_value": round(market_value * fx, 2),
                                    "cost_basis": round(cost_basis * fx, 2) if cost_basis else None,
                                    "unrealized_pnl": round(pnl * fx, 2) if pnl else None
                                }

                        options.append(opt_data)

                    # Calculate account value (holdings + cash)
                    account_value = {}
                    for c, v in account_holdings.items():
                        account_value[c] = account_value.get(c, 0) + v
                    for c, v in account_cash.items():
                        account_value[c] = account_value.get(c, 0) + v

                    # Calculate unrealized P&L
                    account_pnl = {}
                    for c in account_holdings:
                        h = account_holdings.get(c, 0)
                        cb = account_cost_basis.get(c, 0)
                        if cb > 0:
                            account_pnl[c] = h - cb

                    # Build account totals
                    account_totals = {
                        "holdings": {k: round(v, 2) for k, v in account_holdings.items()},
                        "cash": {k: round(v, 2) for k, v in account_cash.items()},
                        "value": {k: round(v, 2) for k, v in account_value.items()},
                        "cost_basis": {k: round(v, 2) for k, v in account_cost_basis.items()},
                        "unrealized_pnl": {k: round(v, 2) for k, v in account_pnl.items()}
                    }

                    # Add converted totals if reporting_currency
                    if reporting_currency:
                        conv = {"currency": reporting_currency, "holdings": 0, "cash": 0, "value": 0, "cost_basis": 0, "unrealized_pnl": 0}
                        for c, v in account_holdings.items():
                            if c == reporting_currency:
                                conv["holdings"] += v
                            else:
                                fx = get_fx_rate_cached(c, reporting_currency, fx_cache)
                                if fx:
                                    fx_rates_used[f"{c}_{reporting_currency}"] = fx
                                    conv["holdings"] += v * fx
                        for c, v in account_cash.items():
                            if c == reporting_currency:
                                conv["cash"] += v
                            else:
                                fx = get_fx_rate_cached(c, reporting_currency, fx_cache)
                                if fx:
                                    fx_rates_used[f"{c}_{reporting_currency}"] = fx
                                    conv["cash"] += v * fx
                        for c, v in account_cost_basis.items():
                            if c == reporting_currency:
                                conv["cost_basis"] += v
                            else:
                                fx = fx_rates_used.get(f"{c}_{reporting_currency}")
                                if fx:
                                    conv["cost_basis"] += v * fx
                        conv["value"] = conv["holdings"] + conv["cash"]
                        conv["unrealized_pnl"] = conv["holdings"] - conv["cost_basis"]
                        account_totals["converted"] = {k: round(v, 2) if isinstance(v, float) else v for k, v in conv.items()}

                    # Build notes for margin and discrepancies
                    notes = []

                    # Check for margin (negative cash)
                    for curr, cash_val in account_cash.items():
                        if cash_val < 0:
                            notes.append({
                                "type": "margin",
                                "message": f"Margin in use: {cash_val:,.2f} {curr}"
                            })

                    # Check for discrepancy between our value and brokerage value
                    if brokerage_value and brokerage_currency:
                        compare_currency = reporting_currency or brokerage_currency

                        if reporting_currency:
                            our_value = account_totals.get("converted", {}).get("value", 0)
                        else:
                            # Sum our value in brokerage currency
                            our_value = 0
                            for c, v in account_value.items():
                                if c == brokerage_currency:
                                    our_value += v
                                else:
                                    fx = get_fx_rate_cached(c, brokerage_currency, fx_cache)
                                    if fx:
                                        our_value += v * fx

                        # Convert brokerage value to compare currency if needed
                        if brokerage_currency == compare_currency:
                            brokerage_in_compare = brokerage_value
                        else:
                            fx = get_fx_rate_cached(brokerage_currency, compare_currency, fx_cache)
                            brokerage_in_compare = brokerage_value * fx if fx else None

                        if brokerage_in_compare and our_value:
                            diff = our_value - brokerage_in_compare
                            diff_pct = (diff / brokerage_in_compare) * 100 if brokerage_in_compare else 0
                            if abs(diff_pct) > 2:  # More than 2% discrepancy
                                notes.append({
                                    "type": "discrepancy",
                                    "message": f"Value differs from brokerage by {diff_pct:+.1f}% ({diff:+,.2f} {compare_currency})",
                                    "our_value": round(our_value, 2),
                                    "brokerage_value": round(brokerage_in_compare, 2),
                                    "possible_cause": "Missing positions, stale prices, or sync issues"
                                })

                    all_accounts.append({
                        "source": "snaptrade",
                        "account_id": account_id,
                        "name": account.get("name"),
                        "institution": account.get("institution_name"),
                        "account_type": account.get("raw_type"),
                        "brokerage_value": {"amount": round(brokerage_value, 2) if brokerage_value else None, "currency": brokerage_currency},
                        "totals": account_totals,
                        "notes": notes if notes else None,
                        "positions": positions,
                        "options": options
                    })

                except Exception as e:
                    all_accounts.append({
                        "source": "snaptrade",
                        "account_id": account_id,
                        "name": account.get("name"),
                        "error": str(e)
                    })

            snaptrade_count = len(all_accounts)

            # Step 3: Manual portfolios
            manual_count = 0
            try:
                portfolios = load_portfolios()
                for pid, portfolio in portfolios.get("portfolios", {}).items():
                    manual_count += 1

                    port_holdings = {}
                    port_cost_basis = {}
                    positions = []

                    for pos in portfolio.get("positions", []):
                        symbol = pos.get("symbol")
                        units = pos.get("units", 0)
                        avg_cost = pos.get("average_cost", 0)
                        curr = pos.get("currency", "USD")
                        manual_price = pos.get("manual_price")

                        live_price = None
                        price_source = "none"
                        if symbol:
                            live_data = get_live_price(symbol)
                            if live_data.get("price"):
                                live_price = live_data["price"]
                                price_source = "yahoo_finance"
                        if live_price is None and manual_price:
                            live_price = manual_price
                            price_source = "manual"

                        market_value = units * live_price if units and live_price else None
                        cost_basis = units * avg_cost if units and avg_cost else 0

                        pnl = None
                        pnl_pct = None
                        if market_value and cost_basis > 0:
                            pnl = market_value - cost_basis
                            pnl_pct = round((pnl / cost_basis) * 100, 2)

                        # Get classification (name + category)
                        pos_name = pos.get("name")
                        classification = get_classification(symbol, pos_name)

                        pos_data = {
                            "id": pos.get("id"),
                            "name": pos_name,
                            "symbol": symbol,
                            "consolidated_name": classification.get("name", pos_name or symbol),
                            "category": classification.get("category", "Other"),
                            "units": units,
                            "currency": curr,
                            "price": round(live_price, 2) if live_price else None,
                            "price_source": price_source,
                            "market_value": round(market_value, 2) if market_value else None,
                            "average_cost": avg_cost,
                            "cost_basis": round(cost_basis, 2) if cost_basis else None,
                            "unrealized_pnl": round(pnl, 2) if pnl else None,
                            "unrealized_pnl_pct": pnl_pct,
                            "asset_type": pos.get("asset_type"),
                            "notes": pos.get("notes")
                        }

                        if curr and market_value:
                            port_holdings[curr] = port_holdings.get(curr, 0) + market_value
                            grand_holdings[curr] = grand_holdings.get(curr, 0) + market_value
                        if curr and cost_basis:
                            port_cost_basis[curr] = port_cost_basis.get(curr, 0) + cost_basis
                            grand_cost_basis[curr] = grand_cost_basis.get(curr, 0) + cost_basis

                        if reporting_currency and curr and curr != reporting_currency and market_value:
                            fx = get_fx_rate_cached(curr, reporting_currency, fx_cache)
                            if fx:
                                fx_rates_used[f"{curr}_{reporting_currency}"] = fx
                                pos_data["converted"] = {
                                    "currency": reporting_currency,
                                    "market_value": round(market_value * fx, 2),
                                    "cost_basis": round(cost_basis * fx, 2) if cost_basis else None,
                                    "unrealized_pnl": round(pnl * fx, 2) if pnl else None
                                }

                        positions.append(pos_data)

                    # Manual portfolios have no cash
                    port_value = dict(port_holdings)
                    port_pnl = {}
                    for c in port_holdings:
                        h = port_holdings.get(c, 0)
                        cb = port_cost_basis.get(c, 0)
                        if cb > 0:
                            port_pnl[c] = h - cb

                    port_totals = {
                        "holdings": {k: round(v, 2) for k, v in port_holdings.items()},
                        "cash": {},
                        "value": {k: round(v, 2) for k, v in port_value.items()},
                        "cost_basis": {k: round(v, 2) for k, v in port_cost_basis.items()},
                        "unrealized_pnl": {k: round(v, 2) for k, v in port_pnl.items()}
                    }

                    if reporting_currency:
                        conv = {"currency": reporting_currency, "holdings": 0, "cash": 0, "value": 0, "cost_basis": 0, "unrealized_pnl": 0}
                        for c, v in port_holdings.items():
                            if c == reporting_currency:
                                conv["holdings"] += v
                            else:
                                fx = get_fx_rate_cached(c, reporting_currency, fx_cache)
                                if fx:
                                    conv["holdings"] += v * fx
                        for c, v in port_cost_basis.items():
                            if c == reporting_currency:
                                conv["cost_basis"] += v
                            else:
                                fx = fx_rates_used.get(f"{c}_{reporting_currency}")
                                if fx:
                                    conv["cost_basis"] += v * fx
                        conv["value"] = conv["holdings"]
                        conv["unrealized_pnl"] = conv["holdings"] - conv["cost_basis"]
                        port_totals["converted"] = {k: round(v, 2) if isinstance(v, float) else v for k, v in conv.items()}

                    all_accounts.append({
                        "source": "manual",
                        "portfolio_id": pid,
                        "name": portfolio.get("name"),
                        "description": portfolio.get("description"),
                        "totals": port_totals,
                        "positions": positions
                    })
            except Exception:
                pass

            # Build grand totals
            grand_value = {}
            for c, v in grand_holdings.items():
                grand_value[c] = grand_value.get(c, 0) + v
            for c, v in grand_cash.items():
                grand_value[c] = grand_value.get(c, 0) + v

            grand_pnl = {}
            for c in grand_holdings:
                h = grand_holdings.get(c, 0)
                cb = grand_cost_basis.get(c, 0)
                if cb > 0:
                    grand_pnl[c] = h - cb

            totals = {
                "holdings": {k: round(v, 2) for k, v in grand_holdings.items()},
                "cash": {k: round(v, 2) for k, v in grand_cash.items()},
                "value": {k: round(v, 2) for k, v in grand_value.items()},
                "cost_basis": {k: round(v, 2) for k, v in grand_cost_basis.items()},
                "unrealized_pnl": {k: round(v, 2) for k, v in grand_pnl.items()}
            }

            if reporting_currency:
                conv = {"currency": reporting_currency, "holdings": 0, "cash": 0, "value": 0, "cost_basis": 0, "unrealized_pnl": 0}
                for c, v in grand_holdings.items():
                    if c == reporting_currency:
                        conv["holdings"] += v
                    else:
                        fx = get_fx_rate_cached(c, reporting_currency, fx_cache)
                        if fx:
                            fx_rates_used[f"{c}_{reporting_currency}"] = fx
                            conv["holdings"] += v * fx
                for c, v in grand_cash.items():
                    if c == reporting_currency:
                        conv["cash"] += v
                    else:
                        fx = get_fx_rate_cached(c, reporting_currency, fx_cache)
                        if fx:
                            fx_rates_used[f"{c}_{reporting_currency}"] = fx
                            conv["cash"] += v * fx
                for c, v in grand_cost_basis.items():
                    if c == reporting_currency:
                        conv["cost_basis"] += v
                    else:
                        fx = fx_rates_used.get(f"{c}_{reporting_currency}")
                        if fx:
                            conv["cost_basis"] += v * fx
                conv["value"] = conv["holdings"] + conv["cash"]
                conv["unrealized_pnl"] = conv["holdings"] - conv["cost_basis"]
                totals["converted"] = {k: round(v, 2) if isinstance(v, float) else v for k, v in conv.items()}

            result = {
                "success": True,
                "accounts_count": len(all_accounts),
                "snaptrade_accounts": snaptrade_count,
                "manual_portfolios": manual_count,
                "totals": totals,
                "accounts": all_accounts
            }

            if reporting_currency:
                result["reporting_currency"] = reporting_currency
                result["fx_rates"] = {k: round(v, 6) for k, v in fx_rates_used.items()}

            return json.dumps(result, indent=2)

        except Exception as e:
            return json.dumps({"error": str(e)}, indent=2)
