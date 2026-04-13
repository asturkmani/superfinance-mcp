"""Simplified SnapTrade tool - account management and holdings."""

import json
import os
import re
from typing import Optional

import yfinance as yf
from snaptrade_client import SnapTrade

from users import current_user_token, get_user, update_user


_snaptrade_client = None


def get_snaptrade_client():
    """Get or initialize the SnapTrade client."""
    global _snaptrade_client
    if _snaptrade_client is None:
        try:
            consumer_key = os.getenv("SNAPTRADE_CONSUMER_KEY")
            client_id = os.getenv("SNAPTRADE_CLIENT_ID")
            if consumer_key and client_id:
                _snaptrade_client = SnapTrade(
                    consumer_key=consumer_key,
                    client_id=client_id
                )
        except Exception as e:
            print(f"Warning: SnapTrade client initialization failed: {e}")
    return _snaptrade_client


def _resolve_credentials(user_id: Optional[str], user_secret: Optional[str]):
    """Resolve user credentials: explicit args > user token context > env vars."""
    if user_id and user_secret:
        return user_id, user_secret

    token = current_user_token.get()
    if token:
        user_data = get_user(token)
        if user_data:
            return user_data["snaptrade_user_id"], user_data["snaptrade_user_secret"]

    return (
        user_id or os.getenv("SNAPTRADE_USER_ID"),
        user_secret or os.getenv("SNAPTRADE_USER_SECRET"),
    )


def _get_base_currency() -> str:
    """Get the current user's base currency preference."""
    token = current_user_token.get()
    if token:
        user_data = get_user(token)
        if user_data:
            return user_data.get("base_currency", "USD")
    return os.getenv("BASE_CURRENCY", "USD")


def _enrich_positions(positions: list, base_currency: str) -> tuple[list, float]:
    """Replace SnapTrade prices with live Yahoo Finance prices and convert to base currency.

    Returns (enriched_positions, total_value_base).
    """
    if not positions:
        return [], 0.0

    # Collect unique symbols and currencies
    symbols = set()
    currencies_needed = set()
    for pos in positions:
        sym = pos.get("symbol")
        if sym:
            symbols.add(sym)
        ccy = pos.get("currency")
        if ccy and ccy != base_currency:
            currencies_needed.add(ccy)

    # Batch-fetch live prices
    live_prices = {}
    if symbols:
        try:
            tickers = yf.Tickers(" ".join(symbols))
            for sym in symbols:
                try:
                    info = tickers.tickers[sym].info
                    price = info.get("regularMarketPrice") or info.get("previousClose")
                    if price:
                        live_prices[sym] = float(price)
                except Exception:
                    pass
        except Exception:
            pass

    # Batch-fetch FX rates
    fx_rates = {}
    if currencies_needed:
        fx_tickers_str = " ".join(f"{ccy}{base_currency}=X" for ccy in currencies_needed)
        try:
            fx_data = yf.Tickers(fx_tickers_str)
            for ccy in currencies_needed:
                try:
                    pair = f"{ccy}{base_currency}=X"
                    info = fx_data.tickers[pair].info
                    rate = info.get("regularMarketPrice") or info.get("previousClose")
                    if rate:
                        fx_rates[ccy] = float(rate)
                except Exception:
                    pass
        except Exception:
            pass

    # Enrich each position
    enriched = []
    total_base = 0.0
    for pos in positions:
        sym = pos.get("symbol")
        units = pos.get("units") or 0
        ccy = pos.get("currency") or base_currency

        current_price = live_prices.get(sym) or pos.get("price") or 0
        avg_cost = pos.get("average_purchase_price") or 0
        market_value = round(units * current_price, 2)
        cost_basis = round(units * avg_cost, 2)
        unrealised_pnl = round(market_value - cost_basis, 2)
        unrealised_pnl_pct = round((unrealised_pnl / cost_basis) * 100, 2) if cost_basis else 0.0

        fx_rate = fx_rates.get(ccy, 1.0) if ccy != base_currency else 1.0
        value_base = round(market_value * fx_rate, 2)
        total_base += value_base

        enriched.append({
            "symbol": sym,
            "description": pos.get("description"),
            "currency": ccy,
            "fx_rate": fx_rate if ccy != base_currency else None,
            "units": units,
            "avg_cost": avg_cost,
            "current_price": current_price,
            "cost_basis": cost_basis,
            "market_value": market_value,
            "market_value_base": value_base,
            "unrealised_pnl": unrealised_pnl,
            "unrealised_pnl_pct": unrealised_pnl_pct,
        })

    return enriched, round(total_base, 2)


def _safe_get(obj, key, default=None):
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _to_dict(obj):
    if hasattr(obj, 'to_dict'):
        return obj.to_dict()
    if hasattr(obj, '__dict__') and not isinstance(obj, dict):
        return vars(obj)
    return obj


def _extract_holdings_for_account(client, account_id, user_id, user_secret, base_currency):
    """Fetch holdings + cash balances for a single account. Returns dict."""
    response = client.account_information.get_user_holdings(
        account_id=account_id,
        user_id=user_id,
        user_secret=user_secret
    )
    holdings = response.body if hasattr(response, 'body') else response
    if hasattr(holdings, 'to_dict'):
        holdings = holdings.to_dict()

    account_data = _safe_get(holdings, "account", {})
    if hasattr(account_data, 'to_dict'):
        account_data = account_data.to_dict()

    # Extract positions
    raw_positions = []
    positions = _safe_get(holdings, "positions", [])
    for position in positions:
        position = _to_dict(position)

        sym_outer = _to_dict(_safe_get(position, "symbol", {}))
        sym_inner = _to_dict(_safe_get(sym_outer, "symbol", {}))

        ticker = _safe_get(sym_inner, "symbol") if isinstance(sym_inner, dict) else sym_inner
        description = _safe_get(sym_inner, "description") if isinstance(sym_inner, dict) else None

        pos_ccy = _to_dict(_safe_get(position, "currency", {}))
        ccy_code = _safe_get(pos_ccy, "code") if isinstance(pos_ccy, dict) else None

        if not ccy_code:
            sym_ccy = _to_dict(_safe_get(sym_inner, "currency", {})) if isinstance(sym_inner, dict) else {}
            ccy_code = _safe_get(sym_ccy, "code") if isinstance(sym_ccy, dict) else None

        raw_positions.append({
            "symbol": ticker,
            "description": description,
            "units": _safe_get(position, "units"),
            "price": _safe_get(position, "price"),
            "average_purchase_price": _safe_get(position, "average_purchase_price"),
            "currency": ccy_code,
        })

    # Extract options positions (separate endpoint from stock holdings)
    option_positions = []
    try:
        opts_resp = client.options.list_option_holdings(
            account_id=account_id,
            user_id=user_id,
            user_secret=user_secret
        )
        opts = opts_resp.body if hasattr(opts_resp, 'body') else opts_resp
        for opt in opts:
            opt = _to_dict(opt)
            opt_sym = _to_dict(_safe_get(opt, "symbol", {}))
            option_symbol = _to_dict(_safe_get(opt_sym, "option_symbol", {}))
            underlying = _to_dict(_safe_get(option_symbol, "underlying_symbol", {}))
            underlying_ccy = _to_dict(_safe_get(underlying, "currency", {}))

            ticker = _safe_get(underlying, "symbol") if isinstance(underlying, dict) else None
            # SnapTrade ticker e.g. "CORN  260821C00022000" — strip spaces for Yahoo
            raw_ticker = _safe_get(option_symbol, "ticker") or ""
            yahoo_ticker = raw_ticker.replace(" ", "")
            strike = _safe_get(option_symbol, "strike_price")
            expiry = _safe_get(option_symbol, "expiration_date")
            opt_type = _safe_get(option_symbol, "option_type")
            ccy_code = _safe_get(underlying_ccy, "code") if isinstance(underlying_ccy, dict) else None

            if not ccy_code:
                pos_ccy = _to_dict(_safe_get(opt, "currency", {}))
                ccy_code = _safe_get(pos_ccy, "code") if isinstance(pos_ccy, dict) else None

            option_positions.append({
                "underlying": ticker,
                "strike": strike,
                "expiration": str(expiry) if expiry else None,
                "type": opt_type,
                "units": _safe_get(opt, "units"),
                "price": _safe_get(opt, "price"),
                "average_purchase_price": _safe_get(opt, "average_purchase_price"),
                "currency": ccy_code,
                "_yahoo_ticker": yahoo_ticker,
            })
    except Exception:
        pass

    # Batch-fetch live option prices from Yahoo Finance
    opt_yahoo_tickers = {op["_yahoo_ticker"] for op in option_positions if op.get("_yahoo_ticker")}
    live_opt_prices = {}
    if opt_yahoo_tickers:
        try:
            tickers = yf.Tickers(" ".join(opt_yahoo_tickers))
            for sym in opt_yahoo_tickers:
                try:
                    info = tickers.tickers[sym].info
                    price = info.get("regularMarketPrice") or info.get("previousClose")
                    if price:
                        live_opt_prices[sym] = float(price)
                except Exception:
                    pass
        except Exception:
            pass

    for op in option_positions:
        yt = op.pop("_yahoo_ticker", None)
        if yt and yt in live_opt_prices:
            op["price"] = live_opt_prices[yt]

    # Extract cash balances
    cash_balances = []
    balances = _safe_get(holdings, "balances", [])
    for bal in balances:
        bal = _to_dict(bal)
        bal_ccy = _to_dict(_safe_get(bal, "currency", {}))
        cash_balances.append({
            "currency": _safe_get(bal_ccy, "code") if isinstance(bal_ccy, dict) else None,
            "cash": _safe_get(bal, "cash"),
            "buying_power": _safe_get(bal, "buying_power"),
        })

    # Enrich positions with live prices
    enriched, positions_total = _enrich_positions(raw_positions, base_currency)

    # Convert cash to base currency
    cash_currencies = set()
    for cb in cash_balances:
        ccy = cb.get("currency")
        if ccy and ccy != base_currency:
            cash_currencies.add(ccy)

    cash_fx = {}
    if cash_currencies:
        fx_str = " ".join(f"{c}{base_currency}=X" for c in cash_currencies)
        try:
            fx_data = yf.Tickers(fx_str)
            for c in cash_currencies:
                try:
                    pair = f"{c}{base_currency}=X"
                    info = fx_data.tickers[pair].info
                    rate = info.get("regularMarketPrice") or info.get("previousClose")
                    if rate:
                        cash_fx[c] = float(rate)
                except Exception:
                    pass
        except Exception:
            pass

    cash_total_base = 0.0
    for cb in cash_balances:
        cash = cb.get("cash") or 0
        ccy = cb.get("currency") or base_currency
        fx_rate = cash_fx.get(ccy, 1.0) if ccy != base_currency else 1.0
        cb["cash_base"] = round(cash * fx_rate, 2)
        cb["fx_rate"] = fx_rate if ccy != base_currency else None
        cash_total_base += cb["cash_base"]

    cash_total_base = round(cash_total_base, 2)

    # Compute options value with PnL (price * units * 100 for standard contracts)
    options_total_base = 0.0
    for op in option_positions:
        current_price = op.get("price") or 0
        units = op.get("units") or 0
        avg_cost = op.get("average_purchase_price") or 0
        market_value = round(current_price * units * 100, 2)
        cost_basis = round(avg_cost * abs(units), 2)
        unrealised_pnl = round(market_value - cost_basis, 2) if units >= 0 else round(cost_basis - abs(market_value), 2)
        unrealised_pnl_pct = round((unrealised_pnl / cost_basis) * 100, 2) if cost_basis else 0.0
        ccy = op.get("currency") or base_currency
        fx_rate = cash_fx.get(ccy, 1.0) if ccy != base_currency else 1.0
        value_base = round(market_value * fx_rate, 2)

        op["current_price"] = current_price
        op["avg_cost"] = avg_cost
        op["cost_basis"] = cost_basis
        op["market_value"] = market_value
        op["market_value_base"] = value_base
        op["unrealised_pnl"] = unrealised_pnl
        op["unrealised_pnl_pct"] = unrealised_pnl_pct
        del op["price"]
        del op["average_purchase_price"]

        options_total_base += value_base
    options_total_base = round(options_total_base, 2)

    account_total_base = round(positions_total + cash_total_base + options_total_base, 2)

    return {
        "account": {
            "id": _safe_get(account_data, "id"),
            "name": _safe_get(account_data, "name"),
            "number": _safe_get(account_data, "number"),
            "institution": _safe_get(account_data, "institution_name"),
        },
        "positions": enriched,
        "option_positions": option_positions,
        "cash_balances": cash_balances,
        "positions_value_base": positions_total,
        "options_value_base": options_total_base,
        "cash_value_base": cash_total_base,
        "total_value_base": account_total_base,
    }


def register_snaptrade_v2(server):
    """Register simplified SnapTrade tool."""

    @server.tool()
    def snaptrade(
        action: str,
        account_id: Optional[str] = None,
        account_name: Optional[str] = None,
        currency: Optional[str] = None
    ) -> str:
        """
        Manage brokerage accounts via SnapTrade.

        IMPORTANT: Use "portfolio" as the default action when the user asks about their
        holdings, positions, or portfolio. Only use "holdings" if they specifically want
        a single account.

        Actions:
        - portfolio: Get ALL holdings (stocks + options + cash) across ALL accounts with live prices. USE THIS BY DEFAULT.
        - holdings: Get holdings for a single specific account only
        - connect: Get URL to connect a brokerage account
        - accounts: List connected brokerage accounts
        - disconnect: Remove a brokerage connection (by account_id or account_name)
        - set_currency: Set your base currency for portfolio valuation (e.g. "GBP")

        Portfolio and holdings return stock positions, option positions, and cash balances
        separately, each with values converted to the user's base currency.

        Your credentials are automatically loaded from your user profile.

        Args:
            action: Action to perform (portfolio|holdings|connect|accounts|disconnect|set_currency)
            account_id: Account ID (required for holdings, optional for disconnect)
            account_name: Account or institution name to disconnect (e.g. "Trading212")
            currency: Base currency code for set_currency action (e.g. "GBP", "USD", "EUR")

        Returns:
            JSON with results

        Examples:
            snaptrade(action="portfolio")
            snaptrade(action="holdings", account_id="abc-123")
            snaptrade(action="connect")
            snaptrade(action="accounts")
            snaptrade(action="disconnect", account_name="Trading212")
            snaptrade(action="set_currency", currency="GBP")
        """
        try:
            client = get_snaptrade_client()
            if not client:
                return json.dumps({
                    "error": "SnapTrade not configured",
                    "message": "Set SNAPTRADE_CONSUMER_KEY and SNAPTRADE_CLIENT_ID environment variables"
                }, indent=2)

            user_id, user_secret = _resolve_credentials(None, None)

            if action == "connect":
                if not user_id or not user_secret:
                    return json.dumps({
                        "error": "Credentials required",
                        "message": "Register at POST /register first to get your personal MCP link"
                    }, indent=2)

                response = client.authentication.login_snap_trade_user(
                    user_id=user_id,
                    user_secret=user_secret
                )
                data = response.body if hasattr(response, 'body') else response
                if hasattr(data, 'to_dict'):
                    data = data.to_dict()

                redirect_uri = (
                    data.get("redirectURI") if isinstance(data, dict)
                    else getattr(data, 'redirect_uri', None)
                )

                return json.dumps({
                    "success": True,
                    "connection_url": redirect_uri,
                    "message": "Open this URL in your browser to connect your brokerage account"
                }, indent=2)

            elif action == "accounts":
                if not user_id or not user_secret:
                    return json.dumps({"error": "Credentials required"}, indent=2)

                response = client.account_information.list_user_accounts(
                    user_id=user_id,
                    user_secret=user_secret
                )
                accounts = response.body if hasattr(response, 'body') else response

                formatted = []
                for account in accounts:
                    if hasattr(account, 'to_dict'):
                        account = account.to_dict()
                    elif hasattr(account, '__dict__'):
                        account = vars(account)

                    formatted.append({
                        "account_id": account.get("id"),
                        "brokerage_authorization": account.get("brokerage_authorization"),
                        "name": account.get("name"),
                        "number": account.get("number"),
                        "institution": account.get("institution_name"),
                        "balance": account.get("balance"),
                    })

                return json.dumps({
                    "success": True,
                    "count": len(formatted),
                    "accounts": formatted
                }, indent=2)

            elif action == "portfolio":
                if not user_id or not user_secret:
                    return json.dumps({"error": "Credentials required"}, indent=2)

                base_ccy = _get_base_currency()

                # List all accounts
                response = client.account_information.list_user_accounts(
                    user_id=user_id,
                    user_secret=user_secret
                )
                accounts = response.body if hasattr(response, 'body') else response

                account_results = []
                grand_total = 0.0
                for acct in accounts:
                    acct = _to_dict(acct)
                    aid = acct.get("id")
                    if not aid:
                        continue
                    acct_data = _extract_holdings_for_account(
                        client, aid, user_id, user_secret, base_ccy
                    )
                    account_results.append(acct_data)
                    grand_total += acct_data["total_value_base"]

                return json.dumps({
                    "success": True,
                    "base_currency": base_ccy,
                    "accounts": account_results,
                    "grand_total_base": round(grand_total, 2),
                }, indent=2)

            elif action == "holdings":
                if not account_id:
                    return json.dumps({
                        "error": "account_id required for holdings action"
                    }, indent=2)
                if not user_id or not user_secret:
                    return json.dumps({"error": "Credentials required"}, indent=2)

                base_ccy = _get_base_currency()
                result = _extract_holdings_for_account(
                    client, account_id, user_id, user_secret, base_ccy
                )
                result["success"] = True
                result["base_currency"] = base_ccy

                return json.dumps(result, indent=2)

            elif action == "disconnect":
                if not user_id or not user_secret:
                    return json.dumps({"error": "Credentials required"}, indent=2)
                if not account_id and not account_name:
                    return json.dumps({
                        "error": "Provide account_id or account_name to disconnect"
                    }, indent=2)

                response = client.account_information.list_user_accounts(
                    user_id=user_id,
                    user_secret=user_secret
                )
                accounts = response.body if hasattr(response, 'body') else response

                target = None
                for acct in accounts:
                    if hasattr(acct, 'to_dict'):
                        acct = acct.to_dict()
                    elif hasattr(acct, '__dict__'):
                        acct = vars(acct)

                    if account_id and acct.get("id") == account_id:
                        target = acct
                        break
                    if account_name:
                        name_lower = account_name.lower()
                        if (name_lower in (acct.get("name") or "").lower()
                                or name_lower in (acct.get("institution_name") or "").lower()):
                            target = acct
                            break

                if not target:
                    return json.dumps({
                        "error": f"No account found matching: {account_name or account_id}",
                        "hint": "Use snaptrade(action='accounts') to see your connected accounts"
                    }, indent=2)

                auth_id = target.get("brokerage_authorization")
                if not auth_id:
                    return json.dumps({
                        "error": "No brokerage_authorization found for this account"
                    }, indent=2)

                client.connections.remove_brokerage_authorization(
                    authorization_id=auth_id,
                    user_id=user_id,
                    user_secret=user_secret
                )

                return json.dumps({
                    "success": True,
                    "disconnected": {
                        "name": target.get("name"),
                        "institution": target.get("institution_name"),
                        "account_id": target.get("id"),
                    },
                    "message": "Brokerage account disconnected successfully"
                }, indent=2)

            elif action == "set_currency":
                code = (currency or "").strip().upper()
                if not re.match(r"^[A-Z]{3}$", code):
                    return json.dumps({
                        "error": "Invalid currency code. Use 3-letter ISO code (e.g. USD, GBP, EUR)"
                    }, indent=2)

                token = current_user_token.get()
                if not token:
                    return json.dumps({"error": "User context required"}, indent=2)

                old = _get_base_currency()
                update_user(token, {"base_currency": code})

                return json.dumps({
                    "success": True,
                    "previous": old,
                    "base_currency": code,
                    "message": f"Base currency changed from {old} to {code}"
                }, indent=2)

            else:
                return json.dumps({
                    "error": f"Invalid action: {action}",
                    "valid_actions": ["connect", "accounts", "portfolio", "holdings", "disconnect", "set_currency"]
                }, indent=2)

        except Exception as e:
            return json.dumps({"error": str(e)}, indent=2)
