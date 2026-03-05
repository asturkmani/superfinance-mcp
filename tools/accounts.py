"""Account, holdings, and transaction CRUD tools with synced/manual guard."""

import json
from typing import Optional
from db import queries
from helpers.user_context import get_current_user_id


def _get_account_or_error(account_id: str) -> tuple:
    """Return (account_dict, None) or (None, error_json)."""
    account = queries.get_account(account_id)
    if not account:
        return None, json.dumps({"error": f"Account '{account_id}' not found"})
    return account, None


def _check_manual(account_id: str) -> Optional[str]:
    """Return error JSON if account is synced (not editable), else None."""
    account, error = _get_account_or_error(account_id)
    if error:
        return error
    if not account["is_manual"]:
        return json.dumps({
            "error": "Cannot edit synced account",
            "account": account["name"],
            "message": "This account is synced from a brokerage via SnapTrade. "
                       "Only manual accounts can be edited. "
                       "Use snaptrade_sync_to_db to refresh synced data."
        })
    return None


def _check_holdings_editable(account_id: str) -> Optional[str]:
    """Return error JSON if holdings are synced (not editable), else None."""
    account, error = _get_account_or_error(account_id)
    if error:
        return error
    if not account["is_manual"] and account.get("holdings_synced"):
        return json.dumps({
            "error": "Cannot edit synced holdings",
            "account": account["name"],
            "message": "Holdings for this account are synced from SnapTrade. "
                       "Use snaptrade_sync_to_db to refresh."
        })
    return None


def _check_transactions_editable(account_id: str) -> Optional[str]:
    """Return error JSON if transactions are synced (not editable), else None."""
    account, error = _get_account_or_error(account_id)
    if error:
        return error
    if not account["is_manual"] and account.get("transactions_synced"):
        return json.dumps({
            "error": "Cannot edit synced transactions",
            "account": account["name"],
            "message": "Transactions for this account are synced from SnapTrade. "
                       "Use snaptrade_sync_to_db to refresh."
        })
    return None


def register_account_tools(server):
    """Register account CRUD tools."""

    # =========================================================================
    # ACCOUNTS
    # =========================================================================

    @server.tool()
    def create_account(
        name: str,
        account_type: Optional[str] = None,
        currency: str = "USD",
        user_id: Optional[str] = None
    ) -> str:
        """
        Create a manual account (portfolio bucket).

        Use for tracking investments not connected via SnapTrade:
        private equity, real estate, pension, ISA, crypto, liabilities, etc.

        Args:
            name: Account name (e.g., "Vanguard ISA", "Home Equity")
            account_type: Optional label (e.g., "isa", "pension", "real_estate", "crypto")
            currency: Account currency (default USD)
            user_id: User ID (uses default if not provided)

        Returns:
            JSON with the created account details
        """
        if not user_id:
            user_id = get_current_user_id()

        account_id = queries.create_account(
            user_id=user_id,
            name=name,
            account_type=account_type,
            currency=currency,
            is_manual=True
        )

        return json.dumps({
            "success": True,
            "account_id": account_id,
            "name": name,
            "account_type": account_type,
            "currency": currency,
            "is_manual": True
        }, indent=2)

    @server.tool()
    def list_accounts(user_id: Optional[str] = None) -> str:
        """
        List all accounts for a user (both manual and synced).

        Args:
            user_id: User ID (uses default if not provided)

        Returns:
            JSON with list of accounts, each showing if it's editable (manual) or read-only (synced)
        """
        if not user_id:
            user_id = get_current_user_id()

        accounts = queries.get_accounts_for_user(user_id)
        result = []
        for a in accounts:
            is_manual = bool(a["is_manual"])
            h_synced = bool(a.get("holdings_synced"))
            t_synced = bool(a.get("transactions_synced"))
            result.append({
                "id": a["id"],
                "name": a["name"],
                "account_type": a["account_type"],
                "currency": a["currency"],
                "is_manual": is_manual,
                "holdings_synced": h_synced,
                "transactions_synced": t_synced,
                "holdings_editable": is_manual or not h_synced,
                "transactions_editable": is_manual or not t_synced,
                "last_sync_at": a.get("last_sync_at"),
            })

        return json.dumps({"accounts": result, "count": len(result)}, indent=2, default=str)

    @server.tool()
    def update_account(
        account_id: str,
        name: Optional[str] = None
    ) -> str:
        """
        Update a manual account's name.

        Synced accounts cannot be edited.

        Args:
            account_id: Account ID
            name: New account name

        Returns:
            JSON confirming update or error if synced
        """
        error = _check_manual(account_id)
        if error:
            return error

        queries.update_account(account_id, name=name)
        return json.dumps({"success": True, "account_id": account_id, "name": name}, indent=2)

    @server.tool()
    async def delete_account(account_id: str) -> str:
        """
        Delete an account and all its holdings/transactions.

        For synced accounts, this also disconnects the brokerage connection
        from SnapTrade before deleting local data.

        Args:
            account_id: Account ID to delete

        Returns:
            JSON confirming deletion
        """
        account, error = _get_account_or_error(account_id)
        if error:
            return error

        # If synced, disconnect from SnapTrade first
        snaptrade_disconnected = False
        if not account["is_manual"]:
            try:
                from services.snaptrade_service import SnapTradeService
                # Get the brokerage authorization ID from the connection
                conn_id = account.get("connection_id")
                if conn_id:
                    from db.database import get_db, row_to_dict
                    db = get_db()
                    cursor = db.cursor()
                    cursor.execute("SELECT provider_account_id FROM connections WHERE id = ?", (conn_id,))
                    row = cursor.fetchone()
                    if row:
                        auth_id = row[0]
                        result = await SnapTradeService.disconnect_account(auth_id)
                        snaptrade_disconnected = result.get("success", False)
            except Exception as e:
                # Log but don't block deletion
                snaptrade_disconnected = False

        queries.delete_account(account_id)
        
        msg = "Account and all holdings/transactions deleted"
        if snaptrade_disconnected:
            msg += " (SnapTrade connection disconnected)"
        elif not account["is_manual"]:
            msg += " (local data removed — SnapTrade connection may need manual cleanup)"
            
        return json.dumps({"success": True, "account_id": account_id, "message": msg}, indent=2)

    # =========================================================================
    # HOLDINGS
    # =========================================================================

    @server.tool()
    def get_holdings(
        account_id: Optional[str] = None,
        user_id: Optional[str] = None
    ) -> str:
        """
        Get holdings for an account or all accounts.

        Args:
            account_id: Specific account ID (if omitted, returns all holdings for user)
            user_id: User ID (uses default if not provided)

        Returns:
            JSON with holdings list including symbol, quantity, price, market value
        """
        if not user_id:
            user_id = get_current_user_id()

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

    @server.tool()
    def add_holding(
        account_id: str,
        symbol: str,
        quantity: float,
        average_cost: Optional[float] = None,
        current_price: Optional[float] = None,
        currency: str = "USD",
        asset_type: Optional[str] = None,
        name: Optional[str] = None
    ) -> str:
        """
        Add or update a holding in a manual account.

        For liabilities, use a negative market_value (e.g., mortgage = qty 1, price -350000).

        Synced accounts cannot be edited — their holdings come from SnapTrade.

        Args:
            account_id: Account ID (must be manual)
            symbol: Ticker or identifier (e.g., "AAPL", "MORTGAGE", "BTC")
            quantity: Number of units
            average_cost: Cost per unit (optional)
            current_price: Current price per unit (optional)
            currency: Currency code (default USD)
            asset_type: Type label (e.g., "equity", "etf", "real_estate", "liability", "crypto")
            name: Display name (optional)

        Returns:
            JSON confirming the holding or error if synced
        """
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

    @server.tool()
    def update_holding(
        holding_id: str,
        quantity: Optional[float] = None,
        average_cost: Optional[float] = None,
        current_price: Optional[float] = None,
        name: Optional[str] = None
    ) -> str:
        """
        Update a holding in a manual account.

        Synced holdings cannot be edited.

        Args:
            holding_id: Holding ID to update
            quantity: New quantity (optional)
            average_cost: New average cost (optional)
            current_price: New current price (optional)
            name: New display name (optional)

        Returns:
            JSON confirming update or error if synced
        """
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
                "message": "Holdings for this account are synced from SnapTrade. "
                           "Use snaptrade_sync_to_db to refresh."
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

        return json.dumps({"success": True, "holding_id": holding_id, "updated": list(updates.keys())}, indent=2)

    @server.tool()
    def remove_holding(holding_id: str) -> str:
        """
        Remove a holding from a manual account.

        Synced holdings cannot be removed.

        Args:
            holding_id: Holding ID to remove

        Returns:
            JSON confirming removal or error if synced
        """
        from db.database import get_db, row_to_dict
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
        return json.dumps({"success": True, "holding_id": holding_id, "message": "Holding removed"}, indent=2)

    # =========================================================================
    # TRANSACTIONS
    # =========================================================================

    @server.tool()
    def get_transactions(
        account_id: Optional[str] = None,
        symbol: Optional[str] = None,
        user_id: Optional[str] = None
    ) -> str:
        """
        Get transactions for an account or by symbol.

        Args:
            account_id: Account ID (optional)
            symbol: Filter by symbol (optional)
            user_id: User ID (uses default if not provided)

        Returns:
            JSON with transaction list
        """
        if not user_id:
            user_id = get_current_user_id()

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

    @server.tool()
    def add_transaction(
        account_id: str,
        symbol: str,
        date: str,
        transaction_type: str,
        quantity: Optional[float] = None,
        price: Optional[float] = None,
        fees: float = 0.0,
        currency: str = "USD",
        name: Optional[str] = None
    ) -> str:
        """
        Add a transaction to a manual account.

        Synced accounts cannot have manual transactions added.

        Args:
            account_id: Account ID (must be manual)
            symbol: Ticker symbol
            date: Transaction date (YYYY-MM-DD)
            transaction_type: Type (buy, sell, dividend, fee, deposit, withdrawal, transfer, etc.)
            quantity: Number of shares/units (optional for cash-only transactions)
            price: Price per unit (optional)
            fees: Transaction fees (default 0)
            currency: Currency code (default USD)
            name: Security name (optional)

        Returns:
            JSON confirming the transaction or error if synced
        """
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

    @server.tool()
    def delete_transaction(transaction_id: str) -> str:
        """
        Delete a transaction from a manual account.

        Synced transactions cannot be deleted.

        Args:
            transaction_id: Transaction ID to delete

        Returns:
            JSON confirming deletion or error if synced
        """
        from db.database import get_db, row_to_dict
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
        return json.dumps({"success": True, "transaction_id": transaction_id, "message": "Transaction deleted"}, indent=2)

    @server.tool()
    def create_token(name: str = "default") -> str:
        """
        Create a new API token for the current user.
        
        Args:
            name: Optional name for the token (e.g., "desktop", "mobile")
            
        Returns:
            JSON with the new token (save this - it won't be shown again)
        """
        user_id = get_current_user_id()
        token = queries.create_api_token(user_id, name)
        return json.dumps({
            "token": token,
            "name": name,
            "message": "Save this token — it won't be shown again"
        }, indent=2)

    @server.tool()
    def list_tokens() -> str:
        """
        List all API tokens for the current user (masked for security).
        
        Returns:
            JSON with list of tokens (masked)
        """
        user_id = get_current_user_id()
        tokens = queries.list_user_tokens(user_id)
        return json.dumps(tokens, indent=2)

    @server.tool()
    def revoke_token(token: str) -> str:
        """
        Revoke an API token.
        
        Args:
            token: The token to revoke (use the masked or full token string)
            
        Returns:
            JSON confirming revocation
        """
        success = queries.revoke_token(token)
        return json.dumps({"success": success}, indent=2)
