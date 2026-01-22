"""Holdings service - unified portfolio view combining all sources."""

import os
from typing import Optional

from helpers.pricing import get_live_price, get_fx_rate_cached
from helpers.portfolio import load_portfolios
from services.snaptrade_service import get_snaptrade_client


class HoldingsService:
    """Service class for unified holdings operations."""

    @staticmethod
    async def list_all_holdings(
        user_id: Optional[str] = None,
        user_secret: Optional[str] = None,
        reporting_currency: Optional[str] = None
    ) -> dict:
        """
        Get all holdings from SnapTrade and manual portfolios.

        Args:
            user_id: SnapTrade user ID
            user_secret: SnapTrade user secret
            reporting_currency: Optional currency for conversion

        Returns:
            dict with unified holdings view
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
            client = get_snaptrade_client()
            if client:
                user_id = user_id or os.getenv("SNAPTRADE_USER_ID")
                user_secret = user_secret or os.getenv("SNAPTRADE_USER_SECRET")
                if user_id and user_secret:
                    resp = client.account_information.list_user_accounts(
                        user_id=user_id, user_secret=user_secret
                    )
                    accounts = resp.body if hasattr(resp, 'body') else resp

            # Process SnapTrade accounts
            for account in accounts:
                if hasattr(account, 'to_dict'):
                    account = account.to_dict()

                account_id = account.get("id")
                if not account_id:
                    continue

                try:
                    resp = client.account_information.get_user_holdings(
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

                    # Extract cash
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

                    account_holdings = {}
                    account_cost_basis = {}
                    positions = []

                    # Process positions
                    for pos in holdings.get("positions", []):
                        if hasattr(pos, 'to_dict'):
                            pos = pos.to_dict()

                        sym_data = pos.get("symbol", {})
                        if hasattr(sym_data, 'to_dict'):
                            sym_data = sym_data.to_dict()

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

                        pos_data = {
                            "symbol": ticker,
                            "description": desc,
                            "units": round(units, 6) if units else 0,
                            "currency": curr,
                            "price": round(price, 4) if price else None,
                            "price_source": price_source,
                            "market_value": round(market_value, 2) if market_value else None,
                            "equity_value": round(market_value, 2) if market_value else None,  # Will be adjusted for margin below
                            "average_cost": round(avg_cost, 4) if avg_cost else None,
                            "cost_basis": round(cost_basis, 2) if cost_basis else None,
                            "unrealized_pnl": round(pnl, 2) if pnl else None,
                            "unrealized_pnl_pct": pnl_pct
                        }

                        if curr and market_value:
                            account_holdings[curr] = account_holdings.get(curr, 0) + market_value
                            grand_holdings[curr] = grand_holdings.get(curr, 0) + market_value
                        if curr and cost_basis:
                            account_cost_basis[curr] = account_cost_basis.get(curr, 0) + cost_basis
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

                    # Calculate account totals
                    account_value = {}
                    for c, v in account_holdings.items():
                        account_value[c] = account_value.get(c, 0) + v
                    for c, v in account_cash.items():
                        account_value[c] = account_value.get(c, 0) + v

                    # Calculate equity ratio per currency (to account for margin)
                    # When cash is negative (margin), equity = holdings + cash < holdings
                    equity_ratio = {}
                    for c in account_holdings:
                        holdings_val = account_holdings.get(c, 0)
                        equity_val = account_value.get(c, 0)
                        if holdings_val > 0:
                            equity_ratio[c] = equity_val / holdings_val
                        else:
                            equity_ratio[c] = 1.0

                    # Add equity_value to each position (market_value adjusted for margin)
                    for pos_data in positions:
                        curr = pos_data.get("currency")
                        market_value = pos_data.get("market_value")
                        if curr and market_value:
                            ratio = equity_ratio.get(curr, 1.0)
                            pos_data["equity_value"] = round(market_value * ratio, 2)

                    account_pnl = {}
                    for c in account_holdings:
                        h = account_holdings.get(c, 0)
                        cb = account_cost_basis.get(c, 0)
                        if cb > 0:
                            account_pnl[c] = h - cb

                    account_totals = {
                        "holdings": {k: round(v, 2) for k, v in account_holdings.items()},
                        "cash": {k: round(v, 2) for k, v in account_cash.items()},
                        "value": {k: round(v, 2) for k, v in account_value.items()},
                        "cost_basis": {k: round(v, 2) for k, v in account_cost_basis.items()},
                        "unrealized_pnl": {k: round(v, 2) for k, v in account_pnl.items()}
                    }

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

                    all_accounts.append({
                        "source": "snaptrade",
                        "account_id": account_id,
                        "name": account.get("name"),
                        "institution": account.get("institution_name"),
                        "account_type": account.get("raw_type"),
                        "brokerage_value": {"amount": round(brokerage_value, 2) if brokerage_value else None, "currency": brokerage_currency},
                        "totals": account_totals,
                        "positions": positions
                    })

                except Exception as e:
                    all_accounts.append({
                        "source": "snaptrade",
                        "account_id": account_id,
                        "name": account.get("name"),
                        "error": str(e)
                    })

            snaptrade_count = len(all_accounts)

            # Step 2: Manual portfolios
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

                        pos_data = {
                            "id": pos.get("id"),
                            "name": pos.get("name"),
                            "symbol": symbol,
                            "units": units,
                            "currency": curr,
                            "price": round(live_price, 2) if live_price else None,
                            "price_source": price_source,
                            "market_value": round(market_value, 2) if market_value else None,
                            "equity_value": round(market_value, 2) if market_value else None,  # Same as market_value (no margin in manual portfolios)
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

            return result

        except Exception as e:
            return {"error": str(e)}
