"""Reconciliation service — compare holdings vs transaction history."""

from typing import List, Dict, Optional
from db.database import get_db, rows_to_dicts


# Transaction types that ADD shares/units
ADDING_TYPES = {'buy', 'transfer_in', 'dividend_reinvest', 'stock_dividend', 'option_exercise', 'cover'}
# Transaction types that REMOVE shares/units
REMOVING_TYPES = {'sell', 'transfer_out', 'short', 'option_assignment'}


def reconcile_account(account_id: str) -> Dict:
    """
    Compare current holdings against sum of transactions for an account.
    
    Returns discrepancies where holdings qty != implied qty from transactions.
    """
    conn = get_db()
    cursor = conn.cursor()
    
    # Get current holdings for account
    cursor.execute("""
        SELECT symbol, quantity, market_value, asset_type, currency
        FROM holdings WHERE account_id = ?
    """, (account_id,))
    holdings = {row[0]: {
        "symbol": row[0],
        "holdings_qty": row[1],
        "market_value": row[2],
        "asset_type": row[3],
        "currency": row[4],
    } for row in cursor.fetchall()}
    
    # Get all transactions for account
    cursor.execute("""
        SELECT symbol, transaction_type, quantity
        FROM transactions WHERE account_id = ?
    """, (account_id,))
    
    # Compute implied quantities from transactions
    implied = {}
    for row in cursor.fetchall():
        symbol, txn_type, qty = row[0], row[1], row[2] or 0
        
        if symbol not in implied:
            implied[symbol] = 0.0
        
        if txn_type in ADDING_TYPES:
            implied[symbol] += abs(qty)
        elif txn_type in REMOVING_TYPES:
            implied[symbol] -= abs(qty)
        # Cash-only types (dividend, fee, interest, etc.) don't affect qty
    
    # Build discrepancy report
    all_symbols = set(list(holdings.keys()) + list(implied.keys()))
    discrepancies = []
    matched = []
    
    for symbol in sorted(all_symbols):
        h = holdings.get(symbol, {})
        holdings_qty = h.get("holdings_qty", 0) or 0
        implied_qty = round(implied.get(symbol, 0), 6)
        gap = round(holdings_qty - implied_qty, 6)
        
        entry = {
            "symbol": symbol,
            "holdings_qty": holdings_qty,
            "transactions_qty": implied_qty,
            "gap": gap,
            "asset_type": h.get("asset_type"),
            "currency": h.get("currency"),
        }
        
        if abs(gap) > 0.001:  # tolerance for floating point
            if implied_qty == 0 and holdings_qty != 0:
                entry["status"] = "missing_transactions"
                entry["note"] = f"Have {holdings_qty} shares but no buy/sell transactions"
            elif holdings_qty == 0 and implied_qty != 0:
                entry["status"] = "missing_holding"
                entry["note"] = f"Transactions imply {implied_qty} shares but no holding"
            else:
                entry["status"] = "quantity_mismatch"
                entry["note"] = f"Gap of {gap:+.4f} shares"
            discrepancies.append(entry)
        else:
            entry["status"] = "matched"
            matched.append(entry)
    
    return {
        "account_id": account_id,
        "total_symbols": len(all_symbols),
        "matched": len(matched),
        "discrepancies": len(discrepancies),
        "details": discrepancies,
        "matched_details": matched,
    }


def reconcile_user(user_id: str) -> Dict:
    """Reconcile all accounts for a user."""
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("SELECT id, name FROM accounts WHERE user_id = ?", (user_id,))
    accounts = cursor.fetchall()
    
    results = []
    total_discrepancies = 0
    
    for acc_id, acc_name in accounts:
        result = reconcile_account(acc_id)
        result["account_name"] = acc_name
        results.append(result)
        total_discrepancies += result["discrepancies"]
    
    return {
        "user_id": user_id,
        "accounts": len(results),
        "total_discrepancies": total_discrepancies,
        "results": results,
    }
