"""Manual portfolio tools for tracking private investments."""

import json
from datetime import datetime
from typing import Optional

from helpers.portfolio import load_portfolios, save_portfolios, generate_position_id
from helpers.pricing import get_live_price, get_fx_rate_cached


def register_manual_portfolio_tools(server):
    """Register all manual portfolio tools with the server."""

    @server.tool()
    def manual_create_portfolio(
        portfolio_id: str,
        name: str,
        description: Optional[str] = None
    ) -> str:
        """
        Create a new manual portfolio for tracking private investments.

        Use this for investments not connected through SnapTrade, such as:
        - Private equity (SpaceX, Stripe, etc.)
        - Real estate investments
        - Angel investments
        - Other alternative assets

        Args:
            portfolio_id: Unique identifier for the portfolio (e.g., "private-equity", "real-estate")
            name: Display name for the portfolio (e.g., "Private Equity Holdings")
            description: Optional description of the portfolio

        Returns:
            JSON string confirming portfolio creation
        """
        try:
            data = load_portfolios()

            if portfolio_id in data["portfolios"]:
                return json.dumps({
                    "error": f"Portfolio '{portfolio_id}' already exists",
                    "message": "Use a different portfolio_id or delete the existing one first"
                }, indent=2)

            data["portfolios"][portfolio_id] = {
                "name": name,
                "description": description,
                "created_at": datetime.utcnow().isoformat() + "Z",
                "updated_at": datetime.utcnow().isoformat() + "Z",
                "positions": []
            }

            save_portfolios(data)

            return json.dumps({
                "success": True,
                "portfolio_id": portfolio_id,
                "name": name,
                "message": f"Portfolio '{name}' created successfully"
            }, indent=2)

        except Exception as e:
            return json.dumps({
                "error": str(e)
            }, indent=2)

    @server.tool()
    def manual_add_position(
        portfolio_id: str,
        name: str,
        units: float,
        average_cost: float,
        currency: str = "USD",
        symbol: Optional[str] = None,
        manual_price: Optional[float] = None,
        asset_type: Optional[str] = None,
        notes: Optional[str] = None
    ) -> str:
        """
        Add a position to a manual portfolio.

        For pricing, you can specify:
        - A Yahoo Finance symbol (e.g., "STRB" for SpaceX exposure) for live prices
        - A manual_price if there's no ticker available

        Args:
            portfolio_id: The portfolio to add the position to
            name: Display name for the position (e.g., "SpaceX Series J")
            units: Number of shares/units held
            average_cost: Average cost per unit in the specified currency
            currency: Currency code (e.g., "USD", "GBP", "EUR"). Default: "USD"
            symbol: Optional Yahoo Finance ticker symbol for live pricing
            manual_price: Optional manual price if no ticker is available
            asset_type: Optional category (e.g., "private_equity", "real_estate", "crypto")
            notes: Optional notes about the position

        Returns:
            JSON string confirming position was added
        """
        try:
            data = load_portfolios()

            if portfolio_id not in data["portfolios"]:
                return json.dumps({
                    "error": f"Portfolio '{portfolio_id}' not found",
                    "message": "Create the portfolio first using manual_create_portfolio"
                }, indent=2)

            position_id = generate_position_id()

            position = {
                "id": position_id,
                "name": name,
                "symbol": symbol,
                "units": units,
                "average_cost": average_cost,
                "currency": currency.upper(),
                "manual_price": manual_price,
                "asset_type": asset_type,
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
                "position": position,
                "message": f"Position '{name}' added to portfolio '{portfolio_id}'"
            }, indent=2)

        except Exception as e:
            return json.dumps({
                "error": str(e)
            }, indent=2)

    @server.tool()
    def manual_update_position(
        portfolio_id: str,
        position_id: str,
        units: Optional[float] = None,
        average_cost: Optional[float] = None,
        manual_price: Optional[float] = None,
        symbol: Optional[str] = None,
        name: Optional[str] = None,
        notes: Optional[str] = None
    ) -> str:
        """
        Update an existing position in a manual portfolio.

        Only the fields you provide will be updated; others remain unchanged.

        Args:
            portfolio_id: The portfolio containing the position
            position_id: The ID of the position to update (from manual_add_position)
            units: New number of units (optional)
            average_cost: New average cost per unit (optional)
            manual_price: New manual price override (optional, set to 0 to clear)
            symbol: New Yahoo Finance symbol (optional, set to empty string to clear)
            name: New display name (optional)
            notes: New notes (optional)

        Returns:
            JSON string confirming the update
        """
        try:
            data = load_portfolios()

            if portfolio_id not in data["portfolios"]:
                return json.dumps({
                    "error": f"Portfolio '{portfolio_id}' not found"
                }, indent=2)

            portfolio = data["portfolios"][portfolio_id]
            position = None
            position_index = None

            for i, pos in enumerate(portfolio["positions"]):
                if pos["id"] == position_id:
                    position = pos
                    position_index = i
                    break

            if position is None:
                return json.dumps({
                    "error": f"Position '{position_id}' not found in portfolio '{portfolio_id}'"
                }, indent=2)

            # Update only provided fields
            if units is not None:
                position["units"] = units
            if average_cost is not None:
                position["average_cost"] = average_cost
            if manual_price is not None:
                position["manual_price"] = manual_price if manual_price != 0 else None
            if symbol is not None:
                position["symbol"] = symbol if symbol else None
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
                "position": position,
                "message": f"Position '{position['name']}' updated"
            }, indent=2)

        except Exception as e:
            return json.dumps({
                "error": str(e)
            }, indent=2)

    @server.tool()
    def manual_remove_position(
        portfolio_id: str,
        position_id: str
    ) -> str:
        """
        Remove a position from a manual portfolio.

        Args:
            portfolio_id: The portfolio containing the position
            position_id: The ID of the position to remove

        Returns:
            JSON string confirming removal
        """
        try:
            data = load_portfolios()

            if portfolio_id not in data["portfolios"]:
                return json.dumps({
                    "error": f"Portfolio '{portfolio_id}' not found"
                }, indent=2)

            portfolio = data["portfolios"][portfolio_id]
            original_count = len(portfolio["positions"])

            portfolio["positions"] = [
                p for p in portfolio["positions"] if p["id"] != position_id
            ]

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
                "message": f"Position removed from portfolio '{portfolio_id}'"
            }, indent=2)

        except Exception as e:
            return json.dumps({
                "error": str(e)
            }, indent=2)

    @server.tool()
    def manual_delete_portfolio(
        portfolio_id: str
    ) -> str:
        """
        Delete an entire manual portfolio and all its positions.

        WARNING: This is irreversible! All positions in the portfolio will be deleted.

        Args:
            portfolio_id: The portfolio to delete

        Returns:
            JSON string confirming deletion
        """
        try:
            data = load_portfolios()

            if portfolio_id not in data["portfolios"]:
                return json.dumps({
                    "error": f"Portfolio '{portfolio_id}' not found"
                }, indent=2)

            portfolio_name = data["portfolios"][portfolio_id]["name"]
            positions_count = len(data["portfolios"][portfolio_id]["positions"])

            del data["portfolios"][portfolio_id]
            save_portfolios(data)

            return json.dumps({
                "success": True,
                "portfolio_id": portfolio_id,
                "name": portfolio_name,
                "positions_deleted": positions_count,
                "message": f"Portfolio '{portfolio_name}' and all its positions have been deleted"
            }, indent=2)

        except Exception as e:
            return json.dumps({
                "error": str(e)
            }, indent=2)

    @server.tool()
    def manual_list_portfolios() -> str:
        """
        List all manual portfolios with summary information.

        Returns a summary of each portfolio including name, position count, and last updated time.
        Use manual_get_portfolio to get full details with live prices.

        Returns:
            JSON string containing portfolio summaries
        """
        try:
            data = load_portfolios()

            portfolios_summary = []
            for portfolio_id, portfolio in data["portfolios"].items():
                # Calculate total cost basis
                total_cost_basis = sum(
                    p["units"] * p["average_cost"]
                    for p in portfolio["positions"]
                )

                portfolios_summary.append({
                    "portfolio_id": portfolio_id,
                    "name": portfolio["name"],
                    "description": portfolio.get("description"),
                    "positions_count": len(portfolio["positions"]),
                    "total_cost_basis": round(total_cost_basis, 2),
                    "created_at": portfolio.get("created_at"),
                    "updated_at": portfolio.get("updated_at")
                })

            return json.dumps({
                "success": True,
                "portfolios_count": len(portfolios_summary),
                "portfolios": portfolios_summary
            }, indent=2)

        except Exception as e:
            return json.dumps({
                "error": str(e)
            }, indent=2)

    @server.tool()
    def manual_get_portfolio(
        portfolio_id: str,
        target_currency: Optional[str] = None
    ) -> str:
        """
        Get a manual portfolio with live prices from Yahoo Finance.

        Fetches current prices for positions that have a Yahoo Finance symbol,
        and uses manual_price for positions without a symbol. Calculates market
        values, unrealized P&L, and optionally converts to a target currency.

        For private companies like SpaceX, you can use secondary market tickers:
        - STRB (Starbase) - provides exposure to SpaceX
        - Or set manual_price for positions without a ticker

        Args:
            portfolio_id: The portfolio to retrieve
            target_currency: Optional currency to convert all values to (e.g., "GBP", "EUR")

        Returns:
            JSON string containing portfolio with live prices and calculated P&L
        """
        try:
            data = load_portfolios()

            if portfolio_id not in data["portfolios"]:
                return json.dumps({
                    "error": f"Portfolio '{portfolio_id}' not found"
                }, indent=2)

            portfolio = data["portfolios"][portfolio_id]

            # FX rate cache
            fx_cache = {}
            fx_rates_used = {}

            positions_with_prices = []
            total_market_value = 0.0
            total_cost_basis = 0.0
            total_market_value_converted = 0.0

            for pos in portfolio["positions"]:
                symbol = pos.get("symbol")
                units = pos.get("units", 0)
                average_cost = pos.get("average_cost", 0)
                pos_currency = pos.get("currency", "USD")
                manual_price = pos.get("manual_price")

                # Get price: try Yahoo Finance first, then manual_price
                live_price = None
                price_source = "none"

                if symbol:
                    live_data = get_live_price(symbol)
                    if live_data.get("price") is not None:
                        live_price = live_data["price"]
                        price_source = "yahoo_finance"

                if live_price is None and manual_price is not None:
                    live_price = manual_price
                    price_source = "manual"

                # Calculate values
                cost_basis = units * average_cost if units and average_cost else 0
                market_value = units * live_price if units and live_price else None

                unrealized_pnl = None
                unrealized_pnl_pct = None
                if market_value is not None and cost_basis > 0:
                    unrealized_pnl = market_value - cost_basis
                    unrealized_pnl_pct = round((unrealized_pnl / cost_basis) * 100, 2)

                pos_data = {
                    "id": pos.get("id"),
                    "name": pos.get("name"),
                    "symbol": symbol,
                    "units": units,
                    "currency": pos_currency,
                    "live_price": round(live_price, 2) if live_price else None,
                    "price_source": price_source,
                    "market_value": round(market_value, 2) if market_value else None,
                    "average_cost": average_cost,
                    "cost_basis": round(cost_basis, 2) if cost_basis else None,
                    "unrealized_pnl": round(unrealized_pnl, 2) if unrealized_pnl else None,
                    "unrealized_pnl_pct": unrealized_pnl_pct,
                    "asset_type": pos.get("asset_type"),
                    "notes": pos.get("notes")
                }

                # Track totals
                if market_value:
                    total_market_value += market_value
                total_cost_basis += cost_basis

                # Currency conversion if target_currency specified
                if target_currency and pos_currency != target_currency:
                    fx_rate = get_fx_rate_cached(pos_currency, target_currency, fx_cache)
                    if fx_rate:
                        fx_key = f"{pos_currency}_{target_currency}"
                        fx_rates_used[fx_key] = fx_rate

                        pos_data["converted"] = {
                            "currency": target_currency,
                            "fx_rate": fx_rate,
                            "live_price": round(live_price * fx_rate, 2) if live_price else None,
                            "market_value": round(market_value * fx_rate, 2) if market_value else None,
                            "cost_basis": round(cost_basis * fx_rate, 2) if cost_basis else None,
                            "unrealized_pnl": round(unrealized_pnl * fx_rate, 2) if unrealized_pnl else None,
                            "unrealized_pnl_pct": unrealized_pnl_pct
                        }
                        if market_value:
                            total_market_value_converted += market_value * fx_rate
                elif target_currency and pos_currency == target_currency:
                    if market_value:
                        total_market_value_converted += market_value

                positions_with_prices.append(pos_data)

            # Calculate total P&L
            total_unrealized_pnl = total_market_value - total_cost_basis if total_market_value else None
            total_unrealized_pnl_pct = None
            if total_unrealized_pnl is not None and total_cost_basis > 0:
                total_unrealized_pnl_pct = round((total_unrealized_pnl / total_cost_basis) * 100, 2)

            result = {
                "success": True,
                "portfolio_id": portfolio_id,
                "name": portfolio["name"],
                "description": portfolio.get("description"),
                "positions_count": len(positions_with_prices),
                "positions": positions_with_prices,
                "total_market_value": round(total_market_value, 2) if total_market_value else None,
                "total_cost_basis": round(total_cost_basis, 2),
                "total_unrealized_pnl": round(total_unrealized_pnl, 2) if total_unrealized_pnl else None,
                "total_unrealized_pnl_pct": total_unrealized_pnl_pct,
                "updated_at": portfolio.get("updated_at")
            }

            if target_currency:
                result["target_currency"] = target_currency
                result["fx_rates_used"] = fx_rates_used
                result["total_market_value_converted"] = {
                    target_currency: round(total_market_value_converted, 2)
                } if total_market_value_converted else None
                result["fx_note"] = "Cost basis converted using current FX rate, not historical rate from purchase date"

            return json.dumps(result, indent=2)

        except Exception as e:
            return json.dumps({
                "error": str(e)
            }, indent=2)
