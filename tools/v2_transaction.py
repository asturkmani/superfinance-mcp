"""Consolidated transaction management tool."""

import json
from typing import Optional

from db import queries
from helpers.user_context import get_current_user_id


def _check_transactions_editable(account_id: str) -> Optional[str]:
    """Return error JSON if transactions are synced (not editable), else None."""
    account = queries.get_account(account_id)
    if not account:
        return json.dumps({"error": f"Account '{account_id}' not found"})
    if not account["is_manual"] and account.get("transactions_synced"):
        return json.dumps({
            "error": "Cannot edit synced transactions",
            "account": account["name"],
            "message": "Transactions for this account are synced from SnapTrade."
        })
    return None


def register_transaction_v2(server):
    """Register consolidated transaction tool."""

    @server.tool()
    def transaction(
        action: str,
        account_id: str = None,
        transaction_id: str = None,
        symbol: str = None,
        date: str = None,
        transaction_type: str = None,
        quantity: Optional[float] = None,
        price: Optional[float] = None,
        fees: float = 0.0,
        currency: str = "USD",
        name: Optional[str] = None,
        user_id: Optional[str] = None
    ) -> str:
        """
        Manage transactions.

        Actions:
        - list: Get transactions for an account or by symbol
        - add: Add a transaction to a manual account
        - delete: Delete a transaction from a manual account

        Args:
            action: Action to perform (list|add|delete)
            account_id: Account ID for list/add actions
            transaction_id: Transaction ID for delete action
            symbol: Ticker symbol (for add) or filter (for list)
            date: Transaction date in YYYY-MM-DD format
            transaction_type: Type (buy|sell|dividend|fee|deposit|withdrawal|transfer)
            quantity: Number of shares/units
            price: Price per unit
            fees: Transaction fees (default 0)
            currency: Currency code (default "USD")
            name: Security name
            user_id: User ID (uses default if not provided)

        Returns:
            JSON with transaction data or operation result

        Examples:
            transaction(action="list", account_id="acc_123")
            transaction(action="list", symbol="AAPL")
            transaction(action="add", account_id="acc_123", symbol="AAPL", date="2024-01-15", transaction_type="buy", quantity=10, price=150.00)
            transaction(action="delete", transaction_id="txn_123")
        """
        try:
            if not user_id:
                user_id = get_current_user_id()

            if action == "list":
                if account_id:
                    txns = queries.get_transactions_for_account(account_id)
                elif symbol:
                    txns = queries.get_transactions_by_symbol(symbol, user_id)
                else:
                    # Get all transactions across all accounts
                    from db.database import get_db, rows_to_dicts
                    conn = get_db()
                    cursor = conn.cursor()
                    cursor.execute("""
                        SELECT t.* FROM transactions t
                        JOIN accounts a ON t.account_id = a.id
                        WHERE a.user_id = ?
                        ORDER BY t.date DESC
                        LIMIT 500
                    """, (user_id,))
                    txns = rows_to_dicts(cursor.fetchall())

                result = []
                for t in txns:
                    result.append({
                        "id": t["id"],
                        "account_id": t["account_id"],
                        "symbol": t["symbol"],
                        "name": t.get("name"),
                        "date": t["date"],
                        "transaction_type": t["transaction_type"],
                        "quantity": t.get("quantity"),
                        "price": t.get("price"),
                        "fees": t.get("fees"),
                        "currency": t["currency"],
                        "source": t["source"],
                    })

                return json.dumps({"transactions": result, "count": len(result)}, indent=2, default=str)

            elif action == "add":
                if not account_id or not symbol or not date or not transaction_type:
                    return json.dumps({
                        "error": "account_id, symbol, date, and transaction_type required for add action"
                    }, indent=2)

                error = _check_transactions_editable(account_id)
                if error:
                    return error

                txn_id = queries.create_transaction(
                    account_id=account_id,
                    symbol=symbol,
                    date=date,
                    transaction_type=transaction_type,
                    name=name,
                    quantity=quantity,
                    price=price,
                    fees=fees,
                    currency=currency,
                    source="manual",
                )

                return json.dumps({
                    "success": True,
                    "transaction_id": txn_id,
                    "symbol": symbol,
                    "date": date,
                    "transaction_type": transaction_type,
                    "quantity": quantity,
                    "price": price,
                }, indent=2)

            elif action == "delete":
                if not transaction_id:
                    return json.dumps({
                        "error": "transaction_id required for delete action"
                    }, indent=2)

                from db.database import get_db
                conn = get_db()
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT t.id, t.source, a.is_manual, a.transactions_synced FROM transactions t
                    JOIN accounts a ON t.account_id = a.id
                    WHERE t.id = ?
                """, (transaction_id,))
                row = cursor.fetchone()
                if not row:
                    return json.dumps({"error": f"Transaction '{transaction_id}' not found"})
                if not row[2] and row[3]:  # not manual AND transactions synced
                    return json.dumps({
                        "error": "Cannot delete synced transaction",
                        "message": "Transactions for this account are synced from SnapTrade."
                    })

                cursor.execute("DELETE FROM transactions WHERE id = ?", (transaction_id,))
                conn.commit()
                return json.dumps({
                    "success": True,
                    "transaction_id": transaction_id,
                    "message": "Transaction deleted"
                }, indent=2)

            else:
                return json.dumps({
                    "error": f"Invalid action: {action}",
                    "valid_actions": ["list", "add", "delete"]
                }, indent=2)

        except Exception as e:
            return json.dumps({"error": str(e)}, indent=2)
