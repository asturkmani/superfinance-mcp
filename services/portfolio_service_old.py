"""Portfolio service - manual portfolio management."""

from datetime import datetime
from typing import Optional

from helpers.portfolio import load_portfolios, save_portfolios, generate_position_id
from helpers.pricing import get_live_price, get_fx_rate_cached


class PortfolioService:
    """Service class for manual portfolio operations."""

    @staticmethod
    async def create_portfolio(
        portfolio_id: str,
        name: str,
        description: Optional[str] = None
    ) -> dict:
        """
        Create a new manual portfolio.

        Args:
            portfolio_id: Unique identifier
            name: Display name
            description: Optional description

        Returns:
            dict confirming creation
        """
        try:
            data = load_portfolios()

            if portfolio_id in data["portfolios"]:
                return {
                    "error": f"Portfolio '{portfolio_id}' already exists",
                    "message": "Use a different ID or delete the existing one"
                }

            data["portfolios"][portfolio_id] = {
                "name": name,
                "description": description,
                "created_at": datetime.utcnow().isoformat() + "Z",
                "updated_at": datetime.utcnow().isoformat() + "Z",
                "positions": []
            }

            save_portfolios(data)

            return {
                "success": True,
                "portfolio_id": portfolio_id,
                "name": name,
                "message": f"Portfolio '{name}' created"
            }
        except Exception as e:
            return {"error": str(e)}

    @staticmethod
    async def add_position(
        portfolio_id: str,
        name: str,
        units: float,
        average_cost: float,
        currency: str = "USD",
        symbol: Optional[str] = None,
        manual_price: Optional[float] = None,
        asset_type: Optional[str] = None,
        notes: Optional[str] = None
    ) -> dict:
        """
        Add a position to a portfolio.

        Args:
            portfolio_id: Target portfolio
            name: Position display name
            units: Number of units
            average_cost: Cost per unit
            currency: Currency code
            symbol: Optional Yahoo Finance ticker
            manual_price: Optional manual price
            asset_type: Optional category
            notes: Optional notes

        Returns:
            dict with position details
        """
        try:
            data = load_portfolios()

            if portfolio_id not in data["portfolios"]:
                return {
                    "error": f"Portfolio '{portfolio_id}' not found",
                    "message": "Create the portfolio first"
                }

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

            return {
                "success": True,
                "portfolio_id": portfolio_id,
                "position_id": position_id,
                "position": position
            }
        except Exception as e:
            return {"error": str(e)}

    @staticmethod
    async def update_position(
        portfolio_id: str,
        position_id: str,
        units: Optional[float] = None,
        average_cost: Optional[float] = None,
        manual_price: Optional[float] = None,
        symbol: Optional[str] = None,
        name: Optional[str] = None,
        notes: Optional[str] = None
    ) -> dict:
        """
        Update a position in a portfolio.

        Args:
            portfolio_id: Target portfolio
            position_id: Position to update
            units: New units (optional)
            average_cost: New cost (optional)
            manual_price: New manual price (optional)
            symbol: New symbol (optional)
            name: New name (optional)
            notes: New notes (optional)

        Returns:
            dict with updated position
        """
        try:
            data = load_portfolios()

            if portfolio_id not in data["portfolios"]:
                return {"error": f"Portfolio '{portfolio_id}' not found"}

            portfolio = data["portfolios"][portfolio_id]
            position = None

            for i, pos in enumerate(portfolio["positions"]):
                if pos["id"] == position_id:
                    position = pos
                    break

            if position is None:
                return {"error": f"Position '{position_id}' not found"}

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

            return {
                "success": True,
                "portfolio_id": portfolio_id,
                "position_id": position_id,
                "position": position
            }
        except Exception as e:
            return {"error": str(e)}

    @staticmethod
    async def remove_position(portfolio_id: str, position_id: str) -> dict:
        """
        Remove a position from a portfolio.

        Args:
            portfolio_id: Target portfolio
            position_id: Position to remove

        Returns:
            dict confirming removal
        """
        try:
            data = load_portfolios()

            if portfolio_id not in data["portfolios"]:
                return {"error": f"Portfolio '{portfolio_id}' not found"}

            portfolio = data["portfolios"][portfolio_id]
            original_count = len(portfolio["positions"])

            portfolio["positions"] = [
                p for p in portfolio["positions"] if p["id"] != position_id
            ]

            if len(portfolio["positions"]) == original_count:
                return {"error": f"Position '{position_id}' not found"}

            portfolio["updated_at"] = datetime.utcnow().isoformat() + "Z"
            save_portfolios(data)

            return {
                "success": True,
                "portfolio_id": portfolio_id,
                "position_id": position_id,
                "message": "Position removed"
            }
        except Exception as e:
            return {"error": str(e)}

    @staticmethod
    async def delete_portfolio(portfolio_id: str) -> dict:
        """
        Delete a portfolio and all positions.

        Args:
            portfolio_id: Portfolio to delete

        Returns:
            dict confirming deletion
        """
        try:
            data = load_portfolios()

            if portfolio_id not in data["portfolios"]:
                return {"error": f"Portfolio '{portfolio_id}' not found"}

            portfolio_name = data["portfolios"][portfolio_id]["name"]
            positions_count = len(data["portfolios"][portfolio_id]["positions"])

            del data["portfolios"][portfolio_id]
            save_portfolios(data)

            return {
                "success": True,
                "portfolio_id": portfolio_id,
                "name": portfolio_name,
                "positions_deleted": positions_count
            }
        except Exception as e:
            return {"error": str(e)}

    @staticmethod
    async def list_portfolios() -> dict:
        """
        List all portfolios with summaries.

        Returns:
            dict with portfolio summaries
        """
        try:
            data = load_portfolios()

            summaries = []
            for pid, portfolio in data["portfolios"].items():
                total_cost = sum(
                    p["units"] * p["average_cost"]
                    for p in portfolio["positions"]
                )

                summaries.append({
                    "portfolio_id": pid,
                    "name": portfolio["name"],
                    "description": portfolio.get("description"),
                    "positions_count": len(portfolio["positions"]),
                    "total_cost_basis": round(total_cost, 2),
                    "created_at": portfolio.get("created_at"),
                    "updated_at": portfolio.get("updated_at")
                })

            return {
                "success": True,
                "count": len(summaries),
                "portfolios": summaries
            }
        except Exception as e:
            return {"error": str(e)}

    @staticmethod
    async def get_portfolio(
        portfolio_id: str,
        target_currency: Optional[str] = None
    ) -> dict:
        """
        Get a portfolio with live prices.

        Args:
            portfolio_id: Portfolio to retrieve
            target_currency: Optional currency for conversion

        Returns:
            dict with portfolio and live prices
        """
        try:
            data = load_portfolios()

            if portfolio_id not in data["portfolios"]:
                return {"error": f"Portfolio '{portfolio_id}' not found"}

            portfolio = data["portfolios"][portfolio_id]

            fx_cache = {}
            fx_rates_used = {}

            positions = []
            total_market_value = 0.0
            total_cost_basis = 0.0
            total_converted = 0.0

            for pos in portfolio["positions"]:
                symbol = pos.get("symbol")
                units = pos.get("units", 0)
                avg_cost = pos.get("average_cost", 0)
                pos_currency = pos.get("currency", "USD")
                manual_price = pos.get("manual_price")

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

                cost_basis = units * avg_cost if units and avg_cost else 0
                market_value = units * live_price if units and live_price else None

                pnl = None
                pnl_pct = None
                if market_value is not None and cost_basis > 0:
                    pnl = market_value - cost_basis
                    pnl_pct = round((pnl / cost_basis) * 100, 2)

                pos_data = {
                    "id": pos.get("id"),
                    "name": pos.get("name"),
                    "symbol": symbol,
                    "units": units,
                    "currency": pos_currency,
                    "live_price": round(live_price, 2) if live_price else None,
                    "price_source": price_source,
                    "market_value": round(market_value, 2) if market_value else None,
                    "average_cost": avg_cost,
                    "cost_basis": round(cost_basis, 2) if cost_basis else None,
                    "unrealized_pnl": round(pnl, 2) if pnl else None,
                    "unrealized_pnl_pct": pnl_pct,
                    "asset_type": pos.get("asset_type"),
                    "notes": pos.get("notes")
                }

                if market_value:
                    total_market_value += market_value
                total_cost_basis += cost_basis

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
                            "unrealized_pnl": round(pnl * fx_rate, 2) if pnl else None,
                            "unrealized_pnl_pct": pnl_pct
                        }
                        if market_value:
                            total_converted += market_value * fx_rate
                elif target_currency and pos_currency == target_currency:
                    if market_value:
                        total_converted += market_value

                positions.append(pos_data)

            total_pnl = total_market_value - total_cost_basis if total_market_value else None
            total_pnl_pct = None
            if total_pnl is not None and total_cost_basis > 0:
                total_pnl_pct = round((total_pnl / total_cost_basis) * 100, 2)

            result = {
                "success": True,
                "portfolio_id": portfolio_id,
                "name": portfolio["name"],
                "description": portfolio.get("description"),
                "positions_count": len(positions),
                "positions": positions,
                "total_market_value": round(total_market_value, 2) if total_market_value else None,
                "total_cost_basis": round(total_cost_basis, 2),
                "total_unrealized_pnl": round(total_pnl, 2) if total_pnl else None,
                "total_unrealized_pnl_pct": total_pnl_pct,
                "updated_at": portfolio.get("updated_at")
            }

            if target_currency:
                result["target_currency"] = target_currency
                result["fx_rates_used"] = fx_rates_used
                result["total_market_value_converted"] = {
                    target_currency: round(total_converted, 2)
                } if total_converted else None

            return result
        except Exception as e:
            return {"error": str(e)}
