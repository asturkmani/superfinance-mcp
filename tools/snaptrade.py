"""SnapTrade tools for brokerage account integration."""

import json
import os
from typing import Optional

from snaptrade_client import SnapTrade

from helpers.pricing import get_live_price


# Initialize SnapTrade client
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


def register_snaptrade_tools(server):
    """Register all SnapTrade tools with the server."""

    @server.tool()
    def snaptrade_register_user(user_id: Optional[str] = None) -> str:
        """
        Register a new SnapTrade user to connect brokerage accounts.

        This is a one-time setup step. Returns a user_secret that must be stored securely
        and used for all subsequent SnapTrade operations.

        Args:
            user_id: Unique identifier for the user. If not provided, uses SNAPTRADE_USER_ID
                     from environment variables.

        Returns:
            JSON string containing user_id and user_secret (IMPORTANT: Save this!)

        Note: If SnapTrade is not configured (missing API credentials), returns an error message.
        """
        snaptrade_client = get_snaptrade_client()
        if not snaptrade_client:
            return json.dumps({
                "error": "SnapTrade not configured",
                "message": "Set SNAPTRADE_CONSUMER_KEY and SNAPTRADE_CLIENT_ID environment variables"
            })

        try:
            if not user_id:
                user_id = os.getenv("SNAPTRADE_USER_ID")
                if not user_id:
                    return json.dumps({
                        "error": "user_id required",
                        "message": "Provide user_id parameter or set SNAPTRADE_USER_ID environment variable"
                    })

            response = snaptrade_client.authentication.register_snap_trade_user(
                user_id=user_id
            )

            data = response.body if hasattr(response, 'body') else response
            if hasattr(data, 'to_dict'):
                data = data.to_dict()

            return json.dumps({
                "success": True,
                "user_id": user_id,
                "user_secret": data.get("userSecret") if isinstance(data, dict) else getattr(data, 'user_secret', None),
                "message": "User registered successfully. IMPORTANT: Save the user_secret!"
            }, indent=2)

        except Exception as e:
            return json.dumps({
                "error": str(e),
                "message": "Failed to register user"
            }, indent=2)

    @server.tool()
    def snaptrade_get_connection_url(
        user_id: Optional[str] = None,
        user_secret: Optional[str] = None
    ) -> str:
        """
        Get URL for user to connect their brokerage account.

        Returns a redirect URL that the user must visit in their browser to authenticate
        with their brokerage and grant SnapTrade access.

        Args:
            user_id: SnapTrade user ID. If not provided, uses SNAPTRADE_USER_ID env var.
            user_secret: SnapTrade user secret. If not provided, uses SNAPTRADE_USER_SECRET env var.

        Returns:
            JSON string containing the connection URL
        """
        snaptrade_client = get_snaptrade_client()
        if not snaptrade_client:
            return json.dumps({
                "error": "SnapTrade not configured",
                "message": "Set SNAPTRADE_CONSUMER_KEY and SNAPTRADE_CLIENT_ID environment variables"
            })

        try:
            user_id = user_id or os.getenv("SNAPTRADE_USER_ID")
            user_secret = user_secret or os.getenv("SNAPTRADE_USER_SECRET")

            if not user_id or not user_secret:
                return json.dumps({
                    "error": "Credentials required",
                    "message": "Provide user_id and user_secret, or set SNAPTRADE_USER_ID and SNAPTRADE_USER_SECRET"
                })

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

        except Exception as e:
            return json.dumps({
                "error": str(e),
                "message": "Failed to get connection URL"
            }, indent=2)

    @server.tool()
    def snaptrade_list_accounts(
        user_id: Optional[str] = None,
        user_secret: Optional[str] = None
    ) -> str:
        """
        List all connected brokerage accounts for a SnapTrade user.

        Returns account details including IDs, names, institutions, and current balances.

        Args:
            user_id: SnapTrade user ID. If not provided, uses SNAPTRADE_USER_ID env var.
            user_secret: SnapTrade user secret. If not provided, uses SNAPTRADE_USER_SECRET env var.

        Returns:
            JSON string containing list of connected accounts
        """
        snaptrade_client = get_snaptrade_client()
        if not snaptrade_client:
            return json.dumps({
                "error": "SnapTrade not configured"
            })

        try:
            user_id = user_id or os.getenv("SNAPTRADE_USER_ID")
            user_secret = user_secret or os.getenv("SNAPTRADE_USER_SECRET")

            if not user_id or not user_secret:
                return json.dumps({
                    "error": "Credentials required"
                })

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

        except Exception as e:
            return json.dumps({
                "error": str(e)
            }, indent=2)

    @server.tool()
    def snaptrade_get_holdings(
        account_id: str,
        user_id: Optional[str] = None,
        user_secret: Optional[str] = None
    ) -> str:
        """
        Get holdings/positions for a specific brokerage account.

        Returns detailed information about all positions including stocks, ETFs, options,
        and cryptocurrencies held in the account.

        Args:
            account_id: The SnapTrade account ID (UUID from snaptrade_list_accounts)
            user_id: SnapTrade user ID. If not provided, uses SNAPTRADE_USER_ID env var.
            user_secret: SnapTrade user secret. If not provided, uses SNAPTRADE_USER_SECRET env var.

        Returns:
            JSON string containing account holdings with positions and balances
        """
        snaptrade_client = get_snaptrade_client()
        if not snaptrade_client:
            return json.dumps({
                "error": "SnapTrade not configured"
            })

        try:
            user_id = user_id or os.getenv("SNAPTRADE_USER_ID")
            user_secret = user_secret or os.getenv("SNAPTRADE_USER_SECRET")

            if not user_id or not user_secret:
                return json.dumps({
                    "error": "Credentials required"
                })

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

        except Exception as e:
            return json.dumps({
                "error": str(e)
            }, indent=2)

    @server.tool()
    def snaptrade_get_transactions(
        account_id: str,
        start_date: str,
        end_date: str,
        user_id: Optional[str] = None,
        user_secret: Optional[str] = None,
        transaction_type: Optional[str] = None
    ) -> str:
        """
        Get transaction history for a brokerage account.

        Returns historical transactions including buys, sells, dividends, deposits, and withdrawals.
        Data is refreshed once daily. Results are paginated with max 1000 per request.

        Args:
            account_id: The SnapTrade account ID (UUID from snaptrade_list_accounts)
            start_date: Start date in YYYY-MM-DD format (e.g., "2024-01-01")
            end_date: End date in YYYY-MM-DD format (e.g., "2024-12-31")
            user_id: SnapTrade user ID. If not provided, uses SNAPTRADE_USER_ID env var.
            user_secret: SnapTrade user secret. If not provided, uses SNAPTRADE_USER_SECRET env var.
            transaction_type: Optional filter by type (e.g., "BUY,SELL,DIVIDEND")

        Returns:
            JSON string containing transaction history
        """
        snaptrade_client = get_snaptrade_client()
        if not snaptrade_client:
            return json.dumps({
                "error": "SnapTrade not configured"
            })

        try:
            user_id = user_id or os.getenv("SNAPTRADE_USER_ID")
            user_secret = user_secret or os.getenv("SNAPTRADE_USER_SECRET")

            if not user_id or not user_secret:
                return json.dumps({
                    "error": "Credentials required"
                })

            params = {
                "account_id": account_id,
                "user_id": user_id,
                "user_secret": user_secret,
                "start_date": start_date,
                "end_date": end_date
            }

            if transaction_type:
                params["type"] = transaction_type

            response = snaptrade_client.account_information.get_account_activities(**params)

            activities = response.body if hasattr(response, 'body') else response

            def safe_get(obj, key, default=None):
                if isinstance(obj, dict):
                    return obj.get(key, default)
                return getattr(obj, key, default)

            formatted_activities = []
            for activity in activities:
                if hasattr(activity, 'to_dict'):
                    activity = activity.to_dict()

                formatted_activities.append({
                    "id": safe_get(activity, "id"),
                    "type": safe_get(activity, "type"),
                    "symbol": safe_get(activity, "symbol"),
                    "description": safe_get(activity, "description"),
                    "trade_date": safe_get(activity, "trade_date"),
                    "settlement_date": safe_get(activity, "settlement_date"),
                    "units": safe_get(activity, "units"),
                    "price": safe_get(activity, "price"),
                    "amount": safe_get(activity, "amount"),
                    "currency": safe_get(activity, "currency"),
                    "fee": safe_get(activity, "fee"),
                    "institution": safe_get(activity, "institution")
                })

            return json.dumps({
                "success": True,
                "count": len(formatted_activities),
                "transactions": formatted_activities,
                "note": "Data refreshed once daily. Max 1000 transactions per request."
            }, indent=2)

        except Exception as e:
            return json.dumps({
                "error": str(e)
            }, indent=2)

    @server.tool()
    def snaptrade_disconnect_account(
        authorization_id: str,
        user_id: Optional[str] = None,
        user_secret: Optional[str] = None
    ) -> str:
        """
        Disconnect/remove a brokerage connection from SnapTrade.

        WARNING: This is irreversible! It will remove the brokerage connection and ALL
        associated accounts and holdings data from SnapTrade.

        Args:
            authorization_id: The brokerage authorization ID (get from snaptrade_list_accounts,
                             it's the 'brokerage_authorization' field in each account)
            user_id: SnapTrade user ID. If not provided, uses SNAPTRADE_USER_ID env var.
            user_secret: SnapTrade user secret. If not provided, uses SNAPTRADE_USER_SECRET env var.

        Returns:
            JSON string confirming disconnection or error message
        """
        snaptrade_client = get_snaptrade_client()
        if not snaptrade_client:
            return json.dumps({
                "error": "SnapTrade not configured"
            })

        try:
            user_id = user_id or os.getenv("SNAPTRADE_USER_ID")
            user_secret = user_secret or os.getenv("SNAPTRADE_USER_SECRET")

            if not user_id or not user_secret:
                return json.dumps({
                    "error": "Credentials required"
                })

            snaptrade_client.connections.remove_brokerage_authorization(
                authorization_id=authorization_id,
                user_id=user_id,
                user_secret=user_secret
            )

            return json.dumps({
                "success": True,
                "message": f"Brokerage connection {authorization_id} has been disconnected and all associated data removed."
            }, indent=2)

        except Exception as e:
            return json.dumps({
                "error": str(e)
            }, indent=2)

    @server.tool()
    def snaptrade_refresh_account(
        authorization_id: str,
        user_id: Optional[str] = None,
        user_secret: Optional[str] = None
    ) -> str:
        """
        Trigger a manual refresh of holdings data for a brokerage connection.

        SnapTrade syncs holdings once daily by default. Use this to force an immediate
        refresh of all accounts under a brokerage connection. The refresh is queued
        asynchronously - data may take a few moments to update.

        Args:
            authorization_id: The brokerage authorization ID (get from snaptrade_list_accounts,
                             it's the 'brokerage_authorization' field in each account)
            user_id: SnapTrade user ID. If not provided, uses SNAPTRADE_USER_ID env var.
            user_secret: SnapTrade user secret. If not provided, uses SNAPTRADE_USER_SECRET env var.

        Returns:
            JSON string confirming refresh has been scheduled

        Note: Each refresh call may incur additional charges depending on your SnapTrade plan.
        """
        snaptrade_client = get_snaptrade_client()
        if not snaptrade_client:
            return json.dumps({
                "error": "SnapTrade not configured"
            })

        try:
            user_id = user_id or os.getenv("SNAPTRADE_USER_ID")
            user_secret = user_secret or os.getenv("SNAPTRADE_USER_SECRET")

            if not user_id or not user_secret:
                return json.dumps({
                    "error": "Credentials required"
                })

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

        except Exception as e:
            return json.dumps({
                "error": str(e)
            }, indent=2)
