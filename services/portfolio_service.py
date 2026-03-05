"""Portfolio service - manual portfolio management with SQLite backend."""

from datetime import datetime
from typing import Optional

from db import queries
from helpers.pricing import get_live_price, get_fx_rate_cached


class PortfolioService:
    """Service class for manual portfolio operations."""

    @staticmethod
    async def create_portfolio(
        user_id: str,
        portfolio_id: str,
        name: str,
        description: Optional[str] = None
    ) -> dict:
        """
        Create a new manual portfolio (account).

        Args:
            user_id: User ID
            portfolio_id: Unique identifier for the portfolio
            name: Display name
            description: Optional description

        Returns:
            dict confirming creation
        """
        try:
            # Check if account with this ID already exists
            existing = queries.get_account(portfolio_id)
            if existing:
                return {
                    "error": f"Portfolio '{portfolio_id}' already exists",
                    "message": "Use a different ID or delete the existing one"
                }

            # Create account
            account_id = queries.create_account(
                user_id=user_id,
                name=name,
                account_type=description if description else None,
                currency="USD",
                is_manual=True
            )

            # Override the generated ID with the provided portfolio_id
            # This maintains backward compatibility with the old JSON-based system
            from db.database import get_db
            conn = get_db()
            cursor = conn.cursor()
            cursor.execute("UPDATE accounts SET id = ? WHERE id = ?", (portfolio_id, account_id))
            conn.commit()

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
        user_id: str,
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
            user_id: User ID (for validation)
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
            # Verify account exists and belongs to user
            account = queries.get_account(portfolio_id)
            if not account:
                return {
                    "error": f"Portfolio '{portfolio_id}' not found",
                    "message": "Create the portfolio first"
                }

            if account['user_id'] != user_id:
                return {
                    "error": "Access denied",
                    "message": "This portfolio belongs to another user"
                }

            # Calculate market value
            market_value = None
            if manual_price is not None:
                market_value = units * manual_price

            # Create holding
            holding_id = queries.upsert_holding(
                account_id=portfolio_id,
                symbol=symbol or name,  # Use name as symbol if no symbol provided
                name=name,
                quantity=units,
                average_cost=average_cost,
                current_price=manual_price,
                market_value=market_value,
                currency=currency.upper(),
                asset_type=asset_type,
                metadata={"notes": notes} if notes else None
            )

            # Get the created holding
            from db.database import get_db
            conn = get_db()
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM holdings WHERE id = ?", (holding_id,))
            holding = dict(cursor.fetchone())

            return {
                "success": True,
                "portfolio_id": portfolio_id,
                "position_id": holding_id,
                "position": {
                    "id": holding['id'],
                    "name": holding['name'],
                    "symbol": holding['symbol'],
                    "units": holding['quantity'],
                    "average_cost": holding['average_cost'],
                    "currency": holding['currency'],
                    "manual_price": holding['current_price'],
                    "asset_type": holding['asset_type'],
                    "notes": notes,
                    "created_at": holding['created_at'],
                    "updated_at": holding['updated_at']
                }
            }
        except Exception as e:
            return {"error": str(e)}

    @staticmethod
    async def update_position(
        user_id: str,
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
            user_id: User ID (for validation)
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
            # Verify account exists and belongs to user
            account = queries.get_account(portfolio_id)
            if not account:
                return {"error": f"Portfolio '{portfolio_id}' not found"}

            if account['user_id'] != user_id:
                return {"error": "Access denied"}

            # Get current holding
            from db.database import get_db
            conn = get_db()
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM holdings WHERE id = ? AND account_id = ?", 
                         (position_id, portfolio_id))
            holding = cursor.fetchone()

            if not holding:
                return {"error": f"Position '{position_id}' not found"}

            holding = dict(holding)

            # Build update parameters
            updates = {}
            if name is not None:
                updates['name'] = name
            if units is not None:
                updates['quantity'] = units
            if average_cost is not None:
                updates['average_cost'] = average_cost
            if manual_price is not None:
                updates['current_price'] = manual_price if manual_price != 0 else None
            if symbol is not None:
                # Can't update symbol directly since it's part of upsert key
                # Instead update via SQL
                cursor.execute("UPDATE holdings SET symbol = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?", 
                             (symbol, position_id))

            # Calculate new market value if needed
            quantity = updates.get('quantity', holding['quantity'])
            price = updates.get('current_price', holding['current_price'])
            if quantity and price:
                updates['market_value'] = quantity * price

            # Update holding
            if updates:
                # Build SQL update
                set_clauses = [f"{k} = ?" for k in updates.keys()]
                set_clauses.append("updated_at = CURRENT_TIMESTAMP")
                values = list(updates.values()) + [position_id]

                cursor.execute(
                    f"UPDATE holdings SET {', '.join(set_clauses)} WHERE id = ?",
                    values
                )
                conn.commit()

            # Get updated holding
            cursor.execute("SELECT * FROM holdings WHERE id = ?", (position_id,))
            updated = dict(cursor.fetchone())

            return {
                "success": True,
                "portfolio_id": portfolio_id,
                "position_id": position_id,
                "position": {
                    "id": updated['id'],
                    "name": updated['name'],
                    "symbol": updated['symbol'],
                    "units": updated['quantity'],
                    "average_cost": updated['average_cost'],
                    "currency": updated['currency'],
                    "manual_price": updated['current_price'],
                    "asset_type": updated['asset_type'],
                    "updated_at": updated['updated_at']
                }
            }
        except Exception as e:
            return {"error": str(e)}

    @staticmethod
    async def remove_position(user_id: str, portfolio_id: str, position_id: str) -> dict:
        """
        Remove a position from a portfolio.

        Args:
            user_id: User ID (for validation)
            portfolio_id: Target portfolio
            position_id: Position to remove

        Returns:
            dict confirming removal
        """
        try:
            # Verify account exists and belongs to user
            account = queries.get_account(portfolio_id)
            if not account:
                return {"error": f"Portfolio '{portfolio_id}' not found"}

            if account['user_id'] != user_id:
                return {"error": "Access denied"}

            # Delete holding
            deleted = queries.delete_holding(position_id)

            if not deleted:
                return {"error": f"Position '{position_id}' not found"}

            return {
                "success": True,
                "portfolio_id": portfolio_id,
                "position_id": position_id,
                "message": "Position removed"
            }
        except Exception as e:
            return {"error": str(e)}

    @staticmethod
    async def delete_portfolio(user_id: str, portfolio_id: str) -> dict:
        """
        Delete a portfolio and all positions.

        Args:
            user_id: User ID (for validation)
            portfolio_id: Portfolio to delete

        Returns:
            dict confirming deletion
        """
        try:
            # Verify account exists and belongs to user
            account = queries.get_account(portfolio_id)
            if not account:
                return {"error": f"Portfolio '{portfolio_id}' not found"}

            if account['user_id'] != user_id:
                return {"error": "Access denied"}

            portfolio_name = account['name']

            # Get holdings count before deletion
            holdings = queries.get_holdings_for_account(portfolio_id)
            positions_count = len(holdings)

            # Delete account (cascades to holdings and transactions)
            queries.delete_account(portfolio_id)

            return {
                "success": True,
                "portfolio_id": portfolio_id,
                "name": portfolio_name,
                "positions_deleted": positions_count
            }
        except Exception as e:
            return {"error": str(e)}

    @staticmethod
    async def list_portfolios(user_id: str) -> dict:
        """
        List all portfolios for a user with summaries.

        Args:
            user_id: User ID

        Returns:
            dict with portfolio summaries
        """
        try:
            accounts = queries.get_accounts_for_user(user_id)

            summaries = []
            for account in accounts:
                # Only include manual accounts
                if not account['is_manual']:
                    continue

                holdings = queries.get_holdings_for_account(account['id'])

                total_cost = sum(
                    (h['quantity'] or 0) * (h['average_cost'] or 0)
                    for h in holdings
                )

                summaries.append({
                    "portfolio_id": account['id'],
                    "name": account['name'],
                    "description": account['account_type'],
                    "positions_count": len(holdings),
                    "total_cost_basis": round(total_cost, 2),
                    "created_at": account['created_at'],
                    "updated_at": account['updated_at']
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
        user_id: str,
        portfolio_id: str,
        target_currency: Optional[str] = None
    ) -> dict:
        """
        Get a portfolio with live prices.

        Args:
            user_id: User ID (for validation)
            portfolio_id: Portfolio to retrieve
            target_currency: Optional currency for conversion

        Returns:
            dict with portfolio and live prices
        """
        try:
            # Verify account exists and belongs to user
            account = queries.get_account(portfolio_id)
            if not account:
                return {"error": f"Portfolio '{portfolio_id}' not found"}

            if account['user_id'] != user_id:
                return {"error": "Access denied"}

            holdings = queries.get_holdings_for_account(portfolio_id)

            fx_cache = {}
            fx_rates_used = {}

            positions = []
            total_market_value = 0.0
            total_cost_basis = 0.0
            total_converted = 0.0

            for holding in holdings:
                symbol = holding.get('symbol')
                units = holding.get('quantity', 0)
                avg_cost = holding.get('average_cost', 0)
                pos_currency = holding.get('currency', 'USD')
                manual_price = holding.get('current_price')

                live_price = None
                price_source = "none"

                # Try to get live price
                if symbol:
                    live_data = get_live_price(symbol)
                    if live_data.get("price") is not None:
                        live_price = live_data["price"]
                        price_source = "yahoo_finance"

                # Fall back to manual price
                if live_price is None and manual_price is not None:
                    live_price = manual_price
                    price_source = "manual"

                cost_basis = units * avg_cost if units and avg_cost else 0
                market_value = units * live_price if units and live_price else None

                pnl = None
                pnl_pct = None
                if market_value is not None and cost_basis != 0:
                    pnl = market_value - cost_basis
                    if cost_basis > 0:
                        pnl_pct = round((pnl / cost_basis) * 100, 2)

                pos_data = {
                    "id": holding.get('id'),
                    "name": holding.get('name'),
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
                    "asset_type": holding.get('asset_type'),
                    "notes": None  # TODO: extract from metadata
                }

                if market_value is not None:
                    total_market_value += market_value
                if cost_basis is not None:
                    total_cost_basis += cost_basis

                # Handle currency conversion
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
                        if market_value is not None:
                            total_converted += market_value * fx_rate
                elif target_currency and pos_currency == target_currency:
                    if market_value is not None:
                        total_converted += market_value

                positions.append(pos_data)

            total_pnl = total_market_value - total_cost_basis if total_market_value else None
            total_pnl_pct = None
            if total_pnl is not None and total_cost_basis > 0:
                total_pnl_pct = round((total_pnl / total_cost_basis) * 100, 2)

            result = {
                "success": True,
                "portfolio_id": portfolio_id,
                "name": account['name'],
                "description": account.get('account_type'),
                "positions_count": len(positions),
                "positions": positions,
                "total_market_value": round(total_market_value, 2) if total_market_value else None,
                "total_cost_basis": round(total_cost_basis, 2),
                "total_unrealized_pnl": round(total_pnl, 2) if total_pnl else None,
                "total_unrealized_pnl_pct": total_pnl_pct,
                "updated_at": account.get('updated_at')
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
