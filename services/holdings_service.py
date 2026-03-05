"""Holdings service - unified portfolio view from SQLite.

This service reads all holdings from SQLite (manual and synced).
SnapTrade sync writes to SQLite; this service only reads.
"""

from typing import Optional

from db import queries
from helpers.pricing import get_live_price, get_fx_rate_cached
from helpers.classification import get_classification


class HoldingsService:
    """Service class for unified holdings operations (read-only from SQLite)."""

    @staticmethod
    async def list_all_holdings(
        user_id: str,
        reporting_currency: Optional[str] = None
    ) -> dict:
        """
        Get all holdings for a user from SQLite.

        Args:
            user_id: User ID
            reporting_currency: Optional currency for conversion

        Returns:
            dict with unified holdings view
        """
        try:
            fx_cache = {}
            fx_rates_used = {}
            all_accounts = []

            # Grand totals by currency
            grand_holdings = {}
            grand_cash = {}
            grand_cost_basis = {}

            # Get all accounts for user
            accounts = queries.get_accounts_for_user(user_id)

            for account in accounts:
                account_id = account['id']
                
                # Get holdings for this account
                holdings = queries.get_holdings_for_account(account_id)
                
                # Account totals
                account_holdings = {}
                account_cost_basis = {}
                account_cash = {}  # TODO: Add cash tracking to schema if needed
                
                positions = []
                
                for holding in holdings:
                    symbol = holding.get('symbol')
                    name = holding.get('name')
                    units = holding.get('quantity', 0)
                    avg_cost = holding.get('average_cost', 0)
                    stored_price = holding.get('current_price')
                    currency = holding.get('currency', 'USD')
                    asset_type = holding.get('asset_type')
                    
                    # Get live price (prefer live over stored)
                    live_price = None
                    price_source = "none"
                    if symbol and symbol != "LIABILITY":
                        live_data = get_live_price(symbol)
                        if live_data.get("price"):
                            live_price = live_data["price"]
                            price_source = "yahoo_finance"
                    
                    # Fall back to stored price
                    if live_price is None and stored_price is not None:
                        live_price = stored_price
                        price_source = "manual"
                    
                    # Calculate values
                    market_value = units * live_price if units and live_price else None
                    cost_basis = units * avg_cost if units and avg_cost else 0
                    
                    pnl = None
                    pnl_pct = None
                    if market_value is not None and cost_basis != 0:
                        pnl = market_value - cost_basis
                        if cost_basis > 0:
                            pnl_pct = round((pnl / cost_basis) * 100, 2)
                    
                    # Get classification
                    classification = get_classification(symbol, name)
                    
                    pos_data = {
                        "id": holding.get('id'),
                        "symbol": symbol,
                        "name": name,
                        "consolidated_name": classification.get("name", name or symbol),
                        "category": classification.get("category", "Other"),
                        "units": round(units, 6) if units else 0,
                        "currency": currency,
                        "price": round(live_price, 2) if live_price else None,
                        "price_source": price_source,
                        "market_value": round(market_value, 2) if market_value else None,
                        "average_cost": round(avg_cost, 4) if avg_cost else None,
                        "cost_basis": round(cost_basis, 2) if cost_basis else None,
                        "unrealized_pnl": round(pnl, 2) if pnl else None,
                        "unrealized_pnl_pct": pnl_pct,
                        "asset_type": asset_type,
                        "notes": holding.get('metadata', {}).get('notes') if holding.get('metadata') else None
                    }
                    
                    # Track by currency
                    if currency and market_value:
                        account_holdings[currency] = account_holdings.get(currency, 0) + market_value
                        grand_holdings[currency] = grand_holdings.get(currency, 0) + market_value
                    if currency and cost_basis:
                        account_cost_basis[currency] = account_cost_basis.get(currency, 0) + cost_basis
                        grand_cost_basis[currency] = grand_cost_basis.get(currency, 0) + cost_basis
                    
                    # Add converted if reporting_currency
                    if reporting_currency and currency and currency != reporting_currency and market_value:
                        fx = get_fx_rate_cached(currency, reporting_currency, fx_cache)
                        if fx:
                            fx_rates_used[f"{currency}_{reporting_currency}"] = fx
                            pos_data["converted"] = {
                                "currency": reporting_currency,
                                "market_value": round(market_value * fx, 2),
                                "cost_basis": round(cost_basis * fx, 2) if cost_basis else None,
                                "unrealized_pnl": round(pnl * fx, 2) if pnl else None
                            }
                    
                    positions.append(pos_data)
                
                # Calculate account value (holdings + cash)
                account_value = {}
                for c, v in account_holdings.items():
                    account_value[c] = account_value.get(c, 0) + v
                for c, v in account_cash.items():
                    account_value[c] = account_value.get(c, 0) + v
                
                # Calculate unrealized P&L
                account_pnl = {}
                for c in account_holdings:
                    h = account_holdings.get(c, 0)
                    cb = account_cost_basis.get(c, 0)
                    if cb > 0:
                        account_pnl[c] = h - cb
                
                # Build account totals
                account_totals = {
                    "holdings": {k: round(v, 2) for k, v in account_holdings.items()},
                    "cash": {k: round(v, 2) for k, v in account_cash.items()},
                    "value": {k: round(v, 2) for k, v in account_value.items()},
                    "cost_basis": {k: round(v, 2) for k, v in account_cost_basis.items()},
                    "unrealized_pnl": {k: round(v, 2) for k, v in account_pnl.items()}
                }
                
                # Add converted totals if reporting_currency
                if reporting_currency:
                    conv = {
                        "currency": reporting_currency,
                        "holdings": 0,
                        "cash": 0,
                        "value": 0,
                        "cost_basis": 0,
                        "unrealized_pnl": 0
                    }
                    for c, v in account_holdings.items():
                        if c == reporting_currency:
                            conv["holdings"] += v
                        else:
                            fx = get_fx_rate_cached(c, reporting_currency, fx_cache)
                            if fx:
                                fx_rates_used[f"{c}_{reporting_currency}"] = fx
                                conv["holdings"] += v * fx
                    for c, v in account_cash.items():
                        if c == reporting_currency:
                            conv["cash"] += v
                        else:
                            fx = get_fx_rate_cached(c, reporting_currency, fx_cache)
                            if fx:
                                fx_rates_used[f"{c}_{reporting_currency}"] = fx
                                conv["cash"] += v * fx
                    for c, v in account_cost_basis.items():
                        if c == reporting_currency:
                            conv["cost_basis"] += v
                        else:
                            fx = fx_rates_used.get(f"{c}_{reporting_currency}")
                            if fx:
                                conv["cost_basis"] += v * fx
                    conv["value"] = conv["holdings"] + conv["cash"]
                    conv["unrealized_pnl"] = conv["holdings"] - conv["cost_basis"]
                    account_totals["converted"] = {
                        k: round(v, 2) if isinstance(v, float) else v
                        for k, v in conv.items()
                    }
                
                # Determine account source
                connection = None
                if account.get('connection_id'):
                    # This is a synced account
                    conn = queries.get_account(account['connection_id'])
                    if conn:
                        connection = conn.get('provider')
                
                source = "synced" if connection else "manual"
                
                account_data = {
                    "source": source,
                    "account_id": account_id,
                    "name": account['name'],
                    "account_type": account.get('account_type'),
                    "totals": account_totals,
                    "positions": positions,
                    "last_sync_at": account.get('last_sync_at')
                }
                
                if connection:
                    account_data["provider"] = connection
                
                all_accounts.append(account_data)
            
            # Build grand totals
            grand_value = {}
            for c, v in grand_holdings.items():
                grand_value[c] = grand_value.get(c, 0) + v
            for c, v in grand_cash.items():
                grand_value[c] = grand_value.get(c, 0) + v
            
            grand_pnl = {}
            for c in grand_holdings:
                h = grand_holdings.get(c, 0)
                cb = grand_cost_basis.get(c, 0)
                if cb > 0:
                    grand_pnl[c] = h - cb
            
            totals = {
                "holdings": {k: round(v, 2) for k, v in grand_holdings.items()},
                "cash": {k: round(v, 2) for k, v in grand_cash.items()},
                "value": {k: round(v, 2) for k, v in grand_value.items()},
                "cost_basis": {k: round(v, 2) for k, v in grand_cost_basis.items()},
                "unrealized_pnl": {k: round(v, 2) for k, v in grand_pnl.items()}
            }
            
            if reporting_currency:
                conv = {
                    "currency": reporting_currency,
                    "holdings": 0,
                    "cash": 0,
                    "value": 0,
                    "cost_basis": 0,
                    "unrealized_pnl": 0
                }
                for c, v in grand_holdings.items():
                    if c == reporting_currency:
                        conv["holdings"] += v
                    else:
                        fx = get_fx_rate_cached(c, reporting_currency, fx_cache)
                        if fx:
                            fx_rates_used[f"{c}_{reporting_currency}"] = fx
                            conv["holdings"] += v * fx
                for c, v in grand_cash.items():
                    if c == reporting_currency:
                        conv["cash"] += v
                    else:
                        fx = get_fx_rate_cached(c, reporting_currency, fx_cache)
                        if fx:
                            fx_rates_used[f"{c}_{reporting_currency}"] = fx
                            conv["cash"] += v * fx
                for c, v in grand_cost_basis.items():
                    if c == reporting_currency:
                        conv["cost_basis"] += v
                    else:
                        fx = fx_rates_used.get(f"{c}_{reporting_currency}")
                        if fx:
                            conv["cost_basis"] += v * fx
                conv["value"] = conv["holdings"] + conv["cash"]
                conv["unrealized_pnl"] = conv["holdings"] - conv["cost_basis"]
                totals["converted"] = {
                    k: round(v, 2) if isinstance(v, float) else v
                    for k, v in conv.items()
                }
            
            result = {
                "success": True,
                "accounts_count": len(all_accounts),
                "totals": totals,
                "accounts": all_accounts
            }
            
            if reporting_currency:
                result["reporting_currency"] = reporting_currency
                result["fx_rates"] = {k: round(v, 6) for k, v in fx_rates_used.items()}
            
            return result
            
        except Exception as e:
            return {"error": str(e)}
