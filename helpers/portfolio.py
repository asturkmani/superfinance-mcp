"""Portfolio helpers - SQLite-based portfolio operations.

This module provides backward-compatible helpers for the transition from JSON to SQLite.
New code should use db.queries directly.
"""

import uuid
from typing import Optional

from db import queries
from helpers.user_context import get_current_user_id


def generate_position_id() -> str:
    """Generate a unique position ID."""
    return str(uuid.uuid4())[:8]


def generate_liability_id() -> str:
    """Generate a unique liability ID with liab_ prefix."""
    return f"liab_{str(uuid.uuid4())[:8]}"


# =========================================================================
# BACKWARD COMPATIBILITY HELPERS
# =========================================================================
# These functions maintain API compatibility with the old JSON-based system
# while using SQLite under the hood.
# =========================================================================


def load_portfolios(user_id: Optional[str] = None) -> dict:
    """
    Load portfolios from SQLite (backward compatibility).
    
    Args:
        user_id: Optional user ID. If not provided, uses default user.
        
    Returns:
        dict with portfolios structure (compatible with old JSON format)
    """
    if not user_id:
        user_id = get_current_user_id()
    
    accounts = queries.get_accounts_for_user(user_id)
    
    portfolios = {}
    liabilities = {}
    
    for account in accounts:
        if account['is_manual']:
            # Get holdings for this account
            holdings = queries.get_holdings_for_account(account['id'])
            
            # Check if this is a liability (negative-value holdings)
            is_liability = False
            if holdings:
                # If any holding has negative quantity or market_value, treat as liability
                for h in holdings:
                    if (h.get('quantity') or 0) < 0 or (h.get('market_value') or 0) < 0:
                        is_liability = True
                        break
            
            # Convert holdings to old position format
            positions = []
            for h in holdings:
                pos = {
                    "id": h['id'],
                    "name": h['name'],
                    "symbol": h['symbol'],
                    "units": h['quantity'],
                    "average_cost": h['average_cost'],
                    "manual_price": h['current_price'],
                    "currency": h['currency'],
                    "asset_type": h['asset_type'],
                    "notes": h.get('metadata', {}).get('notes') if h.get('metadata') else None
                }
                positions.append(pos)
            
            if is_liability:
                # Store as liability
                # For liabilities, we use a single holding to represent the balance
                if holdings:
                    h = holdings[0]
                    liabilities[account['id']] = {
                        "id": account['id'],
                        "name": account['name'],
                        "type": account.get('account_type', 'other'),
                        "balance": abs(h.get('market_value', 0)),
                        "interest_rate": h.get('metadata', {}).get('interest_rate') if h.get('metadata') else None,
                        "currency": h['currency'],
                        "notes": h.get('metadata', {}).get('notes') if h.get('metadata') else None,
                        "created_at": account['created_at'],
                        "updated_at": account['updated_at']
                    }
            else:
                # Store as portfolio
                portfolios[account['id']] = {
                    "name": account['name'],
                    "description": account.get('account_type'),
                    "positions": positions,
                    "created_at": account['created_at'],
                    "updated_at": account['updated_at']
                }
    
    return {
        "portfolios": portfolios,
        "liabilities": liabilities
    }


# Note: save_portfolios() is removed - use db.queries directly for writes


# =========================================================================
# Liability Functions (backward compatibility)
# =========================================================================

def load_liabilities(user_id: Optional[str] = None) -> list[dict]:
    """Load all liabilities from SQLite."""
    data = load_portfolios(user_id)
    return list(data.get("liabilities", {}).values())


def get_liability(liability_id: str) -> dict | None:
    """Get a single liability by ID."""
    account = queries.get_account(liability_id)
    if not account:
        return None
    
    holdings = queries.get_holdings_for_account(liability_id)
    if not holdings:
        return None
    
    h = holdings[0]
    return {
        "id": account['id'],
        "name": account['name'],
        "type": account.get('account_type', 'other'),
        "balance": abs(h.get('market_value', 0)),
        "interest_rate": h.get('metadata', {}).get('interest_rate') if h.get('metadata') else None,
        "currency": h['currency'],
        "notes": h.get('metadata', {}).get('notes') if h.get('metadata') else None,
        "created_at": account['created_at'],
        "updated_at": account['updated_at']
    }


def save_liability(liability: dict, user_id: Optional[str] = None) -> dict:
    """
    Save a new liability.
    
    Args:
        liability: Dict with name, balance, type, interest_rate, currency, notes
        user_id: Optional user ID. If not provided, uses default user.
        
    Returns:
        Dict with success status and the created liability
    """
    try:
        if not user_id:
            user_id = get_current_user_id()
        
        liability_id = generate_liability_id()
        
        # Create account for the liability
        queries.create_account(
            user_id=user_id,
            name=liability.get("name"),
            account_type=liability.get("type", "other"),
            currency=liability.get("currency", "USD"),
            is_manual=True
        )
        
        # Override with custom ID
        from db.database import get_db
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE accounts SET id = ? WHERE id = (SELECT id FROM accounts WHERE user_id = ? ORDER BY created_at DESC LIMIT 1)",
            (liability_id, user_id)
        )
        conn.commit()
        
        # Create a holding to represent the liability balance (negative value)
        balance = float(liability.get("balance", 0))
        metadata = {}
        if liability.get("interest_rate"):
            metadata["interest_rate"] = liability["interest_rate"]
        if liability.get("notes"):
            metadata["notes"] = liability["notes"]
        
        queries.upsert_holding(
            account_id=liability_id,
            symbol="LIABILITY",
            name=liability.get("name"),
            quantity=1,
            average_cost=-balance,  # Negative to indicate liability
            market_value=-balance,
            currency=liability.get("currency", "USD"),
            asset_type="liability",
            metadata=metadata if metadata else None
        )
        
        return {
            "success": True,
            "liability": get_liability(liability_id)
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def update_liability(liability_id: str, updates: dict) -> dict:
    """
    Update an existing liability.
    
    Args:
        liability_id: The liability ID
        updates: Dict of fields to update (name, balance, type, interest_rate, notes)
        
    Returns:
        Dict with success status and updated liability
    """
    try:
        account = queries.get_account(liability_id)
        if not account:
            return {"success": False, "error": f"Liability '{liability_id}' not found"}
        
        # Update account if name or type changed
        if "name" in updates or "type" in updates:
            name = updates.get("name")
            account_type = updates.get("type")
            from db.database import get_db
            conn = get_db()
            cursor = conn.cursor()
            
            update_parts = []
            params = []
            if name:
                update_parts.append("name = ?")
                params.append(name)
            if account_type:
                update_parts.append("account_type = ?")
                params.append(account_type)
            
            if update_parts:
                update_parts.append("updated_at = CURRENT_TIMESTAMP")
                params.append(liability_id)
                cursor.execute(
                    f"UPDATE accounts SET {', '.join(update_parts)} WHERE id = ?",
                    params
                )
                conn.commit()
        
        # Update holding if balance, interest_rate, or notes changed
        holdings = queries.get_holdings_for_account(liability_id)
        if holdings:
            h = holdings[0]
            
            # Build metadata
            metadata = h.get('metadata', {}) or {}
            if "interest_rate" in updates:
                metadata["interest_rate"] = updates["interest_rate"]
            if "notes" in updates:
                metadata["notes"] = updates["notes"]
            
            # Update balance if provided
            if "balance" in updates:
                balance = float(updates["balance"])
                queries.upsert_holding(
                    account_id=liability_id,
                    symbol="LIABILITY",
                    name=updates.get("name", h['name']),
                    quantity=1,
                    average_cost=-balance,
                    market_value=-balance,
                    currency=h['currency'],
                    asset_type="liability",
                    metadata=metadata if metadata else None
                )
            elif metadata:
                # Just update metadata
                from db.database import get_db
                import json
                conn = get_db()
                cursor = conn.cursor()
                cursor.execute(
                    "UPDATE holdings SET metadata = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                    (json.dumps(metadata), h['id'])
                )
                conn.commit()
        
        return {"success": True, "liability": get_liability(liability_id)}
    except Exception as e:
        return {"success": False, "error": str(e)}


def delete_liability(liability_id: str) -> dict:
    """
    Delete a liability.
    
    Args:
        liability_id: The liability ID to delete
        
    Returns:
        Dict with success status
    """
    try:
        liability = get_liability(liability_id)
        if not liability:
            return {"success": False, "error": f"Liability '{liability_id}' not found"}
        
        queries.delete_account(liability_id)
        
        return {"success": True, "deleted": liability}
    except Exception as e:
        return {"success": False, "error": str(e)}
