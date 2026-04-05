"""Simplified SnapTrade tool - account creation and holdings."""

import json
import os
from typing import Optional

from snaptrade_client import SnapTrade


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


def register_snaptrade_v2(server):
    """Register simplified SnapTrade tool."""

    @server.tool()
    def snaptrade(
        action: str,
        user_id: Optional[str] = None,
        user_secret: Optional[str] = None,
        account_id: Optional[str] = None
    ) -> str:
        """
        Manage brokerage accounts via SnapTrade.

        Actions:
        - register: Create a new SnapTrade user (returns user_id and user_secret)
        - connect: Get URL to connect a brokerage account
        - accounts: List connected brokerage accounts
        - holdings: Get holdings for a specific account

        Args:
            action: Action to perform (register|connect|accounts|holdings)
            user_id: SnapTrade user ID (uses SNAPTRADE_USER_ID env var if not provided)
            user_secret: SnapTrade user secret (uses SNAPTRADE_USER_SECRET env var if not provided)
            account_id: Account ID (required for holdings action)

        Returns:
            JSON with results

        Examples:
            snaptrade(action="register", user_id="my-user-123")
            snaptrade(action="connect")
            snaptrade(action="accounts")
            snaptrade(action="holdings", account_id="abc-123")
        """
        try:
            client = get_snaptrade_client()
            if not client:
                return json.dumps({
                    "error": "SnapTrade not configured",
                    "message": "Set SNAPTRADE_CONSUMER_KEY and SNAPTRADE_CLIENT_ID environment variables"
                }, indent=2)

            user_id = user_id or os.getenv("SNAPTRADE_USER_ID")
            user_secret = user_secret or os.getenv("SNAPTRADE_USER_SECRET")

            if action == "register":
                if not user_id:
                    return json.dumps({
                        "error": "user_id required for register action"
                    }, indent=2)

                response = client.authentication.register_snap_trade_user(user_id=user_id)
                data = response.body if hasattr(response, 'body') else response
                if hasattr(data, 'to_dict'):
                    data = data.to_dict()

                return json.dumps({
                    "success": True,
                    "user_id": user_id,
                    "user_secret": data.get("userSecret") if isinstance(data, dict) else getattr(data, 'user_secret', None),
                    "message": "User registered. IMPORTANT: Save the user_secret!"
                }, indent=2)

            elif action == "connect":
                if not user_id or not user_secret:
                    return json.dumps({
                        "error": "Credentials required",
                        "message": "Provide user_id and user_secret, or set SNAPTRADE_USER_ID and SNAPTRADE_USER_SECRET"
                    }, indent=2)

                response = client.authentication.login_snap_trade_user(
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

            elif action == "holdings":
                if not account_id:
                    return json.dumps({
                        "error": "account_id required for holdings action"
                    }, indent=2)
                if not user_id or not user_secret:
                    return json.dumps({"error": "Credentials required"}, indent=2)

                response = client.account_information.get_user_holdings(
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
                        "currency": safe_get(currency, "code") if currency else None
                    })

                result["total_value"] = safe_get(holdings, "total_value")

                return json.dumps(result, indent=2)

            else:
                return json.dumps({
                    "error": f"Invalid action: {action}",
                    "valid_actions": ["register", "connect", "accounts", "holdings"]
                }, indent=2)

        except Exception as e:
            return json.dumps({"error": str(e)}, indent=2)
