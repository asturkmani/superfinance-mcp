"""Consolidated SnapTrade sync tool."""

import json
import os
from typing import Optional

from snaptrade_client import SnapTrade
from services.snaptrade_service import SnapTradeService
from helpers.user_context import get_current_user_id


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


def register_sync_v2(server):
    """Register consolidated sync tool."""

    @server.tool()
    async def sync(
        action: str,
        vault_user_id: Optional[str] = None,
        user_id: Optional[str] = None,
        user_secret: Optional[str] = None,
        authorization_id: Optional[str] = None,
        account_id: Optional[str] = None,
        start_date: str = None,
        end_date: str = None
    ) -> str:
        """
        Sync brokerage data via SnapTrade.

        Actions:
        - connect: Get URL to connect a brokerage account
        - status: List connected brokerage accounts
        - sync_to_db: Sync all accounts and holdings to local database
        - sync_accounts: List accounts from SnapTrade
        - sync_holdings: Get holdings for a specific account
        - sync_transactions: Get transactions for an account
        - refresh: Manually refresh brokerage data
        - disconnect: Remove a brokerage connection

        Args:
            action: Action to perform
            vault_user_id: Vault user ID for sync_to_db (uses default if not provided)
            user_id: SnapTrade user ID (uses env var if not provided)
            user_secret: SnapTrade user secret (uses env var if not provided)
            authorization_id: Brokerage authorization ID (for refresh/disconnect)
            account_id: Account ID (for sync_holdings/sync_transactions)
            start_date: Start date for sync_transactions (YYYY-MM-DD)
            end_date: End date for sync_transactions (YYYY-MM-DD)

        Returns:
            JSON with sync results or brokerage data

        Examples:
            sync(action="connect")
            sync(action="status")
            sync(action="sync_to_db")
            sync(action="sync_accounts")
            sync(action="sync_holdings", account_id="abc-123")
            sync(action="sync_transactions", account_id="abc-123", start_date="2024-01-01", end_date="2024-12-31")
            sync(action="refresh", authorization_id="auth-123")
            sync(action="disconnect", authorization_id="auth-123")
        """
        try:
            snaptrade_client = get_snaptrade_client()
            if not snaptrade_client and action != "sync_to_db":
                return json.dumps({
                    "error": "SnapTrade not configured",
                    "message": "Set SNAPTRADE_CONSUMER_KEY and SNAPTRADE_CLIENT_ID environment variables"
                }, indent=2)

            user_id = user_id or os.getenv("SNAPTRADE_USER_ID")
            user_secret = user_secret or os.getenv("SNAPTRADE_USER_SECRET")

            if action == "connect":
                if not user_id or not user_secret:
                    return json.dumps({
                        "error": "Credentials required",
                        "message": "Provide user_id and user_secret, or set SNAPTRADE_USER_ID and SNAPTRADE_USER_SECRET"
                    }, indent=2)

                response = snaptrade_client.authentication.login_snap_trade_user(
                    user_id=user_id,
                    user_secret=user_secret
                )

                data = response.body if hasattr(response, 'body') else response
                if hasattr(data, 'to_dict'):
                    data = data.to_dict()

                redirect_uri = data.get("redirectURI") if isinstance(data, dict) else getattr(data, 'redirect_uri', None)

                return json.dumps({
                    "success": True,
                    "connection_url": redirect_uri,
                    "message": "Open this URL in your browser to connect your brokerage account"
                }, indent=2)

            elif action == "status" or action == "sync_accounts":
                if not user_id or not user_secret:
                    return json.dumps({
                        "error": "Credentials required"
                    }, indent=2)

                response = snaptrade_client.account_information.list_user_accounts(
                    user_id=user_id,
                    user_secret=user_secret
                )

                accounts = response.body if hasattr(response, 'body') else response

                formatted_accounts = []
                for account in accounts:
                    if hasattr(account, 'to_dict'):
                        account = account.to_dict()
                    elif hasattr(account, '__dict__'):
                        account = vars(account)

                    formatted_accounts.append({
                        "account_id": account.get("id"),
                        "brokerage_authorization": account.get("brokerage_authorization"),
                        "name": account.get("name"),
                        "number": account.get("number"),
                        "institution": account.get("institution_name"),
                        "balance": account.get("balance"),
                        "meta": account.get("meta", {})
                    })

                return json.dumps({
                    "success": True,
                    "count": len(formatted_accounts),
                    "accounts": formatted_accounts
                }, indent=2)

            elif action == "sync_to_db":
                if not vault_user_id:
                    vault_user_id = get_current_user_id()
                
                result = await SnapTradeService.sync_to_db(
                    vault_user_id=vault_user_id,
                    snaptrade_user_id=user_id,
                    snaptrade_user_secret=user_secret
                )
                
                return json.dumps(result, indent=2)

            elif action == "sync_holdings":
                if not account_id:
                    return json.dumps({
                        "error": "account_id required for sync_holdings action"
                    }, indent=2)

                if not user_id or not user_secret:
                    return json.dumps({
                        "error": "Credentials required"
                    }, indent=2)

                response = snaptrade_client.account_information.get_user_holdings(
                    account_id=account_id,
                    user_id=user_id,
                    user_secret=user_secret
                )

                holdings = response.body if hasattr(response, 'body') else response
                if hasattr(holdings, 'to_dict'):
                    holdings = holdings.to_dict()

                def safe_get(obj, key, default=None):
                    if isinstance(obj, dict):
                        return obj.get(key, default)
                    return getattr(obj, key, default)

                account_data = safe_get(holdings, "account", {})
                if hasattr(account_data, 'to_dict'):
                    account_data = account_data.to_dict()

                result = {
                    "success": True,
                    "account": {
                        "id": safe_get(account_data, "id"),
                        "name": safe_get(account_data, "name"),
                        "number": safe_get(account_data, "number"),
                        "institution": safe_get(account_data, "institution_name")
                    },
                    "balances": safe_get(holdings, "balances", []),
                    "positions": []
                }

                positions = safe_get(holdings, "positions", [])
                for position in positions:
                    if hasattr(position, 'to_dict'):
                        position = position.to_dict()
                    symbol = safe_get(position, "symbol", {})
                    if hasattr(symbol, 'to_dict'):
                        symbol = symbol.to_dict()
                    currency = safe_get(symbol, "currency", {})
                    if hasattr(currency, 'to_dict'):
                        currency = currency.to_dict()

                    result["positions"].append({
                        "symbol": safe_get(symbol, "symbol"),
                        "description": safe_get(symbol, "description"),
                        "units": safe_get(position, "units"),
                        "price": safe_get(position, "price"),
                        "open_pnl": safe_get(position, "open_pnl"),
                        "fractional_units": safe_get(position, "fractional_units"),
                        "currency": safe_get(currency, "code") if currency else None
                    })

                result["total_value"] = safe_get(holdings, "total_value")

                return json.dumps(result, indent=2)

            elif action == "sync_transactions":
                if not account_id or not start_date or not end_date:
                    return json.dumps({
                        "error": "account_id, start_date, and end_date required for sync_transactions action"
                    }, indent=2)

                if not user_id or not user_secret:
                    return json.dumps({
                        "error": "Credentials required"
                    }, indent=2)

                params = {
                    "account_id": account_id,
                    "user_id": user_id,
                    "user_secret": user_secret,
                    "start_date": start_date,
                    "end_date": end_date
                }

                response = snaptrade_client.account_information.get_account_activities(**params)
                activities = response.body if hasattr(response, 'body') else response

                if isinstance(activities, dict):
                    activities = activities.get("data", [])

                formatted = []
                for a in activities:
                    formatted.append(_extract_transaction(a))

                return json.dumps({
                    "success": True,
                    "account_id": account_id,
                    "count": len(formatted),
                    "transactions": formatted
                }, indent=2)

            elif action == "refresh":
                if not authorization_id:
                    return json.dumps({
                        "error": "authorization_id required for refresh action"
                    }, indent=2)

                if not user_id or not user_secret:
                    return json.dumps({
                        "error": "Credentials required"
                    }, indent=2)

                response = snaptrade_client.connections.refresh_brokerage_authorization(
                    authorization_id=authorization_id,
                    user_id=user_id,
                    user_secret=user_secret
                )

                data = response.body if hasattr(response, 'body') else response
                if hasattr(data, 'to_dict'):
                    data = data.to_dict()

                return json.dumps({
                    "success": True,
                    "authorization_id": authorization_id,
                    "message": "Refresh scheduled. Holdings will be updated shortly.",
                    "detail": data.get("detail") if isinstance(data, dict) else str(data)
                }, indent=2)

            elif action == "disconnect":
                if not authorization_id:
                    return json.dumps({
                        "error": "authorization_id required for disconnect action"
                    }, indent=2)

                if not user_id or not user_secret:
                    return json.dumps({
                        "error": "Credentials required"
                    }, indent=2)

                snaptrade_client.connections.remove_brokerage_authorization(
                    authorization_id=authorization_id,
                    user_id=user_id,
                    user_secret=user_secret
                )

                return json.dumps({
                    "success": True,
                    "message": f"Brokerage connection {authorization_id} has been disconnected"
                }, indent=2)

            else:
                return json.dumps({
                    "error": f"Invalid action: {action}",
                    "valid_actions": ["connect", "status", "sync_to_db", "sync_accounts", "sync_holdings", "sync_transactions", "refresh", "disconnect"]
                }, indent=2)

        except Exception as e:
            return json.dumps({"error": str(e)}, indent=2)


def _safe_get(obj, key, default=None):
    """Safely get a value from dict-like objects or SnapTrade schema objects."""
    if obj is None:
        return default
    if hasattr(obj, 'get'):
        try:
            val = obj.get(key)
            return val if val is not None else default
        except Exception:
            pass
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _extract_transaction(activity) -> dict:
    """Extract and format a transaction from SnapTrade activity."""
    safe_get = _safe_get

    symbol_obj = safe_get(activity, "symbol")
    symbol = None
    symbol_description = None
    if symbol_obj:
        symbol = safe_get(symbol_obj, "symbol")
        symbol_description = safe_get(symbol_obj, "description")

    currency_obj = safe_get(activity, "currency")
    currency = None
    if currency_obj:
        currency = safe_get(currency_obj, "code")

    account_obj = safe_get(activity, "account")
    account_id = None
    account_name = None
    if account_obj:
        account_id = safe_get(account_obj, "id")
        account_name = safe_get(account_obj, "name")

    def to_float(val):
        if val is None:
            return None
        try:
            return float(val)
        except (TypeError, ValueError):
            return val

    return {
        "id": safe_get(activity, "id"),
        "account_id": account_id,
        "account_name": account_name,
        "type": safe_get(activity, "type"),
        "symbol": symbol,
        "symbol_description": symbol_description,
        "description": safe_get(activity, "description"),
        "trade_date": str(safe_get(activity, "trade_date")) if safe_get(activity, "trade_date") else None,
        "settlement_date": str(safe_get(activity, "settlement_date")) if safe_get(activity, "settlement_date") else None,
        "units": to_float(safe_get(activity, "units")),
        "price": to_float(safe_get(activity, "price")),
        "amount": to_float(safe_get(activity, "amount")),
        "currency": currency,
        "fee": to_float(safe_get(activity, "fee")),
        "fx_rate": to_float(safe_get(activity, "fx_rate"))
    }
