"""Unified portfolio management tools.

Provides a single interface for both manual portfolios and synced brokerage accounts.
- Manual portfolios: User-managed positions stored locally
- Synced portfolios: Brokerage accounts connected via SnapTrade
"""

import json
import os
from datetime import datetime
from typing import Optional, Literal

from helpers.portfolio import load_portfolios, save_portfolios, generate_position_id
from helpers.pricing import get_live_price, get_fx_rate_cached
from helpers.classification import (
    get_classification,
    get_known_categories,
    get_all_classifications,
    update_classification as _update_classification,
    add_category as _add_category,
)
from tools.snaptrade import get_snaptrade_client


def _get_snaptrade_credentials():
    """Get SnapTrade credentials from environment."""
    return (
        os.getenv("SNAPTRADE_USER_ID"),
        os.getenv("SNAPTRADE_USER_SECRET")
    )


def _get_manual_portfolios_summary() -> list[dict]:
    """Get summary of all manual portfolios."""
    portfolios = []
    try:
        data = load_portfolios()
        for pid, portfolio in data.get("portfolios", {}).items():
            # Calculate total value
            total_value = 0
            for pos in portfolio.get("positions", []):
                units = pos.get("units", 0)
                symbol = pos.get("symbol")
                manual_price = pos.get("manual_price")

                price = None
                if symbol:
                    live_data = get_live_price(symbol)
                    if live_data.get("price"):
                        price = live_data["price"]
                if price is None and manual_price:
                    price = manual_price

                if price and units:
                    total_value += units * price

            portfolios.append({
                "id": pid,
                "name": portfolio.get("name", pid),
                "type": "manual",
                "description": portfolio.get("description"),
                "position_count": len(portfolio.get("positions", [])),
                "total_value": round(total_value, 2),
                "created_at": portfolio.get("created_at"),
                "updated_at": portfolio.get("updated_at"),
            })
    except Exception as e:
        print(f"Error loading manual portfolios: {e}")

    return portfolios


def _get_synced_portfolios_summary() -> list[dict]:
    """Get summary of all synced (SnapTrade) portfolios."""
    portfolios = []

    snaptrade_client = get_snaptrade_client()
    if not snaptrade_client:
        return portfolios

    user_id, user_secret = _get_snaptrade_credentials()
    if not user_id or not user_secret:
        return portfolios

    try:
        resp = snaptrade_client.account_information.list_user_accounts(
            user_id=user_id, user_secret=user_secret
        )
        accounts = resp.body if hasattr(resp, 'body') else resp

        for account in accounts:
            if hasattr(account, 'to_dict'):
                account = account.to_dict()

            account_id = account.get("id")
            if not account_id:
                continue

            # Get balance info
            bal = account.get("balance", {})
            bal_total = bal.get("total", {}) if isinstance(bal, dict) else {}
            total_value = bal_total.get("amount")

            portfolios.append({
                "id": account_id,
                "name": account.get("name", "Unknown"),
                "type": "synced",
                "institution": account.get("institution_name"),
                "account_number": account.get("number"),
                "authorization_id": account.get("brokerage_authorization"),
                "total_value": round(total_value, 2) if total_value else None,
            })
    except Exception as e:
        print(f"Error loading SnapTrade accounts: {e}")

    return portfolios


def _find_portfolio(portfolio_id: str) -> tuple[Optional[str], Optional[dict]]:
    """
    Find a portfolio by ID and return its type and data.

    Returns: (type, data) where type is "manual" or "synced", or (None, None) if not found.
    """
    # Check manual portfolios first
    try:
        data = load_portfolios()
        if portfolio_id in data.get("portfolios", {}):
            return ("manual", data["portfolios"][portfolio_id])
    except Exception:
        pass

    # Check SnapTrade accounts
    snaptrade_client = get_snaptrade_client()
    if snaptrade_client:
        user_id, user_secret = _get_snaptrade_credentials()
        if user_id and user_secret:
            try:
                resp = snaptrade_client.account_information.list_user_accounts(
                    user_id=user_id, user_secret=user_secret
                )
                accounts = resp.body if hasattr(resp, 'body') else resp

                for account in accounts:
                    if hasattr(account, 'to_dict'):
                        account = account.to_dict()
                    if account.get("id") == portfolio_id:
                        return ("synced", account)
            except Exception:
                pass

    return (None, None)


def register_portfolio_tools(server):
    """Register unified portfolio tools with the server."""

    @server.tool()
    def list_portfolios(
        type: Literal["all", "manual", "synced"] = "all"
    ) -> str:
        """
        List all portfolios (manual and synced brokerage accounts).

        Returns summary for each portfolio including name, type, position count, and total value.
        Use get_portfolio(id) to get full position details.

        Args:
            type: Filter by type - "all" (default), "manual", or "synced"

        Returns:
            JSON with list of portfolios
        """
        portfolios = []

        if type in ["all", "manual"]:
            portfolios.extend(_get_manual_portfolios_summary())

        if type in ["all", "synced"]:
            portfolios.extend(_get_synced_portfolios_summary())

        # Sort by total value descending
        portfolios.sort(key=lambda p: p.get("total_value") or 0, reverse=True)

        return json.dumps({
            "success": True,
            "count": len(portfolios),
            "manual_count": len([p for p in portfolios if p["type"] == "manual"]),
            "synced_count": len([p for p in portfolios if p["type"] == "synced"]),
            "portfolios": portfolios
        }, indent=2)

    @server.tool()
    def get_portfolio(
        portfolio_id: str,
        reporting_currency: Optional[str] = None
    ) -> str:
        """
        Get positions in a portfolio (works for both manual and synced).

        Returns all positions with live prices, market values, and P&L.

        Args:
            portfolio_id: The portfolio ID (from list_portfolios)
            reporting_currency: Optional currency code (e.g., "GBP") to convert values

        Returns:
            JSON with portfolio details and positions
        """
        portfolio_type, portfolio_data = _find_portfolio(portfolio_id)

        if portfolio_type is None:
            return json.dumps({
                "error": f"Portfolio '{portfolio_id}' not found",
                "hint": "Use list_portfolios() to see available portfolios"
            }, indent=2)

        fx_cache = {}

        if portfolio_type == "manual":
            # Process manual portfolio
            positions = []
            total_value = 0
            total_cost_basis = 0

            for pos in portfolio_data.get("positions", []):
                symbol = pos.get("symbol")
                units = pos.get("units", 0)
                avg_cost = pos.get("average_cost", 0)
                curr = pos.get("currency", "USD")
                manual_price = pos.get("manual_price")

                # Get price
                price = None
                price_source = "none"
                if symbol:
                    live_data = get_live_price(symbol)
                    if live_data.get("price"):
                        price = live_data["price"]
                        price_source = "yahoo_finance"
                if price is None and manual_price:
                    price = manual_price
                    price_source = "manual"

                market_value = units * price if units and price else None
                cost_basis = units * avg_cost if units and avg_cost else 0

                pnl = None
                pnl_pct = None
                if market_value and cost_basis > 0:
                    pnl = market_value - cost_basis
                    pnl_pct = round((pnl / cost_basis) * 100, 2)

                # Get classification
                classification = get_classification(symbol, pos.get("name"))

                pos_data = {
                    "id": pos.get("id"),
                    "symbol": symbol,
                    "name": pos.get("name"),
                    "consolidated_name": classification.get("name"),
                    "category": classification.get("category"),
                    "units": units,
                    "currency": curr,
                    "price": round(price, 4) if price else None,
                    "price_source": price_source,
                    "market_value": round(market_value, 2) if market_value else None,
                    "average_cost": avg_cost,
                    "cost_basis": round(cost_basis, 2) if cost_basis else None,
                    "unrealized_pnl": round(pnl, 2) if pnl else None,
                    "unrealized_pnl_pct": pnl_pct,
                }

                if market_value:
                    total_value += market_value
                total_cost_basis += cost_basis

                # Currency conversion
                if reporting_currency and curr != reporting_currency and market_value:
                    fx = get_fx_rate_cached(curr, reporting_currency, fx_cache)
                    if fx:
                        pos_data["converted"] = {
                            "currency": reporting_currency,
                            "market_value": round(market_value * fx, 2),
                            "cost_basis": round(cost_basis * fx, 2) if cost_basis else None,
                        }

                positions.append(pos_data)

            total_pnl = total_value - total_cost_basis if total_value else None

            return json.dumps({
                "success": True,
                "portfolio_id": portfolio_id,
                "name": portfolio_data.get("name"),
                "type": "manual",
                "description": portfolio_data.get("description"),
                "position_count": len(positions),
                "total_value": round(total_value, 2) if total_value else None,
                "total_cost_basis": round(total_cost_basis, 2),
                "total_unrealized_pnl": round(total_pnl, 2) if total_pnl else None,
                "positions": positions
            }, indent=2)

        else:
            # Process synced (SnapTrade) portfolio
            snaptrade_client = get_snaptrade_client()
            user_id, user_secret = _get_snaptrade_credentials()

            try:
                resp = snaptrade_client.account_information.get_user_holdings(
                    account_id=portfolio_id,
                    user_id=user_id,
                    user_secret=user_secret
                )
                holdings = resp.body if hasattr(resp, 'body') else resp
                if hasattr(holdings, 'to_dict'):
                    holdings = holdings.to_dict()

                positions = []
                options = []
                total_value = 0
                total_cost_basis = 0

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
                    snap_price = pos.get("price")
                    avg_cost = pos.get("average_purchase_price")

                    # Get live price
                    live_data = get_live_price(ticker) if ticker else {}
                    price = live_data.get("price") or snap_price
                    price_source = live_data.get("source", "snaptrade")

                    market_value = (units * price) if price and units else None
                    cost_basis = (units * avg_cost) if avg_cost and units else None

                    pnl = None
                    pnl_pct = None
                    if market_value and cost_basis and cost_basis > 0:
                        pnl = market_value - cost_basis
                        pnl_pct = round((pnl / cost_basis) * 100, 2)

                    classification = get_classification(ticker, desc)

                    pos_data = {
                        "symbol": ticker,
                        "description": desc,
                        "consolidated_name": classification.get("name"),
                        "category": classification.get("category"),
                        "units": round(units, 6) if units else 0,
                        "currency": curr,
                        "price": round(price, 4) if price else None,
                        "price_source": price_source,
                        "market_value": round(market_value, 2) if market_value else None,
                        "average_cost": round(avg_cost, 4) if avg_cost else None,
                        "cost_basis": round(cost_basis, 2) if cost_basis else None,
                        "unrealized_pnl": round(pnl, 2) if pnl else None,
                        "unrealized_pnl_pct": pnl_pct,
                    }

                    if market_value:
                        total_value += market_value
                    if cost_basis:
                        total_cost_basis += cost_basis

                    positions.append(pos_data)

                # Process options
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

                    units = opt.get("units") or 0
                    price = opt.get("price")
                    avg_cost = opt.get("average_purchase_price")
                    multiplier = 100 if not opt_sym.get("is_mini_option") else 10

                    market_value = (units * price * multiplier) if price and units else None
                    cost_basis = (units * avg_cost) if avg_cost and units else None

                    pnl = None
                    pnl_pct = None
                    if market_value and cost_basis and cost_basis != 0:
                        pnl = market_value - cost_basis
                        pnl_pct = round((pnl / abs(cost_basis)) * 100, 2)

                    classification = get_classification(underlying.get("symbol"), underlying.get("description"))

                    opt_data = {
                        "type": "option",
                        "ticker": opt_sym.get("ticker"),
                        "underlying": underlying.get("symbol"),
                        "consolidated_name": classification.get("name"),
                        "category": classification.get("category"),
                        "option_type": opt_sym.get("option_type"),
                        "strike_price": opt_sym.get("strike_price"),
                        "expiration_date": opt_sym.get("expiration_date"),
                        "units": units,
                        "multiplier": multiplier,
                        "price": price,
                        "market_value": round(market_value, 2) if market_value else None,
                        "cost_basis": round(cost_basis, 2) if cost_basis else None,
                        "unrealized_pnl": round(pnl, 2) if pnl else None,
                        "unrealized_pnl_pct": pnl_pct,
                    }

                    if market_value:
                        total_value += market_value
                    if cost_basis:
                        total_cost_basis += cost_basis

                    options.append(opt_data)

                total_pnl = total_value - total_cost_basis if total_value and total_cost_basis else None

                return json.dumps({
                    "success": True,
                    "portfolio_id": portfolio_id,
                    "name": portfolio_data.get("name"),
                    "type": "synced",
                    "institution": portfolio_data.get("institution_name"),
                    "position_count": len(positions) + len(options),
                    "total_value": round(total_value, 2) if total_value else None,
                    "total_cost_basis": round(total_cost_basis, 2) if total_cost_basis else None,
                    "total_unrealized_pnl": round(total_pnl, 2) if total_pnl else None,
                    "positions": positions,
                    "options": options if options else None
                }, indent=2)

            except Exception as e:
                return json.dumps({"error": str(e)}, indent=2)

    @server.tool()
    def add_portfolio(
        name: str,
        type: Literal["manual", "synced"],
        description: Optional[str] = None,
        institution: Optional[str] = None,
    ) -> str:
        """
        Add a new portfolio.

        For manual portfolios: Creates an empty portfolio ready for add_position().
        For synced portfolios: Returns an OAuth URL to connect your brokerage.

        Args:
            name: Portfolio name/ID (e.g., "private-equity", "main-trading")
            type: "manual" for user-managed, "synced" for brokerage connection
            description: Optional description (manual only)
            institution: Brokerage name (synced only, e.g., "Interactive Brokers")

        Returns:
            JSON confirming creation or OAuth URL for brokerage connection

        Examples:
            add_portfolio(name="crypto", type="manual", description="Crypto holdings")
            add_portfolio(name="ib-main", type="synced", institution="Interactive Brokers")
        """
        if type == "manual":
            try:
                data = load_portfolios()

                if name in data.get("portfolios", {}):
                    return json.dumps({
                        "error": f"Portfolio '{name}' already exists",
                        "hint": "Use a different name or delete the existing one first"
                    }, indent=2)

                data.setdefault("portfolios", {})[name] = {
                    "name": name,
                    "description": description,
                    "created_at": datetime.utcnow().isoformat() + "Z",
                    "updated_at": datetime.utcnow().isoformat() + "Z",
                    "positions": []
                }

                save_portfolios(data)

                return json.dumps({
                    "success": True,
                    "portfolio_id": name,
                    "type": "manual",
                    "message": f"Portfolio '{name}' created. Use add_position() to add holdings."
                }, indent=2)

            except Exception as e:
                return json.dumps({"error": str(e)}, indent=2)

        else:  # synced
            snaptrade_client = get_snaptrade_client()
            if not snaptrade_client:
                return json.dumps({
                    "error": "SnapTrade not configured",
                    "hint": "Set SNAPTRADE_CONSUMER_KEY and SNAPTRADE_CLIENT_ID environment variables"
                }, indent=2)

            user_id, user_secret = _get_snaptrade_credentials()

            # Auto-register user if needed
            if not user_id or not user_secret:
                return json.dumps({
                    "error": "SnapTrade user not registered",
                    "hint": "Set SNAPTRADE_USER_ID and SNAPTRADE_USER_SECRET environment variables"
                }, indent=2)

            try:
                resp = snaptrade_client.authentication.login_snap_trade_user(
                    user_id=user_id,
                    user_secret=user_secret
                )

                data = resp.body if hasattr(resp, 'body') else resp
                if hasattr(data, 'to_dict'):
                    data = data.to_dict()

                redirect_uri = data.get("redirectURI") if isinstance(data, dict) else getattr(data, 'redirect_uri', None)

                return json.dumps({
                    "success": True,
                    "type": "synced",
                    "oauth_url": redirect_uri,
                    "message": "Open this URL in your browser to connect your brokerage account",
                    "note": "After connecting, the account will appear in list_portfolios()"
                }, indent=2)

            except Exception as e:
                return json.dumps({"error": str(e)}, indent=2)

    @server.tool()
    def delete_portfolio(portfolio_id: str) -> str:
        """
        Delete a portfolio.

        For manual portfolios: Deletes the portfolio and all its positions.
        For synced portfolios: Disconnects the brokerage account.

        WARNING: This is irreversible!

        Args:
            portfolio_id: The portfolio ID (from list_portfolios)

        Returns:
            JSON confirming deletion
        """
        portfolio_type, portfolio_data = _find_portfolio(portfolio_id)

        if portfolio_type is None:
            return json.dumps({
                "error": f"Portfolio '{portfolio_id}' not found",
                "hint": "Use list_portfolios() to see available portfolios"
            }, indent=2)

        if portfolio_type == "manual":
            try:
                data = load_portfolios()

                portfolio_name = data["portfolios"][portfolio_id].get("name")
                positions_count = len(data["portfolios"][portfolio_id].get("positions", []))

                del data["portfolios"][portfolio_id]
                save_portfolios(data)

                return json.dumps({
                    "success": True,
                    "portfolio_id": portfolio_id,
                    "type": "manual",
                    "positions_deleted": positions_count,
                    "message": f"Portfolio '{portfolio_name}' deleted"
                }, indent=2)

            except Exception as e:
                return json.dumps({"error": str(e)}, indent=2)

        else:  # synced
            snaptrade_client = get_snaptrade_client()
            user_id, user_secret = _get_snaptrade_credentials()

            authorization_id = portfolio_data.get("brokerage_authorization")
            if not authorization_id:
                return json.dumps({
                    "error": "Could not find brokerage authorization ID",
                    "hint": "This account may already be disconnected"
                }, indent=2)

            try:
                snaptrade_client.connections.remove_brokerage_authorization(
                    authorization_id=authorization_id,
                    user_id=user_id,
                    user_secret=user_secret
                )

                return json.dumps({
                    "success": True,
                    "portfolio_id": portfolio_id,
                    "type": "synced",
                    "message": f"Brokerage connection disconnected. Account '{portfolio_data.get('name')}' removed."
                }, indent=2)

            except Exception as e:
                return json.dumps({"error": str(e)}, indent=2)

    @server.tool()
    def add_position(
        portfolio_id: str,
        symbol: str,
        units: float,
        average_cost: float,
        currency: str = "USD",
        name: Optional[str] = None,
        manual_price: Optional[float] = None,
        notes: Optional[str] = None,
    ) -> str:
        """
        Add a position to a manual portfolio.

        For pricing, provide either:
        - A Yahoo Finance symbol (e.g., "AAPL") for live prices
        - A manual_price if no ticker exists (e.g., private equity)

        For private equity, use .PVT suffix (e.g., "ANTH.PVT" for Anthropic).

        Args:
            portfolio_id: The manual portfolio ID
            symbol: Ticker symbol (e.g., "AAPL", "ANTH.PVT")
            units: Number of shares/units
            average_cost: Cost per unit
            currency: Currency code (default "USD")
            name: Display name (e.g., "Anthropic Series D")
            manual_price: Manual price override if no ticker
            notes: Optional notes

        Returns:
            JSON confirming position was added

        Note: Only works for manual portfolios. Synced portfolios are read-only.
        """
        portfolio_type, _ = _find_portfolio(portfolio_id)

        if portfolio_type is None:
            return json.dumps({
                "error": f"Portfolio '{portfolio_id}' not found",
                "hint": "Use list_portfolios() to see available portfolios"
            }, indent=2)

        if portfolio_type == "synced":
            return json.dumps({
                "error": "Cannot add positions to synced portfolios",
                "hint": "Synced portfolios are read-only. Positions come from your brokerage."
            }, indent=2)

        try:
            data = load_portfolios()

            position_id = generate_position_id()
            position = {
                "id": position_id,
                "symbol": symbol.upper() if symbol else None,
                "name": name,
                "units": units,
                "average_cost": average_cost,
                "currency": currency.upper(),
                "manual_price": manual_price,
                "notes": notes,
                "created_at": datetime.utcnow().isoformat() + "Z",
                "updated_at": datetime.utcnow().isoformat() + "Z"
            }

            data["portfolios"][portfolio_id]["positions"].append(position)
            data["portfolios"][portfolio_id]["updated_at"] = datetime.utcnow().isoformat() + "Z"

            save_portfolios(data)

            return json.dumps({
                "success": True,
                "portfolio_id": portfolio_id,
                "position_id": position_id,
                "symbol": symbol,
                "message": f"Position added to '{portfolio_id}'"
            }, indent=2)

        except Exception as e:
            return json.dumps({"error": str(e)}, indent=2)

    @server.tool()
    def update_position(
        portfolio_id: str,
        position_id: str,
        units: Optional[float] = None,
        average_cost: Optional[float] = None,
        manual_price: Optional[float] = None,
        name: Optional[str] = None,
        notes: Optional[str] = None,
    ) -> str:
        """
        Update an existing position in a manual portfolio.

        Only provided fields are updated; others remain unchanged.

        Args:
            portfolio_id: The manual portfolio ID
            position_id: The position ID (from get_portfolio)
            units: New number of units
            average_cost: New average cost per unit
            manual_price: New manual price (set to 0 to clear)
            name: New display name
            notes: New notes

        Returns:
            JSON confirming update

        Note: Only works for manual portfolios. Synced portfolios are read-only.
        """
        portfolio_type, _ = _find_portfolio(portfolio_id)

        if portfolio_type is None:
            return json.dumps({
                "error": f"Portfolio '{portfolio_id}' not found"
            }, indent=2)

        if portfolio_type == "synced":
            return json.dumps({
                "error": "Cannot update positions in synced portfolios",
                "hint": "Synced portfolios are read-only. Make changes in your brokerage account."
            }, indent=2)

        try:
            data = load_portfolios()
            portfolio = data["portfolios"][portfolio_id]

            position = None
            for pos in portfolio["positions"]:
                if pos["id"] == position_id:
                    position = pos
                    break

            if position is None:
                return json.dumps({
                    "error": f"Position '{position_id}' not found in portfolio '{portfolio_id}'"
                }, indent=2)

            # Update provided fields
            if units is not None:
                position["units"] = units
            if average_cost is not None:
                position["average_cost"] = average_cost
            if manual_price is not None:
                position["manual_price"] = manual_price if manual_price != 0 else None
            if name is not None:
                position["name"] = name
            if notes is not None:
                position["notes"] = notes

            position["updated_at"] = datetime.utcnow().isoformat() + "Z"
            portfolio["updated_at"] = datetime.utcnow().isoformat() + "Z"

            save_portfolios(data)

            return json.dumps({
                "success": True,
                "portfolio_id": portfolio_id,
                "position_id": position_id,
                "message": "Position updated"
            }, indent=2)

        except Exception as e:
            return json.dumps({"error": str(e)}, indent=2)

    @server.tool()
    def remove_position(
        portfolio_id: str,
        position_id: str
    ) -> str:
        """
        Remove a position from a manual portfolio.

        Args:
            portfolio_id: The manual portfolio ID
            position_id: The position ID to remove

        Returns:
            JSON confirming removal

        Note: Only works for manual portfolios. Synced portfolios are read-only.
        """
        portfolio_type, _ = _find_portfolio(portfolio_id)

        if portfolio_type is None:
            return json.dumps({
                "error": f"Portfolio '{portfolio_id}' not found"
            }, indent=2)

        if portfolio_type == "synced":
            return json.dumps({
                "error": "Cannot remove positions from synced portfolios",
                "hint": "Synced portfolios are read-only. Sell positions in your brokerage account."
            }, indent=2)

        try:
            data = load_portfolios()
            portfolio = data["portfolios"][portfolio_id]

            original_count = len(portfolio["positions"])
            portfolio["positions"] = [p for p in portfolio["positions"] if p["id"] != position_id]

            if len(portfolio["positions"]) == original_count:
                return json.dumps({
                    "error": f"Position '{position_id}' not found in portfolio '{portfolio_id}'"
                }, indent=2)

            portfolio["updated_at"] = datetime.utcnow().isoformat() + "Z"
            save_portfolios(data)

            return json.dumps({
                "success": True,
                "portfolio_id": portfolio_id,
                "position_id": position_id,
                "message": "Position removed"
            }, indent=2)

        except Exception as e:
            return json.dumps({"error": str(e)}, indent=2)

    @server.tool()
    def sync_portfolio(portfolio_id: str) -> str:
        """
        Force sync a synced portfolio from the brokerage.

        SnapTrade syncs once daily by default. Use this to trigger an immediate refresh.
        The refresh is queued asynchronously - data may take a few moments to update.

        Args:
            portfolio_id: The synced portfolio ID

        Returns:
            JSON confirming sync was triggered

        Note: Only works for synced portfolios. Manual portfolios don't need syncing.
        """
        portfolio_type, portfolio_data = _find_portfolio(portfolio_id)

        if portfolio_type is None:
            return json.dumps({
                "error": f"Portfolio '{portfolio_id}' not found"
            }, indent=2)

        if portfolio_type == "manual":
            return json.dumps({
                "error": "Cannot sync manual portfolios",
                "hint": "Manual portfolios don't sync. Use update_position() to make changes."
            }, indent=2)

        snaptrade_client = get_snaptrade_client()
        user_id, user_secret = _get_snaptrade_credentials()

        authorization_id = portfolio_data.get("brokerage_authorization")
        if not authorization_id:
            return json.dumps({
                "error": "Could not find brokerage authorization ID"
            }, indent=2)

        try:
            resp = snaptrade_client.connections.refresh_brokerage_authorization(
                authorization_id=authorization_id,
                user_id=user_id,
                user_secret=user_secret
            )

            return json.dumps({
                "success": True,
                "portfolio_id": portfolio_id,
                "message": "Sync triggered. Holdings will update shortly."
            }, indent=2)

        except Exception as e:
            return json.dumps({"error": str(e)}, indent=2)

    @server.tool()
    def get_transactions(
        portfolio_id: str,
        start_date: str,
        end_date: str,
        transaction_type: Optional[str] = None,
        limit: int = 25,
        offset: int = 0,
    ) -> str:
        """
        Get transaction history for a synced portfolio.

        Returns buys, sells, dividends, deposits, and withdrawals.

        Args:
            portfolio_id: The synced portfolio ID
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (YYYY-MM-DD)
            transaction_type: Filter by type (e.g., "BUY", "SELL", "DIVIDEND")
            limit: Max transactions to return (default 25, max 100)
            offset: Skip N transactions for pagination

        Returns:
            JSON with transaction history

        Note: Only available for synced portfolios.
        """
        portfolio_type, _ = _find_portfolio(portfolio_id)

        if portfolio_type is None:
            return json.dumps({
                "error": f"Portfolio '{portfolio_id}' not found"
            }, indent=2)

        if portfolio_type == "manual":
            return json.dumps({
                "error": "Transaction history not available for manual portfolios",
                "hint": "Manual portfolios don't track transactions. Only synced portfolios have transaction history."
            }, indent=2)

        snaptrade_client = get_snaptrade_client()
        user_id, user_secret = _get_snaptrade_credentials()

        try:
            limit = min(limit, 100)

            params = {
                "account_id": portfolio_id,
                "user_id": user_id,
                "user_secret": user_secret,
                "start_date": start_date,
                "end_date": end_date
            }

            if transaction_type:
                params["type"] = transaction_type

            resp = snaptrade_client.account_information.get_account_activities(**params)
            activities = resp.body if hasattr(resp, 'body') else resp

            # Extract list from response
            if isinstance(activities, dict):
                activities = activities.get("data", [])

            total_count = len(activities)
            paginated = activities[offset:offset + limit]

            # Format transactions
            transactions = []
            for a in paginated:
                if hasattr(a, 'to_dict'):
                    a = a.to_dict()
                elif hasattr(a, '__dict__'):
                    a = vars(a)

                def safe_get(obj, key, default=None):
                    if obj is None:
                        return default
                    if hasattr(obj, 'get'):
                        return obj.get(key, default)
                    return getattr(obj, key, default)

                symbol_obj = safe_get(a, "symbol")
                symbol = safe_get(symbol_obj, "symbol") if symbol_obj else None

                transactions.append({
                    "id": safe_get(a, "id"),
                    "type": safe_get(a, "type"),
                    "symbol": symbol,
                    "description": safe_get(a, "description"),
                    "trade_date": str(safe_get(a, "trade_date")) if safe_get(a, "trade_date") else None,
                    "units": float(safe_get(a, "units")) if safe_get(a, "units") else None,
                    "price": float(safe_get(a, "price")) if safe_get(a, "price") else None,
                    "amount": float(safe_get(a, "amount")) if safe_get(a, "amount") else None,
                    "fee": float(safe_get(a, "fee")) if safe_get(a, "fee") else None,
                })

            return json.dumps({
                "success": True,
                "portfolio_id": portfolio_id,
                "showing": len(transactions),
                "total_available": total_count,
                "pagination": {
                    "offset": offset,
                    "limit": limit,
                    "has_more": (offset + limit) < total_count
                },
                "transactions": transactions
            }, indent=2)

        except Exception as e:
            return json.dumps({"error": str(e)}, indent=2)

    # =========================================================================
    # Classification Tools
    # =========================================================================

    @server.tool()
    def list_categories() -> str:
        """
        List all available categories for classifying holdings.

        Categories are used to group holdings by investment theme/sector.
        Use update_classification() to change a holding's category.

        Returns:
            JSON with list of categories
        """
        categories = get_known_categories()
        return json.dumps({
            "success": True,
            "count": len(categories),
            "categories": categories
        }, indent=2)

    @server.tool()
    def list_classifications(
        category: Optional[str] = None
    ) -> str:
        """
        List all symbol classifications (name and category mappings).

        Shows how symbols are grouped and categorized. Use update_classification()
        to change any mapping.

        Args:
            category: Optional filter by category (e.g., "Technology", "Commodities")

        Returns:
            JSON with all classifications
        """
        data = get_all_classifications()
        tickers = data.get("tickers", {})

        # Filter by category if specified
        if category:
            tickers = {
                symbol: info
                for symbol, info in tickers.items()
                if info.get("category", "").lower() == category.lower()
            }

        # Sort by category then name
        sorted_tickers = dict(sorted(
            tickers.items(),
            key=lambda x: (x[1].get("category", ""), x[1].get("name", ""))
        ))

        return json.dumps({
            "success": True,
            "categories": data.get("categories", []),
            "count": len(sorted_tickers),
            "filter": category,
            "classifications": sorted_tickers
        }, indent=2)

    @server.tool()
    def update_classifications(
        updates: list[dict]
    ) -> str:
        """
        Update classifications (name and/or category) for one or more symbols.

        This overrides AI-generated classifications. Use this to:
        - Group related tickers under a common name (e.g., GOOG + GOOGL -> "Google")
        - Change a holding's category (e.g., IREN from "Crypto" to "AI Infrastructure")
        - Batch update multiple symbols at once

        Args:
            updates: List of updates, each with: symbol (required), name (optional), category (optional)

        Returns:
            JSON with results for each update

        Examples:
            update_classifications(updates=[{"symbol": "IREN", "category": "AI Infrastructure"}])
            update_classifications(updates=[
                {"symbol": "GOOG", "name": "Google", "category": "Technology"},
                {"symbol": "GOOGL", "name": "Google", "category": "Technology"}
            ])
        """
        if not updates:
            return json.dumps({"error": "No updates provided"}, indent=2)

        available_categories = get_known_categories()
        results = []
        new_categories = set()

        for update in updates:
            symbol = update.get("symbol")
            name = update.get("name")
            category = update.get("category")

            if not symbol:
                results.append({"error": "Missing symbol", "update": update})
                continue

            if not name and not category:
                results.append({
                    "error": "Must provide at least one of: name, category",
                    "symbol": symbol
                })
                continue

            result = _update_classification(symbol, name, category)

            if result.get("success"):
                entry = {
                    "success": True,
                    "symbol": result["symbol"],
                    "name": result["name"],
                    "category": result["category"]
                }
                if category and category not in available_categories:
                    new_categories.add(category)
                results.append(entry)
            else:
                results.append({"success": False, "symbol": symbol, "error": result.get("error")})

        response = {
            "updated": len([r for r in results if r.get("success")]),
            "failed": len([r for r in results if not r.get("success")]),
            "results": results
        }

        if new_categories:
            response["new_categories"] = list(new_categories)

        return json.dumps(response, indent=2)

    @server.tool()
    def add_categories(categories: list[str]) -> str:
        """
        Add one or more new categories to the available categories list.

        Categories are used to group holdings by investment theme/sector.
        New categories are also automatically created when using update_classifications().

        Args:
            categories: List of category names (e.g., ["AI Infrastructure", "Defense"])

        Returns:
            JSON confirming which categories were added

        Examples:
            add_categories(categories=["AI Infrastructure"])
            add_categories(categories=["Defense", "Space", "Biotech"])
        """
        if not categories:
            return json.dumps({"error": "No categories provided"}, indent=2)

        existing = get_known_categories()
        added = []
        already_existed = []
        failed = []

        for category in categories:
            if not category or not isinstance(category, str):
                failed.append({"category": category, "error": "Invalid category"})
                continue

            category = category.strip()
            if category in existing:
                already_existed.append(category)
            elif _add_category(category):
                added.append(category)
                existing.append(category)  # Update local list
            else:
                failed.append({"category": category, "error": "Failed to add"})

        return json.dumps({
            "added": added,
            "already_existed": already_existed,
            "failed": failed,
            "all_categories": get_known_categories()
        }, indent=2)
