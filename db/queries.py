"""Database query functions for CRUD operations."""

import uuid
from datetime import datetime
from typing import Optional, List, Dict
import json
import secrets
import hashlib

from db.database import get_db, row_to_dict, rows_to_dicts


def _generate_id() -> str:
    """Generate a short unique ID (8 characters)."""
    return str(uuid.uuid4())[:8]


def get_or_create_default_user() -> str:
    """
    Get the default user ID, creating if needed.
    
    This helper ensures backward compatibility during the transition
    from single-user to multi-user architecture.
    
    Returns:
        User ID of the default user
    """
    user = get_user_by_email("default@vault.local")
    if user:
        return user["id"]
    return create_user("default@vault.local", "Default User")


# ============================================================================
# USER QUERIES
# ============================================================================

def create_user(email: str, name: Optional[str] = None) -> str:
    """
    Create a new user.
    
    Args:
        email: User email (must be unique)
        name: Optional user name
        
    Returns:
        User ID
        
    Raises:
        Exception: If email already exists
    """
    user_id = _generate_id()
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("""
        INSERT INTO users (id, email, name)
        VALUES (?, ?, ?)
    """, (user_id, email, name))
    
    conn.commit()
    return user_id


def get_user(user_id: str) -> Optional[Dict]:
    """Get user by ID."""
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
    row = cursor.fetchone()
    
    return row_to_dict(row)


def get_user_by_email(email: str) -> Optional[Dict]:
    """Get user by email."""
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("SELECT * FROM users WHERE email = ?", (email,))
    row = cursor.fetchone()
    
    return row_to_dict(row)


# ============================================================================
# API TOKEN QUERIES
# ============================================================================

def create_api_token(user_id: str, name: str = "default") -> str:
    """Create a new API token for a user. Returns the raw token string."""
    token = f"vault_{secrets.token_urlsafe(32)}"
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO api_tokens (token, user_id, name)
        VALUES (?, ?, ?)
    """, (token, user_id, name))
    conn.commit()
    return token


def get_user_by_token(token: str) -> Optional[Dict]:
    """Look up user by API token. Returns None if invalid/revoked."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT u.* FROM users u
        JOIN api_tokens t ON u.id = t.user_id
        WHERE t.token = ? AND t.revoked = 0
    """, (token,))
    row = cursor.fetchone()
    if row:
        # Update last_used_at
        cursor.execute("UPDATE api_tokens SET last_used_at = CURRENT_TIMESTAMP WHERE token = ?", (token,))
        conn.commit()
    return row_to_dict(row) if row else None


def revoke_token(token: str) -> bool:
    """Revoke an API token."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("UPDATE api_tokens SET revoked = 1 WHERE token = ?", (token,))
    conn.commit()
    return cursor.rowcount > 0


def list_user_tokens(user_id: str) -> List[Dict]:
    """List all tokens for a user (without revealing full token)."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT token, name, created_at, last_used_at, revoked
        FROM api_tokens WHERE user_id = ?
    """, (user_id,))
    rows = cursor.fetchall()
    result = []
    for row in rows_to_dicts(rows):
        # Mask token: show first 10 chars + last 4
        t = row["token"]
        row["token_masked"] = f"{t[:10]}...{t[-4:]}" if len(t) > 14 else "****"
        del row["token"]
        result.append(row)
    return result


def signup_user(email: str, name: str = None, password: str = None) -> tuple:
    """Create user + generate initial API token. Returns (user_id, token)."""
    # Check if email already exists
    existing = get_user_by_email(email)
    if existing:
        raise ValueError(f"Email '{email}' already registered")
    
    user_id = create_user(email, name)
    
    # Store password hash if provided
    if password:
        pw_hash = hashlib.sha256(password.encode()).hexdigest()
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET password_hash = ? WHERE id = ?", (pw_hash, user_id))
        conn.commit()
    
    token = create_api_token(user_id)
    return user_id, token


# ============================================================================
# BROKERAGE QUERIES
# ============================================================================

def upsert_brokerage(
    provider: str,
    provider_institution_id: str,
    name: str,
    logo_url: Optional[str] = None,
    supports_holdings: bool = True,
    supports_transactions: bool = True
) -> str:
    """
    Insert or update a brokerage.
    
    Args:
        provider: Provider name (e.g., 'snaptrade')
        provider_institution_id: Institution ID from provider
        name: Brokerage name
        logo_url: Optional logo URL
        supports_holdings: Whether brokerage supports holdings
        supports_transactions: Whether brokerage supports transactions
        
    Returns:
        Brokerage ID
    """
    conn = get_db()
    cursor = conn.cursor()
    
    # Check if exists
    cursor.execute("""
        SELECT id FROM brokerages 
        WHERE provider = ? AND provider_institution_id = ?
    """, (provider, provider_institution_id))
    
    existing = cursor.fetchone()
    
    if existing:
        # Update
        brokerage_id = existing[0]
        cursor.execute("""
            UPDATE brokerages
            SET name = ?, logo_url = ?, 
                supports_holdings = ?, supports_transactions = ?
            WHERE id = ?
        """, (name, logo_url, int(supports_holdings), int(supports_transactions), brokerage_id))
    else:
        # Insert
        brokerage_id = _generate_id()
        cursor.execute("""
            INSERT INTO brokerages 
            (id, provider, provider_institution_id, name, logo_url, 
             supports_holdings, supports_transactions)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (brokerage_id, provider, provider_institution_id, name, logo_url,
              int(supports_holdings), int(supports_transactions)))
    
    conn.commit()
    return brokerage_id


def get_brokerage(brokerage_id: str) -> Optional[Dict]:
    """Get brokerage by ID."""
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("SELECT * FROM brokerages WHERE id = ?", (brokerage_id,))
    row = cursor.fetchone()
    
    return row_to_dict(row)


# ============================================================================
# CONNECTION QUERIES
# ============================================================================

def create_connection(
    user_id: str,
    provider_account_id: str,
    brokerage_id: Optional[str] = None,
    status: str = "active",
    status_message: Optional[str] = None,
    metadata: Optional[Dict] = None
) -> str:
    """
    Create a new connection.
    
    Args:
        user_id: User ID
        provider_account_id: Account ID from provider
        brokerage_id: Optional brokerage ID
        status: Connection status (active, disabled, error)
        status_message: Optional status message
        metadata: Optional metadata dict (will be JSON encoded)
        
    Returns:
        Connection ID
    """
    connection_id = _generate_id()
    conn = get_db()
    cursor = conn.cursor()
    
    metadata_json = json.dumps(metadata) if metadata else None
    
    cursor.execute("""
        INSERT INTO connections 
        (id, user_id, brokerage_id, provider_account_id, status, status_message, metadata)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (connection_id, user_id, brokerage_id, provider_account_id, 
          status, status_message, metadata_json))
    
    conn.commit()
    return connection_id


def get_connections_for_user(user_id: str) -> List[Dict]:
    """Get all connections for a user."""
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("SELECT * FROM connections WHERE user_id = ?", (user_id,))
    rows = cursor.fetchall()
    
    return rows_to_dicts(rows)


def get_connection_by_provider_account_id(provider_account_id: str) -> Optional[Dict]:
    """Get connection by provider account ID."""
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT * FROM connections 
        WHERE provider_account_id = ?
    """, (provider_account_id,))
    row = cursor.fetchone()
    
    return row_to_dict(row)


def update_connection_status(
    connection_id: str,
    status: str,
    status_message: Optional[str] = None
) -> bool:
    """
    Update connection status.
    
    Args:
        connection_id: Connection ID
        status: New status
        status_message: Optional status message
        
    Returns:
        True if updated, False if not found
    """
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("""
        UPDATE connections
        SET status = ?, status_message = ?, updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
    """, (status, status_message, connection_id))
    
    conn.commit()
    return cursor.rowcount > 0


# ============================================================================
# ACCOUNT QUERIES
# ============================================================================

def create_account(
    user_id: str,
    name: str,
    account_id: Optional[str] = None,
    connection_id: Optional[str] = None,
    account_type: Optional[str] = None,
    currency: str = "USD",
    is_manual: bool = False,
    last_sync_at: Optional[str] = None
) -> str:
    """
    Create a new account.
    
    Args:
        user_id: User ID
        name: Account name
        account_id: Optional account ID (if None, generates random ID)
        connection_id: Optional connection ID
        account_type: Optional account type
        currency: Account currency
        is_manual: Whether this is a manual account
        last_sync_at: Optional last sync timestamp
        
    Returns:
        Account ID
    """
    if account_id is None:
        account_id = _generate_id()
    
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("""
        INSERT INTO accounts 
        (id, user_id, connection_id, name, account_type, currency, is_manual, last_sync_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (account_id, user_id, connection_id, name, account_type, 
          currency, int(is_manual), last_sync_at))
    
    conn.commit()
    return account_id


def get_account(account_id: str) -> Optional[Dict]:
    """Get account by ID."""
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("SELECT * FROM accounts WHERE id = ?", (account_id,))
    row = cursor.fetchone()
    
    return row_to_dict(row)


def get_accounts_for_user(user_id: str) -> List[Dict]:
    """Get all accounts for a user."""
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("SELECT * FROM accounts WHERE user_id = ?", (user_id,))
    rows = cursor.fetchall()
    
    return rows_to_dicts(rows)


def delete_account(account_id: str) -> bool:
    """
    Delete an account (cascades to holdings and transactions).
    
    Args:
        account_id: Account ID to delete
        
    Returns:
        True if deleted, False if not found
    """
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("DELETE FROM accounts WHERE id = ?", (account_id,))
    
    conn.commit()
    return cursor.rowcount > 0


def update_account(
    account_id: str,
    name: Optional[str] = None,
    last_sync_at: Optional[str] = None
) -> bool:
    """
    Update account fields.
    
    Args:
        account_id: Account ID
        name: Optional new name
        last_sync_at: Optional last sync timestamp
        
    Returns:
        True if updated, False if not found
    """
    conn = get_db()
    cursor = conn.cursor()
    
    updates = []
    params = []
    
    if name is not None:
        updates.append("name = ?")
        params.append(name)
    
    if last_sync_at is not None:
        updates.append("last_sync_at = ?")
        params.append(last_sync_at)
    
    if not updates:
        return False
    
    updates.append("updated_at = CURRENT_TIMESTAMP")
    params.append(account_id)
    
    sql = f"UPDATE accounts SET {', '.join(updates)} WHERE id = ?"
    cursor.execute(sql, params)
    
    conn.commit()
    return cursor.rowcount > 0


# ============================================================================
# HOLDING QUERIES
# ============================================================================

def upsert_holding(
    account_id: str,
    symbol: str,
    name: Optional[str] = None,
    quantity: Optional[float] = None,
    average_cost: Optional[float] = None,
    current_price: Optional[float] = None,
    market_value: Optional[float] = None,
    currency: str = "USD",
    asset_type: Optional[str] = None,
    metadata: Optional[Dict] = None
) -> str:
    """
    Insert or update a holding.
    
    Upserts based on account_id + symbol combination.
    
    Args:
        account_id: Account ID
        symbol: Ticker symbol
        name: Optional security name
        quantity: Number of shares/units
        average_cost: Average cost per unit
        current_price: Current price per unit
        market_value: Total market value
        currency: Currency code
        asset_type: Asset type (equity, etf, option, etc.)
        metadata: Optional metadata dict (will be JSON encoded)
        
    Returns:
        Holding ID
    """
    conn = get_db()
    cursor = conn.cursor()
    
    # Check if exists
    cursor.execute("""
        SELECT id FROM holdings 
        WHERE account_id = ? AND symbol = ?
    """, (account_id, symbol))
    
    existing = cursor.fetchone()
    metadata_json = json.dumps(metadata) if metadata else None
    
    if existing:
        # Update
        holding_id = existing[0]
        updates = []
        params = []
        
        if name is not None:
            updates.append("name = ?")
            params.append(name)
        
        if quantity is not None:
            updates.append("quantity = ?")
            params.append(quantity)
        
        if average_cost is not None:
            updates.append("average_cost = ?")
            params.append(average_cost)
        
        if current_price is not None:
            updates.append("current_price = ?")
            params.append(current_price)
        
        if market_value is not None:
            updates.append("market_value = ?")
            params.append(market_value)
        
        if currency is not None:
            updates.append("currency = ?")
            params.append(currency)
        
        if asset_type is not None:
            updates.append("asset_type = ?")
            params.append(asset_type)
        
        if metadata is not None:
            updates.append("metadata = ?")
            params.append(metadata_json)
        
        updates.append("updated_at = CURRENT_TIMESTAMP")
        params.append(holding_id)
        
        sql = f"UPDATE holdings SET {', '.join(updates)} WHERE id = ?"
        cursor.execute(sql, params)
    else:
        # Insert
        holding_id = _generate_id()
        cursor.execute("""
            INSERT INTO holdings 
            (id, account_id, symbol, name, quantity, average_cost, current_price, 
             market_value, currency, asset_type, metadata)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (holding_id, account_id, symbol, name, quantity, average_cost, 
              current_price, market_value, currency, asset_type, metadata_json))
    
    conn.commit()
    return holding_id


def get_holdings_for_account(account_id: str) -> List[Dict]:
    """Get all holdings for an account."""
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("SELECT * FROM holdings WHERE account_id = ?", (account_id,))
    rows = cursor.fetchall()
    
    return rows_to_dicts(rows)


def get_all_holdings_for_user(user_id: str) -> List[Dict]:
    """Get all holdings across all accounts for a user."""
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT h.* 
        FROM holdings h
        JOIN accounts a ON h.account_id = a.id
        WHERE a.user_id = ?
    """, (user_id,))
    rows = cursor.fetchall()
    
    return rows_to_dicts(rows)


def delete_holding(holding_id: str) -> bool:
    """
    Delete a holding.
    
    Args:
        holding_id: Holding ID to delete
        
    Returns:
        True if deleted, False if not found
    """
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("DELETE FROM holdings WHERE id = ?", (holding_id,))
    
    conn.commit()
    return cursor.rowcount > 0


def delete_stale_holdings(account_id: str, active_symbols: set) -> int:
    """
    Delete holdings not in the active_symbols set.
    
    This is used during sync to remove positions that no longer exist
    at the brokerage.
    
    Args:
        account_id: Account ID to clean up
        active_symbols: Set of symbols that should be kept
        
    Returns:
        Number of holdings deleted
    """
    conn = get_db()
    cursor = conn.cursor()
    
    if not active_symbols:
        # If no active symbols, delete all holdings for this account
        cursor.execute("DELETE FROM holdings WHERE account_id = ?", (account_id,))
    else:
        # Delete holdings whose symbols are not in the active set
        placeholders = ",".join("?" * len(active_symbols))
        cursor.execute(f"""
            DELETE FROM holdings 
            WHERE account_id = ? AND symbol NOT IN ({placeholders})
        """, [account_id] + list(active_symbols))
    
    deleted_count = cursor.rowcount
    conn.commit()
    return deleted_count


# ============================================================================
# TRANSACTION QUERIES
# ============================================================================

def get_transaction_by_external_id(external_id: str) -> Optional[Dict]:
    """
    Get transaction by external ID.
    
    Args:
        external_id: External ID to look up
        
    Returns:
        Transaction dict or None if not found
    """
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT * FROM transactions 
        WHERE external_id = ?
    """, (external_id,))
    row = cursor.fetchone()
    
    return row_to_dict(row)


def create_transaction(
    account_id: str,
    symbol: str,
    date: str,
    transaction_type: str,
    name: Optional[str] = None,
    quantity: Optional[float] = None,
    price: Optional[float] = None,
    fees: float = 0.0,
    currency: str = "USD",
    source: str = "manual",
    external_id: Optional[str] = None
) -> str:
    """
    Create a transaction.
    
    If external_id is provided, checks for existing transaction first to avoid duplicates.
    
    Args:
        account_id: Account ID
        symbol: Ticker symbol
        date: Transaction date (YYYY-MM-DD)
        transaction_type: Type (buy, sell, dividend, fee, etc.)
        name: Optional security name
        quantity: Number of shares/units
        price: Price per unit
        fees: Transaction fees
        currency: Currency code
        source: Source (manual, snaptrade, import)
        external_id: Optional external ID for deduplication
        
    Returns:
        Transaction ID
    """
    # Check for existing transaction if external_id provided
    if external_id:
        existing = get_transaction_by_external_id(external_id)
        if existing:
            return existing["id"]
    
    transaction_id = _generate_id()
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("""
        INSERT INTO transactions 
        (id, account_id, symbol, name, date, transaction_type, quantity, 
         price, fees, currency, source, external_id)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (transaction_id, account_id, symbol, name, date, transaction_type,
          quantity, price, fees, currency, source, external_id))
    
    conn.commit()
    return transaction_id


def get_transactions_for_account(account_id: str) -> List[Dict]:
    """Get all transactions for an account."""
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT * FROM transactions 
        WHERE account_id = ?
        ORDER BY date DESC
    """, (account_id,))
    rows = cursor.fetchall()
    
    return rows_to_dicts(rows)


def get_transactions_by_symbol(symbol: str, user_id: Optional[str] = None) -> List[Dict]:
    """
    Get transactions by symbol, optionally filtered by user.
    
    Args:
        symbol: Ticker symbol
        user_id: Optional user ID to filter by
        
    Returns:
        List of transactions
    """
    conn = get_db()
    cursor = conn.cursor()
    
    if user_id:
        cursor.execute("""
            SELECT t.* 
            FROM transactions t
            JOIN accounts a ON t.account_id = a.id
            WHERE t.symbol = ? AND a.user_id = ?
            ORDER BY t.date DESC
        """, (symbol, user_id))
    else:
        cursor.execute("""
            SELECT * FROM transactions 
            WHERE symbol = ?
            ORDER BY date DESC
        """, (symbol,))
    
    rows = cursor.fetchall()
    
    return rows_to_dicts(rows)


# ============================================================================
# CLASSIFICATION QUERIES
# ============================================================================

def upsert_classification(
    symbol: str,
    display_name: Optional[str] = None,
    category: Optional[str] = None,
    source: str = "manual"
) -> str:
    """
    Insert or update a classification.
    
    Args:
        symbol: Ticker symbol (primary key)
        display_name: Display name
        category: Category name
        source: Source (manual, perplexity, financedb)
        
    Returns:
        Symbol (used as ID)
    """
    conn = get_db()
    cursor = conn.cursor()
    
    # Check if exists
    cursor.execute("SELECT symbol FROM classifications WHERE symbol = ?", (symbol,))
    existing = cursor.fetchone()
    
    if existing:
        # Update
        updates = []
        params = []
        
        if display_name is not None:
            updates.append("display_name = ?")
            params.append(display_name)
        
        if category is not None:
            updates.append("category = ?")
            params.append(category)
        
        if source is not None:
            updates.append("source = ?")
            params.append(source)
        
        updates.append("updated_at = CURRENT_TIMESTAMP")
        params.append(symbol)
        
        sql = f"UPDATE classifications SET {', '.join(updates)} WHERE symbol = ?"
        cursor.execute(sql, params)
    else:
        # Insert
        cursor.execute("""
            INSERT INTO classifications (symbol, display_name, category, source)
            VALUES (?, ?, ?, ?)
        """, (symbol, display_name, category, source))
    
    conn.commit()
    return symbol


def get_classification(symbol: str) -> Optional[Dict]:
    """Get classification by symbol."""
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("SELECT * FROM classifications WHERE symbol = ?", (symbol,))
    row = cursor.fetchone()
    
    return row_to_dict(row)


def get_all_classifications() -> List[Dict]:
    """Get all classifications."""
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("SELECT * FROM classifications ORDER BY symbol")
    rows = cursor.fetchall()
    
    return rows_to_dicts(rows)


def get_classifications_by_category(category: str) -> List[Dict]:
    """Get all classifications in a category."""
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT * FROM classifications 
        WHERE category = ?
        ORDER BY symbol
    """, (category,))
    rows = cursor.fetchall()
    
    return rows_to_dicts(rows)


def delete_classification(symbol: str) -> bool:
    """
    Delete a classification.
    
    Args:
        symbol: Symbol to delete
        
    Returns:
        True if deleted, False if not found
    """
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("DELETE FROM classifications WHERE symbol = ?", (symbol,))
    
    conn.commit()
    return cursor.rowcount > 0


# ============================================================================
# WATCHLIST QUERIES
# ============================================================================

def create_watchlist(user_id: str, name: str) -> str:
    """
    Create a watchlist.
    
    Args:
        user_id: User ID
        name: Watchlist name
        
    Returns:
        Watchlist ID
    """
    watchlist_id = _generate_id()
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("""
        INSERT INTO watchlists (id, user_id, name)
        VALUES (?, ?, ?)
    """, (watchlist_id, user_id, name))
    
    conn.commit()
    return watchlist_id


def get_watchlists_for_user(user_id: str) -> List[Dict]:
    """Get all watchlists for a user."""
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("SELECT * FROM watchlists WHERE user_id = ?", (user_id,))
    rows = cursor.fetchall()
    
    return rows_to_dicts(rows)


def add_ticker_to_watchlist(watchlist_id: str, symbol: str) -> bool:
    """
    Add a ticker to a watchlist.
    
    Args:
        watchlist_id: Watchlist ID
        symbol: Ticker symbol
        
    Returns:
        True if added, False if already exists
    """
    conn = get_db()
    cursor = conn.cursor()
    
    try:
        cursor.execute("""
            INSERT INTO watchlist_tickers (watchlist_id, symbol)
            VALUES (?, ?)
        """, (watchlist_id, symbol))
        
        conn.commit()
        return True
    except Exception:
        # Already exists or other error
        return False


def remove_ticker_from_watchlist(watchlist_id: str, symbol: str) -> bool:
    """
    Remove a ticker from a watchlist.
    
    Args:
        watchlist_id: Watchlist ID
        symbol: Ticker symbol
        
    Returns:
        True if removed, False if not found
    """
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("""
        DELETE FROM watchlist_tickers 
        WHERE watchlist_id = ? AND symbol = ?
    """, (watchlist_id, symbol))
    
    conn.commit()
    return cursor.rowcount > 0


def get_watchlist_tickers(watchlist_id: str) -> List[str]:
    """
    Get all tickers in a watchlist.
    
    Args:
        watchlist_id: Watchlist ID
        
    Returns:
        List of ticker symbols
    """
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT symbol FROM watchlist_tickers 
        WHERE watchlist_id = ?
        ORDER BY added_at
    """, (watchlist_id,))
    
    rows = cursor.fetchall()
    return [row[0] for row in rows]


# ============================================================================
# DASHBOARD QUERIES
# ============================================================================

def create_dashboard(user_id: str, name: str, description: Optional[str] = None, layout: str = 'grid') -> str:
    """
    Create a new dashboard.
    
    Args:
        user_id: User ID
        name: Dashboard name
        description: Optional description
        layout: Layout type ('grid' or 'stack')
        
    Returns:
        Dashboard ID
    """
    dashboard_id = _generate_id()
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("""
        INSERT INTO dashboards (id, user_id, name, description, layout)
        VALUES (?, ?, ?, ?, ?)
    """, (dashboard_id, user_id, name, description, layout))
    
    conn.commit()
    return dashboard_id


def get_dashboard(dashboard_id: str) -> Optional[Dict]:
    """
    Get dashboard by ID.
    
    Args:
        dashboard_id: Dashboard ID
        
    Returns:
        Dashboard dict or None
    """
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("SELECT * FROM dashboards WHERE id = ?", (dashboard_id,))
    row = cursor.fetchone()
    
    return row_to_dict(row)


def list_dashboards(user_id: str) -> List[Dict]:
    """
    List all dashboards for a user.
    
    Args:
        user_id: User ID
        
    Returns:
        List of dashboard dicts
    """
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT * FROM dashboards 
        WHERE user_id = ? 
        ORDER BY created_at
    """, (user_id,))
    
    rows = cursor.fetchall()
    return rows_to_dicts(rows)


def update_dashboard(
    dashboard_id: str, 
    name: Optional[str] = None, 
    description: Optional[str] = None, 
    layout: Optional[str] = None,
    is_default: Optional[int] = None
) -> bool:
    """
    Update dashboard fields.
    
    Args:
        dashboard_id: Dashboard ID
        name: New name (optional)
        description: New description (optional)
        layout: New layout (optional)
        is_default: Set as default (optional)
        
    Returns:
        True if updated, False otherwise
    """
    conn = get_db()
    cursor = conn.cursor()
    
    # Build update query dynamically based on provided fields
    updates = []
    params = []
    
    if name is not None:
        updates.append("name = ?")
        params.append(name)
    
    if description is not None:
        updates.append("description = ?")
        params.append(description)
    
    if layout is not None:
        updates.append("layout = ?")
        params.append(layout)
    
    if is_default is not None:
        updates.append("is_default = ?")
        params.append(is_default)
    
    if not updates:
        return False
    
    updates.append("updated_at = CURRENT_TIMESTAMP")
    params.append(dashboard_id)
    
    query = f"UPDATE dashboards SET {', '.join(updates)} WHERE id = ?"
    cursor.execute(query, params)
    
    conn.commit()
    return cursor.rowcount > 0


def delete_dashboard(dashboard_id: str) -> bool:
    """
    Delete a dashboard (widgets are cascade deleted).
    
    Args:
        dashboard_id: Dashboard ID
        
    Returns:
        True if deleted, False otherwise
    """
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("DELETE FROM dashboards WHERE id = ?", (dashboard_id,))
    
    conn.commit()
    return cursor.rowcount > 0


# ============================================================================
# WIDGET QUERIES
# ============================================================================

def add_widget(
    dashboard_id: str,
    widget_type: str,
    config: str,
    title: Optional[str] = None,
    position: Optional[int] = None,
    width: int = 1,
    height: int = 1
) -> str:
    """
    Add a widget to a dashboard.
    
    Args:
        dashboard_id: Dashboard ID
        widget_type: Widget type
        config: JSON config string
        title: Optional title
        position: Position in dashboard (defaults to end)
        width: Grid width (1-4)
        height: Grid height
        
    Returns:
        Widget ID
    """
    widget_id = _generate_id()
    conn = get_db()
    cursor = conn.cursor()
    
    # If position not specified, add to end
    if position is None:
        cursor.execute("""
            SELECT COALESCE(MAX(position), -1) + 1 
            FROM dashboard_widgets 
            WHERE dashboard_id = ?
        """, (dashboard_id,))
        position = cursor.fetchone()[0]
    
    cursor.execute("""
        INSERT INTO dashboard_widgets 
        (id, dashboard_id, widget_type, title, config, position, width, height)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (widget_id, dashboard_id, widget_type, title, config, position, width, height))
    
    conn.commit()
    return widget_id


def get_widget(widget_id: str) -> Optional[Dict]:
    """
    Get widget by ID.
    
    Args:
        widget_id: Widget ID
        
    Returns:
        Widget dict or None
    """
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("SELECT * FROM dashboard_widgets WHERE id = ?", (widget_id,))
    row = cursor.fetchone()
    
    return row_to_dict(row)


def list_widgets(dashboard_id: str) -> List[Dict]:
    """
    List all widgets for a dashboard, ordered by position.
    
    Args:
        dashboard_id: Dashboard ID
        
    Returns:
        List of widget dicts
    """
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT * FROM dashboard_widgets 
        WHERE dashboard_id = ? 
        ORDER BY position
    """, (dashboard_id,))
    
    rows = cursor.fetchall()
    return rows_to_dicts(rows)


def update_widget(
    widget_id: str,
    title: Optional[str] = None,
    config: Optional[str] = None,
    position: Optional[int] = None,
    width: Optional[int] = None,
    height: Optional[int] = None
) -> bool:
    """
    Update widget fields.
    
    Args:
        widget_id: Widget ID
        title: New title (optional)
        config: New config JSON (optional)
        position: New position (optional)
        width: New width (optional)
        height: New height (optional)
        
    Returns:
        True if updated, False otherwise
    """
    conn = get_db()
    cursor = conn.cursor()
    
    # Build update query dynamically
    updates = []
    params = []
    
    if title is not None:
        updates.append("title = ?")
        params.append(title)
    
    if config is not None:
        updates.append("config = ?")
        params.append(config)
    
    if position is not None:
        updates.append("position = ?")
        params.append(position)
    
    if width is not None:
        updates.append("width = ?")
        params.append(width)
    
    if height is not None:
        updates.append("height = ?")
        params.append(height)
    
    if not updates:
        return False
    
    updates.append("updated_at = CURRENT_TIMESTAMP")
    params.append(widget_id)
    
    query = f"UPDATE dashboard_widgets SET {', '.join(updates)} WHERE id = ?"
    cursor.execute(query, params)
    
    conn.commit()
    return cursor.rowcount > 0


def delete_widget(widget_id: str) -> bool:
    """
    Delete a widget.
    
    Args:
        widget_id: Widget ID
        
    Returns:
        True if deleted, False otherwise
    """
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("DELETE FROM dashboard_widgets WHERE id = ?", (widget_id,))
    
    conn.commit()
    return cursor.rowcount > 0


def reorder_widgets(dashboard_id: str, widget_ids: list) -> bool:
    """
    Reorder widgets based on list order.
    
    Args:
        dashboard_id: Dashboard ID
        widget_ids: List of widget IDs in desired order
        
    Returns:
        True if reordered successfully
    """
    conn = get_db()
    cursor = conn.cursor()
    
    # Update position for each widget
    for position, widget_id in enumerate(widget_ids):
        cursor.execute("""
            UPDATE dashboard_widgets 
            SET position = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ? AND dashboard_id = ?
        """, (position, widget_id, dashboard_id))
    
    conn.commit()
    return True
