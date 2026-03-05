"""SQLite database connection and schema management."""

import os
import sqlite3
from pathlib import Path
from typing import Optional, Any, List, Tuple


# Default database path - configurable via environment variable
DEFAULT_DB_PATH = "data/vault.db"


def get_db_path() -> str:
    """Get the database path from environment or use default."""
    return os.getenv('SUPERFINANCE_DB_PATH', DEFAULT_DB_PATH)


def init_db() -> None:
    """Initialize the database (create schema if needed)."""
    # Just call get_db() which will create schema if needed
    conn = get_db()
    conn.close()


def get_db() -> sqlite3.Connection:
    """
    Get database connection, creating schema if needed.
    
    Returns:
        sqlite3.Connection: Database connection with foreign keys enabled
    """
    db_path = get_db_path()
    
    # Create parent directory if it doesn't exist
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    
    # Check if database file exists (to know if we need to create schema)
    db_exists = os.path.exists(db_path)
    
    # Connect to database
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row  # Enable dict-like access
    
    # Enable foreign key constraints
    conn.execute("PRAGMA foreign_keys = ON")
    
    # Create schema if database is new
    if not db_exists or _needs_schema(conn):
        _create_schema(conn)
    else:
        # Run migrations for existing databases
        _run_migrations(conn)
    
    return conn


def _needs_schema(conn: sqlite3.Connection) -> bool:
    """Check if database needs schema creation."""
    cursor = conn.cursor()
    cursor.execute("""
        SELECT name FROM sqlite_master 
        WHERE type='table' AND name='schema_version'
    """)
    return cursor.fetchone() is None


def _create_schema(conn: sqlite3.Connection) -> None:
    """Create database schema from schema.sql file."""
    # Get path to schema.sql
    schema_path = Path(__file__).parent / 'schema.sql'
    
    # Read and execute schema
    with open(schema_path, 'r') as f:
        schema_sql = f.read()
    
    # Execute schema (split on semicolon to handle multiple statements)
    cursor = conn.cursor()
    cursor.executescript(schema_sql)
    
    # Run migrations for existing databases
    _run_migrations(conn)
    
    # Insert initial schema version if not exists
    cursor.execute("""
        INSERT OR IGNORE INTO schema_version (version) VALUES (1)
    """)
    
    conn.commit()


def _run_migrations(conn: sqlite3.Connection) -> None:
    """Run migrations for existing databases."""
    cursor = conn.cursor()
    
    # Migration 1: Add password_hash to users table if it doesn't exist
    cursor.execute("PRAGMA table_info(users)")
    columns = [row[1] for row in cursor.fetchall()]
    if 'password_hash' not in columns:
        cursor.execute("ALTER TABLE users ADD COLUMN password_hash TEXT")
    
    # Migration 2: Create api_tokens table if it doesn't exist
    cursor.execute("""
        SELECT name FROM sqlite_master 
        WHERE type='table' AND name='api_tokens'
    """)
    if not cursor.fetchone():
        cursor.execute("""
            CREATE TABLE api_tokens (
                token TEXT PRIMARY KEY,
                user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                name TEXT DEFAULT 'default',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_used_at TIMESTAMP,
                revoked INTEGER DEFAULT 0
            )
        """)
        cursor.execute("""
            CREATE INDEX idx_api_tokens_user ON api_tokens(user_id)
        """)
    
    # Migration 3: Create dashboards table if it doesn't exist
    cursor.execute("""
        SELECT name FROM sqlite_master 
        WHERE type='table' AND name='dashboards'
    """)
    if not cursor.fetchone():
        cursor.execute("""
            CREATE TABLE dashboards (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                name TEXT NOT NULL,
                description TEXT,
                is_default INTEGER DEFAULT 0,
                layout TEXT DEFAULT 'grid',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cursor.execute("""
            CREATE INDEX idx_dashboards_user ON dashboards(user_id)
        """)
    
    # Migration 4: Create dashboard_widgets table if it doesn't exist
    cursor.execute("""
        SELECT name FROM sqlite_master 
        WHERE type='table' AND name='dashboard_widgets'
    """)
    if not cursor.fetchone():
        cursor.execute("""
            CREATE TABLE dashboard_widgets (
                id TEXT PRIMARY KEY,
                dashboard_id TEXT NOT NULL REFERENCES dashboards(id) ON DELETE CASCADE,
                widget_type TEXT NOT NULL,
                title TEXT,
                config TEXT NOT NULL DEFAULT '{}',
                position INTEGER DEFAULT 0,
                width INTEGER DEFAULT 1,
                height INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cursor.execute("""
            CREATE INDEX idx_widgets_dashboard ON dashboard_widgets(dashboard_id)
        """)
    
    conn.commit()


def execute(sql: str, params: Optional[tuple] = None) -> sqlite3.Cursor:
    """
    Execute a SQL statement.
    
    Args:
        sql: SQL statement to execute
        params: Optional parameters for the SQL statement
        
    Returns:
        sqlite3.Cursor: Cursor with results
    """
    conn = get_db()
    cursor = conn.cursor()
    
    if params:
        cursor.execute(sql, params)
    else:
        cursor.execute(sql)
    
    conn.commit()
    return cursor


def fetch_one(sql: str, params: Optional[tuple] = None) -> Optional[sqlite3.Row]:
    """
    Fetch a single row from the database.
    
    Args:
        sql: SQL query
        params: Optional parameters
        
    Returns:
        Single row or None
    """
    conn = get_db()
    cursor = conn.cursor()
    
    if params:
        cursor.execute(sql, params)
    else:
        cursor.execute(sql)
    
    return cursor.fetchone()


def fetch_all(sql: str, params: Optional[tuple] = None) -> List[sqlite3.Row]:
    """
    Fetch all rows from the database.
    
    Args:
        sql: SQL query
        params: Optional parameters
        
    Returns:
        List of rows
    """
    conn = get_db()
    cursor = conn.cursor()
    
    if params:
        cursor.execute(sql, params)
    else:
        cursor.execute(sql)
    
    return cursor.fetchall()


def row_to_dict(row: Optional[sqlite3.Row]) -> Optional[dict]:
    """Convert a sqlite3.Row to a dictionary."""
    if row is None:
        return None
    return dict(row)


def rows_to_dicts(rows: List[sqlite3.Row]) -> List[dict]:
    """Convert a list of sqlite3.Row to a list of dictionaries."""
    return [dict(row) for row in rows]
