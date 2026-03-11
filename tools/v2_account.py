"""Consolidated account management tool."""

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
                       "Use sync tool to refresh synced data."
        })
    return None


def register_account_v2(server):
    """Register consolidated account tool."""

    @server.tool()
    async def account(
        action: str,
        account_id: str = None,
        name: str = None,
        account_type: Optional[str] = None,
        currency: str = "USD",
        user_id: Optional[str] = None
    ) -> str:
        """
        Manage accounts (portfolio buckets).

        Actions:
        - create: Create a new manual account
        - list: List all accounts (manual and synced)
        - get: Get account details
        - update: Update account name (manual accounts only)
        - delete: Delete account and all holdings/transactions

        Args:
            action: Action to perform (create|list|get|update|delete)
            account_id: Account ID for get/update/delete actions
            name: Account name for create/update
            account_type: Account type label (e.g., "isa", "pension", "real_estate")
            currency: Account currency (default "USD")
            user_id: User ID (uses default if not provided)

        Returns:
            JSON with account data or operation result

        Examples:
            account(action="create", name="Vanguard ISA", account_type="isa", currency="GBP")
            account(action="list")
            account(action="get", account_id="acc_123")
            account(action="update", account_id="acc_123", name="Vanguard S&S ISA")
            account(action="delete", account_id="acc_123")
        """
        try:
            if not user_id:
                user_id = get_current_user_id()

            if action == "create":
                if not name:
                    return json.dumps({
                        "error": "name required for create action"
                    }, indent=2)

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

            elif action == "list":
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

            elif action == "get":
                if not account_id:
                    return json.dumps({
                        "error": "account_id required for get action"
                    }, indent=2)

                account, error = _get_account_or_error(account_id)
                if error:
                    return error

                return json.dumps(account, indent=2, default=str)

            elif action == "update":
                if not account_id:
                    return json.dumps({
                        "error": "account_id required for update action"
                    }, indent=2)
                if not name:
                    return json.dumps({
                        "error": "name required for update action"
                    }, indent=2)

                error = _check_manual(account_id)
                if error:
                    return error

                queries.update_account(account_id, name=name)
                return json.dumps({
                    "success": True,
                    "account_id": account_id,
                    "name": name
                }, indent=2)

            elif action == "delete":
                if not account_id:
                    return json.dumps({
                        "error": "account_id required for delete action"
                    }, indent=2)

                account, error = _get_account_or_error(account_id)
                if error:
                    return error

                # If synced, disconnect from SnapTrade first
                snaptrade_disconnected = False
                if not account["is_manual"]:
                    try:
                        from services.snaptrade_service import SnapTradeService
                        conn_id = account.get("connection_id")
                        if conn_id:
                            from db.database import get_db
                            db = get_db()
                            cursor = db.cursor()
                            cursor.execute("SELECT provider_account_id FROM connections WHERE id = ?", (conn_id,))
                            row = cursor.fetchone()
                            if row:
                                auth_id = row[0]
                                result = await SnapTradeService.disconnect_account(auth_id)
                                snaptrade_disconnected = result.get("success", False)
                    except Exception:
                        snaptrade_disconnected = False

                queries.delete_account(account_id)
                
                msg = "Account and all holdings/transactions deleted"
                if snaptrade_disconnected:
                    msg += " (SnapTrade connection disconnected)"
                elif not account["is_manual"]:
                    msg += " (local data removed — SnapTrade connection may need manual cleanup)"
                    
                return json.dumps({
                    "success": True,
                    "account_id": account_id,
                    "message": msg
                }, indent=2)

            else:
                return json.dumps({
                    "error": f"Invalid action: {action}",
                    "valid_actions": ["create", "list", "get", "update", "delete"]
                }, indent=2)

        except Exception as e:
            return json.dumps({"error": str(e)}, indent=2)
