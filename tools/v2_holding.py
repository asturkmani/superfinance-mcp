"""Consolidated holding management tool."""

import json
from typing import Optional

from db import queries
from services.holdings_service import HoldingsService
from helpers.user_context import get_current_user_id


def _check_holdings_editable(account_id: str) -> Optional[str]:
    """Return error JSON if holdings are synced (not editable), else None."""
    account = queries.get_account(account_id)
    if not account:
        return json.dumps({"error": f"Account '{account_id}' not found"})
    if not account["is_manual"] and account.get("holdings_synced"):
        return json.dumps({
            "error": "Cannot edit synced holdings",
            "account": account["name"],
            "message": "Holdings for this account are synced from SnapTrade. Use sync tool to refresh."
        })
    return None


def register_holding_v2(server):
    """Register consolidated holding tool."""

    @server.tool()
    async def holding(
        action: str,
        account_id: str = None,
        holding_id: str = None,
        symbol: str = None,
        quantity: float = None,
        average_cost: Optional[float] = None,
        current_price: Optional[float] = None,
        currency: str = "USD",
        asset_type: Optional[str] = None,
        name: Optional[str] = None,
        user_id: Optional[str] = None,
        reporting_currency: Optional[str] = None
    ) -> str:
        """
        Manage holdings (positions in accounts).

        Actions:
        - list: Get holdings for an account (or all if account_id omitted)
        - list_all: Get all holdings across all accounts with live prices
        - add: Add or update a holding in a manual account
        - update: Update a holding in a manual account
        - remove: Remove a holding from a manual account

        Args:
            action: Action to perform (list|list_all|add|update|remove)
            account_id: Account ID for list/add actions
            holding_id: Holding ID for update/remove actions
            symbol: Ticker or identifier (e.g., "AAPL", "BTC")
            quantity: Number of units
            average_cost: Cost per unit
            current_price: Current price per unit
            currency: Currency code (default "USD")
            asset_type: Type label (e.g., "equity", "etf", "crypto", "liability")
            name: Display name
            user_id: User ID (uses default if not provided)
            reporting_currency: For list_all - convert all to this currency

        Returns:
            JSON with holding data or operation result

        Examples:
            holding(action="list", account_id="acc_123")
            holding(action="list_all")
            holding(action="list_all", reporting_currency="GBP")
            holding(action="add", account_id="acc_123", symbol="AAPL", quantity=10, average_cost=150.00)
            holding(action="update", holding_id="hold_123", quantity=12)
            holding(action="remove", holding_id="hold_123")
        """
        try:
            if not user_id:
                user_id = get_current_user_id()

            if action == "list":
                if account_id:
                    holdings = queries.get_holdings_for_account(account_id)
                else:
                    holdings = queries.get_all_holdings_for_user(user_id)

                result = []
                for h in holdings:
                    result.append({
                        "id": h["id"],
                        "account_id": h["account_id"],
                        "symbol": h["symbol"],
                        "name": h.get("name"),
                        "quantity": h["quantity"],
                        "average_cost": h.get("average_cost"),
                        "current_price": h.get("current_price"),
                        "market_value": h.get("market_value"),
                        "currency": h["currency"],
                        "asset_type": h.get("asset_type"),
                    })

                return json.dumps({"holdings": result, "count": len(result)}, indent=2, default=str)

            elif action == "list_all":
                result = await HoldingsService.list_all_holdings(
                    user_id=user_id,
                    reporting_currency=reporting_currency
                )
                return json.dumps(result, indent=2)

            elif action == "add":
                if not account_id or not symbol or quantity is None:
                    return json.dumps({
                        "error": "account_id, symbol, and quantity required for add action"
                    }, indent=2)

                error = _check_holdings_editable(account_id)
                if error:
                    return error

                market_value = None
                if quantity is not None and current_price is not None:
                    market_value = quantity * current_price

                holding_id = queries.upsert_holding(
                    account_id=account_id,
                    symbol=symbol,
                    name=name,
                    quantity=quantity,
                    average_cost=average_cost,
                    current_price=current_price,
                    market_value=market_value,
                    currency=currency,
                    asset_type=asset_type,
                )

                return json.dumps({
                    "success": True,
                    "holding_id": holding_id,
                    "symbol": symbol,
                    "quantity": quantity,
                    "market_value": market_value,
                }, indent=2)

            elif action == "update":
                if not holding_id:
                    return json.dumps({
                        "error": "holding_id required for update action"
                    }, indent=2)

                from db.database import get_db, row_to_dict
                conn = get_db()
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT h.*, a.is_manual, a.holdings_synced FROM holdings h
                    JOIN accounts a ON h.account_id = a.id
                    WHERE h.id = ?
                """, (holding_id,))
                row = cursor.fetchone()
                if not row:
                    return json.dumps({"error": f"Holding '{holding_id}' not found"})

                holding = row_to_dict(row)
                if not holding["is_manual"] and holding.get("holdings_synced"):
                    return json.dumps({
                        "error": "Cannot edit synced holding",
                        "message": "Holdings for this account are synced from SnapTrade."
                    })

                # Build update
                updates = {}
                if quantity is not None:
                    updates["quantity"] = quantity
                if average_cost is not None:
                    updates["average_cost"] = average_cost
                if current_price is not None:
                    updates["current_price"] = current_price
                if name is not None:
                    updates["name"] = name

                # Recompute market_value
                q = quantity if quantity is not None else holding["quantity"]
                p = current_price if current_price is not None else holding["current_price"]
                if q is not None and p is not None:
                    updates["market_value"] = q * p

                if updates:
                    set_clause = ", ".join(f"{k} = ?" for k in updates)
                    set_clause += ", updated_at = CURRENT_TIMESTAMP"
                    params = list(updates.values()) + [holding_id]
                    cursor.execute(f"UPDATE holdings SET {set_clause} WHERE id = ?", params)
                    conn.commit()

                return json.dumps({
                    "success": True,
                    "holding_id": holding_id,
                    "updated": list(updates.keys())
                }, indent=2)

            elif action == "remove":
                if not holding_id:
                    return json.dumps({
                        "error": "holding_id required for remove action"
                    }, indent=2)

                from db.database import get_db
                conn = get_db()
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT h.id, a.is_manual, a.holdings_synced FROM holdings h
                    JOIN accounts a ON h.account_id = a.id
                    WHERE h.id = ?
                """, (holding_id,))
                row = cursor.fetchone()
                if not row:
                    return json.dumps({"error": f"Holding '{holding_id}' not found"})
                if not row[1] and row[2]:  # not manual AND holdings synced
                    return json.dumps({
                        "error": "Cannot remove synced holding",
                        "message": "Holdings for this account are synced from SnapTrade."
                    })

                queries.delete_holding(holding_id)
                return json.dumps({
                    "success": True,
                    "holding_id": holding_id,
                    "message": "Holding removed"
                }, indent=2)

            else:
                return json.dumps({
                    "error": f"Invalid action: {action}",
                    "valid_actions": ["list", "list_all", "add", "update", "remove"]
                }, indent=2)

        except Exception as e:
            return json.dumps({"error": str(e)}, indent=2)
