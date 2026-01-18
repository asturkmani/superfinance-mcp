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

    def _safe_get(obj, key, default=None):
        """Safely get a value from dict-like objects or SnapTrade schema objects."""
        if obj is None:
            return default
        # SnapTrade SDK objects support .get() directly
        if hasattr(obj, 'get'):
            try:
                val = obj.get(key)
                return val if val is not None else default
            except Exception:
                pass
        # Fallback to dict access
        if isinstance(obj, dict):
            return obj.get(key, default)
        # Fallback to attribute access
        return getattr(obj, key, default)

    def _extract_transaction(activity) -> dict:
        """Extract and format a transaction from SnapTrade activity."""
        safe_get = _safe_get

        # Extract nested symbol object
        symbol_obj = safe_get(activity, "symbol")
        symbol = None
        symbol_description = None
        if symbol_obj:
            symbol = safe_get(symbol_obj, "symbol")
            symbol_description = safe_get(symbol_obj, "description")

        # Extract nested option_symbol object
        option_symbol_obj = safe_get(activity, "option_symbol")
        option_symbol = None
        if option_symbol_obj:
            option_symbol = safe_get(option_symbol_obj, "description") or safe_get(option_symbol_obj, "id")

        # Extract nested currency object
        currency_obj = safe_get(activity, "currency")
        currency = None
        if currency_obj:
            currency = safe_get(currency_obj, "code")

        # Extract nested account object
        account_obj = safe_get(activity, "account")
        account_id = None
        account_name = None
        if account_obj:
            account_id = safe_get(account_obj, "id")
            account_name = safe_get(account_obj, "name")

        # Convert Decimal types to float for JSON serialization
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
            "option_symbol": option_symbol,
            "option_type": safe_get(activity, "option_type"),
            "description": safe_get(activity, "description"),
            "trade_date": str(safe_get(activity, "trade_date")) if safe_get(activity, "trade_date") else None,
            "settlement_date": str(safe_get(activity, "settlement_date")) if safe_get(activity, "settlement_date") else None,
            "units": to_float(safe_get(activity, "units")),
            "price": to_float(safe_get(activity, "price")),
            "amount": to_float(safe_get(activity, "amount")),
            "currency": currency,
            "fee": to_float(safe_get(activity, "fee")),
            "fx_rate": to_float(safe_get(activity, "fx_rate")),
            "institution": safe_get(activity, "institution"),
            "external_reference_id": safe_get(activity, "external_reference_id")
        }

    @server.tool()
    def snaptrade_get_transactions(
        account_id: str,
        start_date: str,
        end_date: str,
        user_id: Optional[str] = None,
        user_secret: Optional[str] = None,
        transaction_type: Optional[str] = None,
        limit: int = 25,
        offset: int = 0,
        summary_only: bool = False
    ) -> str:
        """
        Get transaction history for a brokerage account.

        Returns historical transactions including buys, sells, dividends, deposits, and withdrawals.
        By default returns only 25 most recent transactions to avoid context overflow.

        Args:
            account_id: The SnapTrade account ID (UUID from snaptrade_list_accounts)
            start_date: Start date in YYYY-MM-DD format (e.g., "2024-01-01")
            end_date: End date in YYYY-MM-DD format (e.g., "2024-12-31")
            user_id: SnapTrade user ID. If not provided, uses SNAPTRADE_USER_ID env var.
            user_secret: SnapTrade user secret. If not provided, uses SNAPTRADE_USER_SECRET env var.
            transaction_type: Optional filter by type (e.g., "BUY", "SELL", "DIVIDEND")
            limit: Max transactions to return (default 25, max 100). Use pagination for more.
            offset: Number of transactions to skip for pagination (default 0)
            summary_only: If True, returns only counts and totals without transaction details

        Returns:
            JSON with transaction history. Use summary_only=True for large date ranges.
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

            # Cap limit at 100 to prevent context overflow
            limit = min(limit, 100)

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

            # Extract the actual list and pagination from the response dict
            pagination_info = None
            if isinstance(activities, dict):
                pagination_info = activities.get("pagination", {})
                activities = activities.get("data", [])

            total_count = pagination_info.get("total", len(activities)) if pagination_info else len(activities)

            # If summary_only, return just counts without full transaction data
            if summary_only:
                # Group by type for summary
                by_type = {}
                total_amount = 0
                for a in activities:
                    t = _extract_transaction(a)
                    tx_type = t.get("type") or "UNKNOWN"
                    if tx_type not in by_type:
                        by_type[tx_type] = {"count": 0, "total_amount": 0}
                    by_type[tx_type]["count"] += 1
                    by_type[tx_type]["total_amount"] += t.get("amount") or 0
                    total_amount += t.get("amount") or 0

                return json.dumps({
                    "success": True,
                    "account_id": account_id,
                    "total_transactions": total_count,
                    "summary_by_type": by_type,
                    "net_amount": round(total_amount, 2),
                    "note": "Set summary_only=False and use limit/offset to view individual transactions"
                }, indent=2)

            # Apply pagination
            paginated = activities[offset:offset + limit]
            formatted_activities = [_extract_transaction(a) for a in paginated]

            return json.dumps({
                "success": True,
                "account_id": account_id,
                "showing": len(formatted_activities),
                "total_available": total_count,
                "pagination": {
                    "offset": offset,
                    "limit": limit,
                    "has_more": (offset + limit) < total_count
                },
                "transactions": formatted_activities,
                "tip": f"Use offset={offset + limit} to get next page" if (offset + limit) < total_count else None
            }, indent=2)

        except Exception as e:
            return json.dumps({
                "error": str(e)
            }, indent=2)

    @server.tool()
    def snaptrade_get_all_transactions(
        start_date: str,
        end_date: str,
        user_id: Optional[str] = None,
        user_secret: Optional[str] = None,
        transaction_type: Optional[str] = None,
        limit: int = 25,
        offset: int = 0,
        summary_only: bool = False
    ) -> str:
        """
        Get transactions across ALL connected brokerage accounts.

        By default returns only 25 most recent transactions to avoid context overflow.
        Use summary_only=True for large date ranges to get counts without details.

        Args:
            start_date: Start date in YYYY-MM-DD format (e.g., "2024-01-01")
            end_date: End date in YYYY-MM-DD format (e.g., "2024-12-31")
            user_id: SnapTrade user ID. If not provided, uses SNAPTRADE_USER_ID env var.
            user_secret: SnapTrade user secret. If not provided, uses SNAPTRADE_USER_SECRET env var.
            transaction_type: Optional filter by type (e.g., "BUY", "SELL", "DIVIDEND")
            limit: Max transactions to return (default 25, max 100). Use pagination for more.
            offset: Number of transactions to skip for pagination (default 0)
            summary_only: If True, returns only counts and totals without transaction details

        Returns:
            JSON with transactions and account summary. Use summary_only=True for overviews.
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

            # Cap limit at 100 to prevent context overflow
            limit = min(limit, 100)

            params = {
                "user_id": user_id,
                "user_secret": user_secret,
                "start_date": start_date,
                "end_date": end_date
            }

            if transaction_type:
                params["type"] = transaction_type

            response = snaptrade_client.transactions_and_reporting.get_activities(**params)
            activities = response.body if hasattr(response, 'body') else response

            # Extract the actual list from the response dict
            if isinstance(activities, dict):
                activities = activities.get("data", activities.get("activities", []))

            total_count = len(activities)

            # Build account and type summaries (always computed for context)
            by_account = {}
            by_type = {}
            total_amount = 0

            for a in activities:
                t = _extract_transaction(a)
                # Account summary
                acc_id = t.get("account_id") or "unknown"
                if acc_id not in by_account:
                    by_account[acc_id] = {
                        "account_name": t.get("account_name"),
                        "count": 0,
                        "total_amount": 0
                    }
                by_account[acc_id]["count"] += 1
                by_account[acc_id]["total_amount"] += t.get("amount") or 0

                # Type summary
                tx_type = t.get("type") or "UNKNOWN"
                if tx_type not in by_type:
                    by_type[tx_type] = {"count": 0, "total_amount": 0}
                by_type[tx_type]["count"] += 1
                by_type[tx_type]["total_amount"] += t.get("amount") or 0

                total_amount += t.get("amount") or 0

            # Round amounts in summaries
            for acc in by_account.values():
                acc["total_amount"] = round(acc["total_amount"], 2)
            for typ in by_type.values():
                typ["total_amount"] = round(typ["total_amount"], 2)

            # If summary_only, return just summaries without transaction details
            if summary_only:
                return json.dumps({
                    "success": True,
                    "total_transactions": total_count,
                    "net_amount": round(total_amount, 2),
                    "by_account": by_account,
                    "by_type": by_type,
                    "note": "Set summary_only=False and use limit/offset to view individual transactions"
                }, indent=2)

            # Apply pagination for full results
            paginated = activities[offset:offset + limit]
            formatted = [_extract_transaction(a) for a in paginated]

            return json.dumps({
                "success": True,
                "showing": len(formatted),
                "total_available": total_count,
                "pagination": {
                    "offset": offset,
                    "limit": limit,
                    "has_more": (offset + limit) < total_count
                },
                "accounts_summary": by_account,
                "transactions": formatted,
                "tip": f"Use offset={offset + limit} to get next page, or summary_only=True for overview" if (offset + limit) < total_count else None
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
