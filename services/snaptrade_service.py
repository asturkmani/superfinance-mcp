"""SnapTrade service - core business logic for brokerage integration."""

import os
import json
from typing import Optional
from datetime import datetime

from snaptrade_client import SnapTrade
from db import queries
from helpers.transaction_types import (
    map_snaptrade_type,
    get_option_multiplier,
    format_option_symbol,
    detect_short_or_cover
)


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
                    "meta": account.get("meta", {}),
                    "sync_status": account.get("sync_status", {}),
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
    async def get_option_positions(
        account_id: str,
        user_id: Optional[str] = None,
        user_secret: Optional[str] = None
    ) -> dict:
        """
        Get option positions for a specific account.
        
        Note: The SnapTrade API may include option positions in the regular
        get_user_holdings response. This method extracts them specifically.
        
        Args:
            account_id: The account ID
            user_id: SnapTrade user ID
            user_secret: SnapTrade user secret
            
        Returns:
            dict with option positions
        """
        client = get_snaptrade_client()
        if not client:
            return {"error": "SnapTrade not configured"}
        
        try:
            user_id, user_secret = SnapTradeService._get_credentials(user_id, user_secret)
            if not user_id or not user_secret:
                return {"error": "Credentials required"}
            
            # For now, use get_user_holdings and filter for options
            # The SnapTrade API typically includes options in the holdings response
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
            
            option_positions = []
            
            # First check the dedicated option_positions field
            raw_options = safe_get(holdings, "option_positions", [])
            for opt in raw_options:
                if hasattr(opt, 'to_dict'):
                    opt = opt.to_dict()
                option_positions.append(opt)
            
            # Also check regular positions for any with option_symbol
            if not option_positions:
                positions = safe_get(holdings, "positions", [])
                for position in positions:
                    if hasattr(position, 'to_dict'):
                        position = position.to_dict()
                    symbol_obj = safe_get(position, "symbol", {})
                    if hasattr(symbol_obj, 'to_dict'):
                        symbol_obj = symbol_obj.to_dict()
                    option_symbol = safe_get(symbol_obj, "option_symbol")
                    if option_symbol:
                        option_positions.append(position)
            
            return {
                "success": True,
                "option_positions": option_positions
            }
        except Exception as e:
            return {"error": str(e)}
    
    @staticmethod
    async def get_account_balances(
        account_id: str,
        user_id: Optional[str] = None,
        user_secret: Optional[str] = None
    ) -> dict:
        """
        Get account balances (cash positions).
        
        Args:
            account_id: The account ID
            user_id: SnapTrade user ID
            user_secret: SnapTrade user secret
            
        Returns:
            dict with account balances
        """
        client = get_snaptrade_client()
        if not client:
            return {"error": "SnapTrade not configured"}
        
        try:
            user_id, user_secret = SnapTradeService._get_credentials(user_id, user_secret)
            if not user_id or not user_secret:
                return {"error": "Credentials required"}
            
            # Use get_user_holdings which includes balances
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
            
            balances = safe_get(holdings, "balances", [])
            
            return {
                "success": True,
                "balances": balances
            }
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
        is_option = False
        
        if symbol_obj:
            symbol = safe_get(symbol_obj, "symbol")
            symbol_description = safe_get(symbol_obj, "description")
            
            # Check if this has option_symbol nested object
            option_symbol_obj = safe_get(symbol_obj, "option_symbol")
            if option_symbol_obj:
                is_option = True
                # Extract option details for symbol formatting
                underlying_obj = safe_get(option_symbol_obj, "underlying_symbol", {})
                underlying = safe_get(underlying_obj, "symbol", "UNKNOWN")
                strike = safe_get(option_symbol_obj, "strike_price")
                opt_type = safe_get(option_symbol_obj, "option_type")
                expiry = safe_get(option_symbol_obj, "expiration_date")
                ticker = safe_get(option_symbol_obj, "ticker")
                
                # Use formatted option symbol
                symbol = format_option_symbol(
                    underlying=underlying,
                    strike=strike,
                    option_type=opt_type,
                    expiry=expiry,
                    ticker=ticker
                )
                
                if not symbol_description and ticker:
                    symbol_description = ticker

        # Legacy: also check for option_symbol at activity level
        option_symbol_obj = safe_get(activity, "option_symbol")
        option_symbol = None
        if option_symbol_obj and not is_option:
            is_option = True
            option_symbol = safe_get(option_symbol_obj, "description") or safe_get(option_symbol_obj, "id")
            
            # Try to format symbol from option_symbol object
            underlying_obj = safe_get(option_symbol_obj, "underlying_symbol", {})
            underlying = safe_get(underlying_obj, "symbol", "UNKNOWN")
            strike = safe_get(option_symbol_obj, "strike_price")
            opt_type = safe_get(option_symbol_obj, "option_type")
            expiry = safe_get(option_symbol_obj, "expiration_date")
            ticker = safe_get(option_symbol_obj, "ticker")
            
            if not symbol:
                symbol = format_option_symbol(
                    underlying=underlying,
                    strike=strike,
                    option_type=opt_type,
                    expiry=expiry,
                    ticker=ticker
                )

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
            "is_option": is_option,
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

    @staticmethod
    async def sync_to_db(
        vault_user_id: str,
        snaptrade_user_id: Optional[str] = None,
        snaptrade_user_secret: Optional[str] = None
    ) -> dict:
        """
        Full sync: fetch accounts + holdings + transactions from SnapTrade, persist to SQLite.
        
        Args:
            vault_user_id: Vault user ID (for SQLite)
            snaptrade_user_id: SnapTrade user ID
            snaptrade_user_secret: SnapTrade user secret
            
        Returns:
            dict with sync summary
        """
        from datetime import timedelta
        
        client = get_snaptrade_client()
        if not client:
            return {"error": "SnapTrade not configured"}
        
        try:
            snaptrade_user_id, snaptrade_user_secret = SnapTradeService._get_credentials(
                snaptrade_user_id, snaptrade_user_secret
            )
            if not snaptrade_user_id or not snaptrade_user_secret:
                return {"error": "Credentials required"}
            
            # Fetch accounts
            accounts_result = await SnapTradeService.list_accounts(
                snaptrade_user_id, snaptrade_user_secret
            )
            
            if not accounts_result.get("success"):
                return accounts_result
            
            synced_accounts = 0
            synced_holdings = 0
            synced_transactions = 0
            cleaned_stale = 0
            errors = []
            
            for account_data in accounts_result.get("accounts", []):
                account_id = account_data.get("account_id")
                if not account_id:
                    continue
                
                try:
                    # Extract metadata
                    institution_name = account_data.get("institution", "Unknown")
                    brokerage_auth = account_data.get("brokerage_authorization")
                    meta = account_data.get("meta", {})
                    account_type = meta.get("type") if isinstance(meta, dict) else None
                    
                    # Extract sync_status from SnapTrade
                    sync_status = account_data.get("sync_status", {})
                    holdings_sync_info = sync_status.get("holdings", {}) if isinstance(sync_status, dict) else {}
                    transactions_sync_info = sync_status.get("transactions", {}) if isinstance(sync_status, dict) else {}
                    holdings_synced = bool(holdings_sync_info.get("initial_sync_completed", False))
                    transactions_synced = bool(transactions_sync_info.get("initial_sync_completed", False))
                    
                    # Extract currency from balance if available
                    balance_data = account_data.get("balance")
                    currency = "USD"  # default
                    if balance_data:
                        if isinstance(balance_data, dict):
                            currency = balance_data.get("currency", "USD")
                        elif hasattr(balance_data, "currency"):
                            currency = getattr(balance_data, "currency", "USD")
                    
                    # Upsert brokerage
                    brokerage_id = queries.upsert_brokerage(
                        provider="snaptrade",
                        provider_institution_id=institution_name,
                        name=institution_name
                    )
                    
                    # Create or get connection (using brokerage_authorization as provider_account_id)
                    connection_id = None
                    if brokerage_auth:
                        existing_connection = queries.get_connection_by_provider_account_id(brokerage_auth)
                        if existing_connection:
                            connection_id = existing_connection["id"]
                        else:
                            connection_id = queries.create_connection(
                                user_id=vault_user_id,
                                provider_account_id=brokerage_auth,
                                brokerage_id=brokerage_id,
                                status="active"
                            )
                    
                    # Create or update account in SQLite
                    existing = queries.get_account(account_id)
                    now = datetime.utcnow().isoformat() + "Z"
                    if existing:
                        # Update sync flags and timestamp
                        from db.database import get_db
                        conn = get_db()
                        cursor = conn.cursor()
                        cursor.execute("""
                            UPDATE accounts 
                            SET holdings_synced = ?, transactions_synced = ?, 
                                last_sync_at = ?, updated_at = CURRENT_TIMESTAMP
                            WHERE id = ?
                        """, (int(holdings_synced), int(transactions_synced), now, account_id))
                        conn.commit()
                    else:
                        # Create new account with SnapTrade account ID directly
                        queries.create_account(
                            user_id=vault_user_id,
                            name=account_data.get("name", "Unknown Account"),
                            account_id=account_id,
                            connection_id=connection_id,
                            account_type=account_type,
                            currency=currency,
                            is_manual=False,
                            last_sync_at=now
                        )
                        # Set sync flags
                        from db.database import get_db
                        conn = get_db()
                        cursor = conn.cursor()
                        cursor.execute("""
                            UPDATE accounts 
                            SET holdings_synced = ?, transactions_synced = ?
                            WHERE id = ?
                        """, (int(holdings_synced), int(transactions_synced), account_id))
                        conn.commit()
                    
                    synced_accounts += 1
                    
                    # Fetch and persist holdings (equity positions)
                    holdings_result = await SnapTradeService.get_holdings(
                        account_id, snaptrade_user_id, snaptrade_user_secret
                    )
                    
                    seen_symbols = set()
                    
                    if holdings_result.get("success"):
                        for position in holdings_result.get("positions", []):
                            # symbol can be a nested dict from SnapTrade API
                            raw_symbol = position.get("symbol")
                            if not raw_symbol:
                                continue
                            
                            # Extract ticker string and metadata from nested dict
                            if isinstance(raw_symbol, dict):
                                symbol = raw_symbol.get("symbol") or raw_symbol.get("raw_symbol")
                                description = raw_symbol.get("description")
                                currency_obj = raw_symbol.get("currency")
                                pos_currency = currency_obj.get("code") if isinstance(currency_obj, dict) else "USD"
                                asset_type_obj = raw_symbol.get("type")
                                asset_type = asset_type_obj.get("description") if isinstance(asset_type_obj, dict) else None
                            else:
                                symbol = raw_symbol
                                description = position.get("description")
                                pos_currency = position.get("currency", "USD")
                                asset_type = None
                            
                            if not symbol:
                                continue
                            
                            seen_symbols.add(symbol)
                            
                            # Extract values
                            quantity = position.get("units") or position.get("fractional_units")
                            current_price = position.get("price")
                            
                            # Compute market_value
                            market_value = None
                            if quantity is not None and current_price is not None:
                                market_value = quantity * current_price
                            
                            # Try to extract average_cost from open_pnl if available
                            average_cost = None
                            open_pnl = position.get("open_pnl")
                            if open_pnl is not None and quantity is not None and quantity != 0:
                                if current_price is not None:
                                    average_cost = current_price - (open_pnl / quantity)
                            
                            queries.upsert_holding(
                                account_id=account_id,
                                symbol=symbol,
                                name=description,
                                quantity=quantity,
                                average_cost=average_cost,
                                current_price=current_price,
                                market_value=market_value,
                                currency=pos_currency,
                                asset_type=asset_type
                            )
                            synced_holdings += 1
                    
                    # Fetch and persist option positions
                    options_result = await SnapTradeService.get_option_positions(
                        account_id, snaptrade_user_id, snaptrade_user_secret
                    )
                    
                    if options_result.get("success"):
                        for position in options_result.get("option_positions", []):
                            raw_symbol = position.get("symbol")
                            if not raw_symbol:
                                continue
                            
                            # Extract option symbol object
                            if isinstance(raw_symbol, dict):
                                option_symbol_obj = raw_symbol.get("option_symbol")
                                if not option_symbol_obj:
                                    continue
                                
                                # Extract option details
                                underlying_obj = option_symbol_obj.get("underlying_symbol", {})
                                underlying = underlying_obj.get("symbol", "UNKNOWN") if isinstance(underlying_obj, dict) else "UNKNOWN"
                                strike = option_symbol_obj.get("strike_price")
                                opt_type = option_symbol_obj.get("option_type")  # 'CALL' or 'PUT'
                                expiry = option_symbol_obj.get("expiration_date")
                                ticker = option_symbol_obj.get("ticker")
                                is_mini = option_symbol_obj.get("is_mini_option", False)
                                
                                # Format symbol
                                symbol = format_option_symbol(
                                    underlying=underlying,
                                    strike=strike,
                                    option_type=opt_type,
                                    expiry=expiry,
                                    ticker=ticker
                                )
                                
                                description = ticker or symbol
                                currency_obj = raw_symbol.get("currency")
                                pos_currency = currency_obj.get("code") if isinstance(currency_obj, dict) else "USD"
                            else:
                                continue
                            
                            seen_symbols.add(symbol)
                            
                            # Extract values
                            quantity = position.get("units") or position.get("fractional_units")
                            current_price = position.get("price")
                            
                            # Compute market_value with option multiplier
                            market_value = None
                            if quantity is not None and current_price is not None:
                                multiplier = get_option_multiplier(is_mini)
                                market_value = quantity * current_price * multiplier
                            
                            # Try to extract average_cost from open_pnl
                            average_cost = None
                            open_pnl = position.get("open_pnl")
                            if open_pnl is not None and quantity is not None and quantity != 0:
                                if current_price is not None:
                                    multiplier = get_option_multiplier(is_mini)
                                    average_cost = current_price - (open_pnl / (quantity * multiplier))
                            
                            # Store option metadata
                            metadata = {
                                "underlying_symbol": underlying,
                                "strike": strike,
                                "option_type": opt_type,
                                "expiration_date": expiry,
                                "is_mini_option": is_mini
                            }
                            
                            queries.upsert_holding(
                                account_id=account_id,
                                symbol=symbol,
                                name=description,
                                quantity=quantity,
                                average_cost=average_cost,
                                current_price=current_price,
                                market_value=market_value,
                                currency=pos_currency,
                                asset_type='option',
                                metadata=metadata
                            )
                            synced_holdings += 1
                    
                    # Fetch and persist cash balances
                    balances_result = await SnapTradeService.get_account_balances(
                        account_id, snaptrade_user_id, snaptrade_user_secret
                    )
                    
                    if balances_result.get("success"):
                        for balance in balances_result.get("balances", []):
                            # Extract cash amount
                            cash = balance.get("cash") if isinstance(balance, dict) else getattr(balance, "cash", None)
                            if not cash or cash == 0:
                                continue
                            
                            # Extract currency
                            currency_obj = balance.get("currency") if isinstance(balance, dict) else getattr(balance, "currency", None)
                            if isinstance(currency_obj, dict):
                                currency_code = currency_obj.get("code", "USD")
                            elif currency_obj:
                                currency_code = getattr(currency_obj, "code", "USD")
                            else:
                                currency_code = "USD"
                            
                            # Create cash holding
                            symbol = currency_code
                            seen_symbols.add(symbol)
                            
                            queries.upsert_holding(
                                account_id=account_id,
                                symbol=symbol,
                                name=f"{currency_code} Cash",
                                quantity=cash,
                                average_cost=1.0,
                                current_price=1.0,
                                market_value=cash,
                                currency=currency_code,
                                asset_type='cash'
                            )
                            synced_holdings += 1
                    
                    # Remove stale holdings (positions that no longer exist at broker)
                    deleted = queries.delete_stale_holdings(account_id, seen_symbols)
                    cleaned_stale += deleted
                    
                    # Fetch and persist transactions (full history, paginated)
                    end_date = datetime.utcnow().strftime("%Y-%m-%d")
                    start_date = "2020-01-01"
                    
                    all_transactions = []
                    offset = 0
                    page_size = 1000
                    while True:
                        txn_result = await SnapTradeService.get_transactions(
                            account_id, start_date, end_date,
                            snaptrade_user_id, snaptrade_user_secret,
                            offset=offset, limit=page_size
                        )
                        if not txn_result.get("success"):
                            break
                        page = txn_result.get("transactions", [])
                        all_transactions.extend(page)
                        if len(page) < page_size:
                            break
                        offset += page_size
                    
                    for txn in all_transactions:
                            # Determine external_id for deduplication
                            external_id = txn.get("id") or txn.get("external_reference_id")
                            
                            # Skip if no symbol (some transactions like deposits don't have symbols)
                            symbol = txn.get("symbol")
                            if not symbol:
                                symbol = "CASH"  # Use placeholder for cash transactions
                            
                            # Extract transaction date
                            txn_date = txn.get("trade_date")
                            if not txn_date:
                                txn_date = txn.get("settlement_date")
                            if not txn_date:
                                continue  # Skip if no date
                            
                            # Convert to YYYY-MM-DD format
                            if isinstance(txn_date, str):
                                txn_date = txn_date.split("T")[0]  # Remove time portion if present
                            
                            # Map SnapTrade transaction type to canonical type
                            st_type = txn.get("type", "")
                            transaction_type = map_snaptrade_type(st_type)
                            
                            # Detect short/cover based on quantity
                            quantity = txn.get("units")
                            is_option = txn.get("is_option", False)
                            transaction_type = detect_short_or_cover(
                                transaction_type,
                                quantity,
                                is_option
                            )
                            
                            # Create transaction (will deduplicate based on external_id)
                            queries.create_transaction(
                                account_id=account_id,
                                symbol=symbol,
                                date=txn_date,
                                transaction_type=transaction_type,
                                name=txn.get("symbol_description"),
                                quantity=abs(quantity) if quantity else None,  # Store absolute value
                                price=txn.get("price"),
                                fees=txn.get("fee") or 0.0,
                                currency=txn.get("currency", "USD"),
                                source="snaptrade",
                                external_id=external_id
                            )
                            synced_transactions += 1
                    
                except Exception as e:
                    errors.append(f"Account {account_id}: {str(e)}")
            
            result = {
                "success": True,
                "synced_accounts": synced_accounts,
                "synced_holdings": synced_holdings,
                "synced_transactions": synced_transactions,
                "cleaned_stale_holdings": cleaned_stale,
                "timestamp": datetime.utcnow().isoformat() + "Z"
            }
            
            if errors:
                result["errors"] = errors
            
            return result
            
        except Exception as e:
            return {"error": str(e)}
