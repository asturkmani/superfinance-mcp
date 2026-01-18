"""SnapTrade service - core business logic for brokerage integration."""

import os
from typing import Optional

from snaptrade_client import SnapTrade


# Singleton client
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


class SnapTradeService:
    """Service class for SnapTrade brokerage operations."""

    @staticmethod
    def _get_credentials(user_id: Optional[str], user_secret: Optional[str]) -> tuple:
        """Get credentials from params or environment."""
        user_id = user_id or os.getenv("SNAPTRADE_USER_ID")
        user_secret = user_secret or os.getenv("SNAPTRADE_USER_SECRET")
        return user_id, user_secret

    @staticmethod
    async def register_user(user_id: Optional[str] = None) -> dict:
        """
        Register a new SnapTrade user.

        Args:
            user_id: Unique user identifier

        Returns:
            dict with user_id and user_secret
        """
        client = get_snaptrade_client()
        if not client:
            return {
                "error": "SnapTrade not configured",
                "message": "Set SNAPTRADE_CONSUMER_KEY and SNAPTRADE_CLIENT_ID"
            }

        try:
            if not user_id:
                user_id = os.getenv("SNAPTRADE_USER_ID")
                if not user_id:
                    return {
                        "error": "user_id required",
                        "message": "Provide user_id or set SNAPTRADE_USER_ID"
                    }

            response = client.authentication.register_snap_trade_user(user_id=user_id)

            data = response.body if hasattr(response, 'body') else response
            if hasattr(data, 'to_dict'):
                data = data.to_dict()

            return {
                "success": True,
                "user_id": user_id,
                "user_secret": data.get("userSecret") if isinstance(data, dict) else getattr(data, 'user_secret', None),
                "message": "User registered. IMPORTANT: Save the user_secret!"
            }
        except Exception as e:
            return {"error": str(e)}

    @staticmethod
    async def get_connection_url(
        user_id: Optional[str] = None,
        user_secret: Optional[str] = None
    ) -> dict:
        """
        Get URL for connecting a brokerage account.

        Args:
            user_id: SnapTrade user ID
            user_secret: SnapTrade user secret

        Returns:
            dict with connection URL
        """
        client = get_snaptrade_client()
        if not client:
            return {"error": "SnapTrade not configured"}

        try:
            user_id, user_secret = SnapTradeService._get_credentials(user_id, user_secret)
            if not user_id or not user_secret:
                return {"error": "Credentials required"}

            response = client.authentication.login_snap_trade_user(
                user_id=user_id,
                user_secret=user_secret
            )

            data = response.body if hasattr(response, 'body') else response
            if hasattr(data, 'to_dict'):
                data = data.to_dict()

            redirect_uri = data.get("redirectURI") if isinstance(data, dict) else getattr(data, 'redirect_uri', None)

            return {
                "success": True,
                "connection_url": redirect_uri,
                "message": "Open this URL to connect your brokerage account"
            }
        except Exception as e:
            return {"error": str(e)}

    @staticmethod
    async def list_accounts(
        user_id: Optional[str] = None,
        user_secret: Optional[str] = None
    ) -> dict:
        """
        List all connected brokerage accounts.

        Args:
            user_id: SnapTrade user ID
            user_secret: SnapTrade user secret

        Returns:
            dict with list of accounts
        """
        client = get_snaptrade_client()
        if not client:
            return {"error": "SnapTrade not configured"}

        try:
            user_id, user_secret = SnapTradeService._get_credentials(user_id, user_secret)
            if not user_id or not user_secret:
                return {"error": "Credentials required"}

            response = client.account_information.list_user_accounts(
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

            return {
                "success": True,
                "count": len(formatted_accounts),
                "accounts": formatted_accounts
            }
        except Exception as e:
            return {"error": str(e)}

    @staticmethod
    async def get_holdings(
        account_id: str,
        user_id: Optional[str] = None,
        user_secret: Optional[str] = None
    ) -> dict:
        """
        Get holdings for a specific account.

        Args:
            account_id: The account ID
            user_id: SnapTrade user ID
            user_secret: SnapTrade user secret

        Returns:
            dict with account holdings
        """
        client = get_snaptrade_client()
        if not client:
            return {"error": "SnapTrade not configured"}

        try:
            user_id, user_secret = SnapTradeService._get_credentials(user_id, user_secret)
            if not user_id or not user_secret:
                return {"error": "Credentials required"}

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

            return result
        except Exception as e:
            return {"error": str(e)}

    @staticmethod
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

    @staticmethod
    def _extract_transaction(activity) -> dict:
        """Extract and format a transaction from SnapTrade activity."""
        safe_get = SnapTradeService._safe_get

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

    @staticmethod
    async def get_transactions(
        account_id: str,
        start_date: str,
        end_date: str,
        user_id: Optional[str] = None,
        user_secret: Optional[str] = None,
        transaction_type: Optional[str] = None,
        offset: Optional[int] = None,
        limit: Optional[int] = None
    ) -> dict:
        """
        Get transaction history for a specific account.

        Args:
            account_id: The account ID
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (YYYY-MM-DD)
            user_id: SnapTrade user ID
            user_secret: SnapTrade user secret
            transaction_type: Optional filter (e.g., "BUY", "SELL", "DIVIDEND")
            offset: Number of records to skip (for pagination)
            limit: Max records to return (default 100, max 1000)

        Returns:
            dict with transactions
        """
        client = get_snaptrade_client()
        if not client:
            return {"error": "SnapTrade not configured"}

        try:
            user_id, user_secret = SnapTradeService._get_credentials(user_id, user_secret)
            if not user_id or not user_secret:
                return {"error": "Credentials required"}

            params = {
                "account_id": account_id,
                "user_id": user_id,
                "user_secret": user_secret,
                "start_date": start_date,
                "end_date": end_date
            }

            if transaction_type:
                params["type"] = transaction_type
            if offset is not None:
                params["offset"] = offset
            if limit is not None:
                params["limit"] = limit

            response = client.account_information.get_account_activities(**params)
            activities = response.body if hasattr(response, 'body') else response

            # Extract the actual list from the response dict
            pagination_info = None
            if isinstance(activities, dict):
                # Response has keys: ['data', 'pagination']
                pagination_info = activities.get("pagination")
                activities = activities.get("data", [])

            formatted = [SnapTradeService._extract_transaction(a) for a in activities]

            return {
                "success": True,
                "account_id": account_id,
                "count": len(formatted),
                "transactions": formatted,
                "pagination": pagination_info or {
                    "offset": offset or 0,
                    "limit": limit,
                    "has_more": len(formatted) == (limit or 1000)
                }
            }
        except Exception as e:
            return {"error": str(e)}

    @staticmethod
    async def get_all_transactions(
        start_date: str,
        end_date: str,
        user_id: Optional[str] = None,
        user_secret: Optional[str] = None,
        accounts: Optional[str] = None,
        brokerage_authorizations: Optional[str] = None,
        transaction_type: Optional[str] = None
    ) -> dict:
        """
        Get transactions across all accounts.

        Args:
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (YYYY-MM-DD)
            user_id: SnapTrade user ID
            user_secret: SnapTrade user secret
            accounts: Optional comma-separated account IDs to filter
            brokerage_authorizations: Optional comma-separated auth IDs to filter
            transaction_type: Optional filter (e.g., "BUY", "SELL", "DIVIDEND")

        Returns:
            dict with transactions from all accounts
        """
        client = get_snaptrade_client()
        if not client:
            return {"error": "SnapTrade not configured"}

        try:
            user_id, user_secret = SnapTradeService._get_credentials(user_id, user_secret)
            if not user_id or not user_secret:
                return {"error": "Credentials required"}

            params = {
                "user_id": user_id,
                "user_secret": user_secret,
                "start_date": start_date,
                "end_date": end_date
            }

            if accounts:
                params["accounts"] = accounts
            if brokerage_authorizations:
                params["brokerage_authorizations"] = brokerage_authorizations
            if transaction_type:
                params["type"] = transaction_type

            response = client.transactions_and_reporting.get_activities(**params)
            activities = response.body if hasattr(response, 'body') else response

            # Extract the actual list from the response dict
            if isinstance(activities, dict):
                # Response has keys: ['data', 'pagination'] or similar
                activities = activities.get("data", activities.get("activities", []))

            formatted = [SnapTradeService._extract_transaction(a) for a in activities]

            # Group by account for summary
            by_account = {}
            for t in formatted:
                acc_id = t.get("account_id") or "unknown"
                if acc_id not in by_account:
                    by_account[acc_id] = {
                        "account_name": t.get("account_name"),
                        "count": 0
                    }
                by_account[acc_id]["count"] += 1

            return {
                "success": True,
                "total_count": len(formatted),
                "accounts_summary": by_account,
                "transactions": formatted
            }
        except Exception as e:
            return {"error": str(e)}

    @staticmethod
    async def disconnect_account(
        authorization_id: str,
        user_id: Optional[str] = None,
        user_secret: Optional[str] = None
    ) -> dict:
        """
        Disconnect a brokerage connection.

        Args:
            authorization_id: The brokerage authorization ID
            user_id: SnapTrade user ID
            user_secret: SnapTrade user secret

        Returns:
            dict confirming disconnection
        """
        client = get_snaptrade_client()
        if not client:
            return {"error": "SnapTrade not configured"}

        try:
            user_id, user_secret = SnapTradeService._get_credentials(user_id, user_secret)
            if not user_id or not user_secret:
                return {"error": "Credentials required"}

            client.connections.remove_brokerage_authorization(
                authorization_id=authorization_id,
                user_id=user_id,
                user_secret=user_secret
            )

            return {
                "success": True,
                "message": f"Connection {authorization_id} disconnected"
            }
        except Exception as e:
            return {"error": str(e)}

    @staticmethod
    async def refresh_account(
        authorization_id: str,
        user_id: Optional[str] = None,
        user_secret: Optional[str] = None
    ) -> dict:
        """
        Trigger a manual refresh of holdings data.

        Args:
            authorization_id: The brokerage authorization ID
            user_id: SnapTrade user ID
            user_secret: SnapTrade user secret

        Returns:
            dict confirming refresh scheduled
        """
        client = get_snaptrade_client()
        if not client:
            return {"error": "SnapTrade not configured"}

        try:
            user_id, user_secret = SnapTradeService._get_credentials(user_id, user_secret)
            if not user_id or not user_secret:
                return {"error": "Credentials required"}

            response = client.connections.refresh_brokerage_authorization(
                authorization_id=authorization_id,
                user_id=user_id,
                user_secret=user_secret
            )

            data = response.body if hasattr(response, 'body') else response
            if hasattr(data, 'to_dict'):
                data = data.to_dict()

            return {
                "success": True,
                "authorization_id": authorization_id,
                "message": "Refresh scheduled",
                "detail": data.get("detail") if isinstance(data, dict) else str(data)
            }
        except Exception as e:
            return {"error": str(e)}
