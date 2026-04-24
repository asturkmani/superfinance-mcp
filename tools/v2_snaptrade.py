"""Simplified SnapTrade tool - account management and holdings."""

import json
import os
import re
from typing import Optional

import yfinance as yf
from snaptrade_client import SnapTrade

from users import current_user_token, get_user, update_user


# Minor/fractional currencies that need conversion to their major currency
# GBX = British pence (1/100 GBP), ILA = Israeli Agorot (1/100 ILS)
MINOR_CURRENCIES = {
    "GBX": ("GBP", 100),  # British pence -> pounds
    "GBx": ("GBP", 100),
    "ILA": ("ILS", 100),  # Israeli agorot -> shekels
}


def _normalize_currency(ccy: str) -> tuple[str, float]:
    """Convert minor currency to major currency with divisor.

    Returns (major_currency, divisor) where divisor is the amount to divide by.
    E.g., GBX -> ("GBP", 100) meaning 1 GBX = 0.01 GBP
    """
    if ccy in MINOR_CURRENCIES:
        return MINOR_CURRENCIES[ccy]
    return (ccy, 1)


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

    # Batch-fetch FX rates (handling minor currencies like GBX -> GBP)
    fx_rates = {}
    currency_divisors = {}
    major_currencies_needed = set()

    for ccy in currencies_needed:
        major, divisor = _normalize_currency(ccy)
        currency_divisors[ccy] = (major, divisor)
        if major != base_currency:
            major_currencies_needed.add(major)

    if major_currencies_needed:
        fx_tickers_str = " ".join(f"{ccy}{base_currency}=X" for ccy in major_currencies_needed)
        try:
            fx_data = yf.Tickers(fx_tickers_str)
            for major_ccy in major_currencies_needed:
                try:
                    pair = f"{major_ccy}{base_currency}=X"
                    info = fx_data.tickers[pair].info
                    rate = info.get("regularMarketPrice") or info.get("previousClose")
                    if rate:
                        fx_rates[major_ccy] = float(rate)
                except Exception:
                    pass
        except Exception:
            pass

    # Build effective FX rates for original currencies (applying divisors)
    effective_fx_rates = {}
    for ccy in currencies_needed:
        major, divisor = currency_divisors[ccy]
        if major == base_currency:
            effective_fx_rates[ccy] = 1.0 / divisor
        else:
            major_rate = fx_rates.get(major, 1.0)
            effective_fx_rates[ccy] = major_rate / divisor

    # Enrich each position
    enriched = []
    total_base = 0.0
    for pos in positions:
        sym = pos.get("symbol")
        units = pos.get("units") or 0
        ccy = pos.get("currency") or base_currency

        # Price priority: Yahoo Finance > manual_price > cost_price
        price_source = "unknown"
        current_price = 0

        if sym and sym in live_prices:
            current_price = live_prices[sym]
            price_source = "yahoo"
        elif pos.get("price"):  # manual_price
            current_price = pos.get("price")
            price_source = "manual"
        elif pos.get("average_purchase_price"):  # cost_price as fallback
            current_price = pos.get("average_purchase_price")
            price_source = "cost"

        avg_cost = pos.get("average_purchase_price") or 0
        market_value = round(units * current_price, 2)
        cost_basis = round(units * avg_cost, 2)
        unrealised_pnl = round(market_value - cost_basis, 2)
        unrealised_pnl_pct = round((unrealised_pnl / cost_basis) * 100, 2) if cost_basis else 0.0

        fx_rate = effective_fx_rates.get(ccy, 1.0) if ccy != base_currency else 1.0
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
            "price_source": price_source,
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

    # Convert cash to base currency (handling minor currencies like GBX)
    cash_currencies = set()
    for cb in cash_balances:
        ccy = cb.get("currency")
        if ccy and ccy != base_currency:
            cash_currencies.add(ccy)

    # Build FX rates with minor currency handling
    cash_currency_divisors = {}
    cash_major_currencies = set()
    for ccy in cash_currencies:
        major, divisor = _normalize_currency(ccy)
        cash_currency_divisors[ccy] = (major, divisor)
        if major != base_currency:
            cash_major_currencies.add(major)

    cash_fx_raw = {}
    if cash_major_currencies:
        fx_str = " ".join(f"{c}{base_currency}=X" for c in cash_major_currencies)
        try:
            fx_data = yf.Tickers(fx_str)
            for c in cash_major_currencies:
                try:
                    pair = f"{c}{base_currency}=X"
                    info = fx_data.tickers[pair].info
                    rate = info.get("regularMarketPrice") or info.get("previousClose")
                    if rate:
                        cash_fx_raw[c] = float(rate)
                except Exception:
                    pass
        except Exception:
            pass

    # Build effective FX rates for original currencies
    cash_fx = {}
    for ccy in cash_currencies:
        major, divisor = cash_currency_divisors[ccy]
        if major == base_currency:
            cash_fx[ccy] = 1.0 / divisor
        else:
            major_rate = cash_fx_raw.get(major, 1.0)
            cash_fx[ccy] = major_rate / divisor

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
        # Use cash_fx which now handles minor currencies properly
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
    """Register the unified portfolio tool."""

    @server.tool()
    def portfolio(
        action: str,
        account_id: Optional[str] = None,
        account_name: Optional[str] = None,
        currency: Optional[str] = None,
        # Manual holding fields
        id: Optional[str] = None,
        symbol: Optional[str] = None,
        description: Optional[str] = None,
        units: Optional[float] = None,
        cost_price: Optional[float] = None,
        manual_price: Optional[float] = None,
    ) -> str:
        """
        Unified portfolio management — brokerage accounts (SnapTrade) and manual/private holdings.

        IMPORTANT: Use "overview" as the default action when the user asks about their
        holdings, positions, or portfolio.

        Brokerage actions:
        - overview: Get ALL holdings (brokerage + manual) across ALL accounts with live prices. USE THIS BY DEFAULT.
        - holdings: Get holdings for a single specific brokerage account only
        - connect: Get URL to connect a brokerage account
        - accounts: List connected brokerage accounts
        - disconnect: Remove a brokerage connection (by account_id or account_name)
        - set_currency: Set your base currency for portfolio valuation (e.g. "GBP")
        - add_manual: Add a manual/private holding (pension, loan, private equity, etc.)
        - update_manual: Update a manual holding by id
        - remove_manual: Remove a manual holding by id

        For trackable holdings, set symbol (e.g. "VOO") to get live Yahoo prices.
        For non-trackable holdings, omit symbol and set manual_price.
        Manual holdings appear in overview alongside brokerage accounts.

        Args:
            action: Action to perform
            account_id: Account ID (for holdings/disconnect)
            account_name: Account or institution name (for disconnect, or grouping label for add_manual — defaults to "Manual")
            currency: Currency code (for set_currency or add_manual, e.g. "GBP")
            id: Holding ID (for update_manual/remove_manual)
            symbol: Yahoo Finance ticker (for add_manual/update_manual, e.g. "VOO")
            description: Human-readable label (for add_manual/update_manual, e.g. "Pension VOO", "Loan to X")
            units: Number of units (for add_manual/update_manual)
            cost_price: Average cost per unit (for add_manual/update_manual)
            manual_price: Manual price override, used when no symbol or Yahoo fails (for add_manual/update_manual)

        Examples:
            portfolio(action="overview")
            portfolio(action="holdings", account_id="abc-123")
            portfolio(action="connect")
            portfolio(action="add_manual", description="Pension VOO", symbol="VOO", units=500, currency="USD", cost_price=420)
            portfolio(action="add_manual", description="Loan to Mobility Giant", units=1, currency="GBP", manual_price=25000)
            portfolio(action="update_manual", id="a1b2c3d4", units=600)
            portfolio(action="remove_manual", id="a1b2c3d4")
            portfolio(action="set_currency", currency="GBP")
        """
        try:
            # Manual holding actions don't need SnapTrade
            MANUAL_ACTIONS = {"add_manual", "update_manual", "remove_manual"}
            BROKERAGE_ACTIONS = {"overview", "holdings", "connect", "accounts", "disconnect", "set_currency"}

            client = None
            user_id = user_secret = None
            if action in BROKERAGE_ACTIONS:
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

            elif action == "overview":
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

                # Include manual holdings in portfolio
                manual_section = None
                token = current_user_token.get()
                user_data = get_user(token) if token else None
                manual_list = user_data.get("manual_holdings", []) if user_data else []
                if manual_list:
                    positions = []
                    for h in manual_list:
                        positions.append({
                            "symbol": h.get("symbol"),
                            "description": h.get("description"),
                            "units": h.get("units") or 1,
                            "price": h.get("manual_price"),
                            "average_purchase_price": h.get("cost_price"),
                            "currency": h.get("currency") or base_ccy,
                            "_account_name": h.get("account_name", "Manual"),
                            "_id": h["id"],
                        })
                    enriched, manual_total = _enrich_positions(positions, base_ccy)
                    for i, e in enumerate(enriched):
                        e["id"] = positions[i]["_id"]
                        e["account_name"] = positions[i]["_account_name"]
                    manual_section = {
                        "holdings": enriched,
                        "total_value_base": manual_total,
                    }
                    grand_total += manual_total

                result = {
                    "success": True,
                    "base_currency": base_ccy,
                    "accounts": account_results,
                    "grand_total_base": round(grand_total, 2),
                }
                if manual_section:
                    result["manual_holdings"] = manual_section

                return json.dumps(result, indent=2)

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

            # --- Manual holding actions ---

            elif action == "add_manual":
                token = current_user_token.get()
                if not token:
                    return json.dumps({"error": "User context required"}, indent=2)
                if not description:
                    return json.dumps({"error": "description is required"}, indent=2)
                if units is None:
                    return json.dumps({"error": "units is required"}, indent=2)
                if not currency:
                    return json.dumps({"error": "currency is required (e.g. USD, GBP)"}, indent=2)

                import uuid as _uuid
                holding = {
                    "id": _uuid.uuid4().hex[:8],
                    "symbol": symbol.upper() if symbol else None,
                    "description": description,
                    "units": float(units),
                    "currency": currency.upper(),
                    "cost_price": float(cost_price) if cost_price is not None else None,
                    "manual_price": float(manual_price) if manual_price is not None else None,
                    "account_name": account_name or "Manual",
                }

                user_data = get_user(token) or {}
                all_holdings = user_data.get("manual_holdings", [])
                all_holdings.append(holding)
                update_user(token, {"manual_holdings": all_holdings})

                return json.dumps({"success": True, "holding": holding}, indent=2)

            elif action == "update_manual":
                token = current_user_token.get()
                if not token:
                    return json.dumps({"error": "User context required"}, indent=2)
                if not id:
                    return json.dumps({"error": "id is required for update_manual"}, indent=2)

                user_data = get_user(token) or {}
                all_holdings = user_data.get("manual_holdings", [])
                target = next((h for h in all_holdings if h["id"] == id), None)
                if not target:
                    return json.dumps({"error": f"No holding found with id '{id}'"}, indent=2)

                if symbol is not None:
                    target["symbol"] = symbol.upper() if symbol else None
                if description is not None:
                    target["description"] = description
                if units is not None:
                    target["units"] = float(units)
                if currency is not None:
                    target["currency"] = currency.upper()
                if cost_price is not None:
                    target["cost_price"] = float(cost_price)
                if manual_price is not None:
                    target["manual_price"] = float(manual_price)
                if account_name is not None:
                    target["account_name"] = account_name

                update_user(token, {"manual_holdings": all_holdings})
                return json.dumps({"success": True, "holding": target}, indent=2)

            elif action == "remove_manual":
                token = current_user_token.get()
                if not token:
                    return json.dumps({"error": "User context required"}, indent=2)
                if not id:
                    return json.dumps({"error": "id is required for remove_manual"}, indent=2)

                user_data = get_user(token) or {}
                all_holdings = user_data.get("manual_holdings", [])
                before = len(all_holdings)
                all_holdings = [h for h in all_holdings if h["id"] != id]
                if len(all_holdings) == before:
                    return json.dumps({"error": f"No holding found with id '{id}'"}, indent=2)

                update_user(token, {"manual_holdings": all_holdings})
                return json.dumps({"success": True, "removed": id}, indent=2)

            else:
                return json.dumps({
                    "error": f"Invalid action: {action}",
                    "valid_actions": [
                        "overview", "holdings", "connect", "accounts", "disconnect", "set_currency",
                        "add_manual", "update_manual", "remove_manual",
                    ]
                }, indent=2)

        except Exception as e:
            return json.dumps({"error": str(e)}, indent=2)
