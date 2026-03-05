"""Tests for database schema and connection management."""

import os
import sqlite3
import tempfile
import pytest
from pathlib import Path


@pytest.fixture
def test_db():
    """Create a temporary test database."""
    with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.db') as f:
        db_path = f.name
    
    yield db_path
    
    # Cleanup
    if os.path.exists(db_path):
        os.unlink(db_path)


def test_schema_creates_all_tables(test_db):
    """Test that schema creates all expected tables."""
    from db.database import get_db
    
    # Set test database path
    os.environ['SUPERFINANCE_DB_PATH'] = test_db
    
    # Get database connection (should create schema)
    conn = get_db()
    cursor = conn.cursor()
    
    # Query for all tables
    cursor.execute("""
        SELECT name FROM sqlite_master 
        WHERE type='table' 
        ORDER BY name
    """)
    tables = [row[0] for row in cursor.fetchall()]
    
    # Verify all expected tables exist
    expected_tables = [
        'accounts',
        'api_tokens',
        'brokerages',
        'classifications',
        'connections',
        'dashboard_widgets',
        'dashboards',
        'holdings',
        'schema_version',
        'transactions',
        'users',
        'watchlist_tickers',
        'watchlists'
    ]
    
    for table in expected_tables:
        assert table in tables, f"Table '{table}' not found in database"
    
    conn.close()


def test_schema_is_idempotent(test_db):
    """Test that schema can be run multiple times without errors."""
    from db.database import get_db
    
    os.environ['SUPERFINANCE_DB_PATH'] = test_db
    
    # Create schema first time
    conn1 = get_db()
    conn1.close()
    
    # Run again - should not fail
    conn2 = get_db()
    cursor = conn2.cursor()
    
    cursor.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table'")
    count = cursor.fetchone()[0]
    
    assert count == 13, f"Expected 13 tables, got {count}"
    
    conn2.close()


def test_schema_version_tracking(test_db):
    """Test that schema version is tracked."""
    from db.database import get_db
    
    os.environ['SUPERFINANCE_DB_PATH'] = test_db
    
    conn = get_db()
    cursor = conn.cursor()
    
    # Check schema_version table exists and has version 1
    cursor.execute("SELECT version FROM schema_version ORDER BY version DESC LIMIT 1")
    result = cursor.fetchone()
    
    assert result is not None, "No schema version found"
    assert result[0] == 1, f"Expected version 1, got {result[0]}"
    
    conn.close()


def test_foreign_key_constraints_enabled(test_db):
    """Test that foreign key constraints are enabled."""
    from db.database import get_db
    
    os.environ['SUPERFINANCE_DB_PATH'] = test_db
    
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("PRAGMA foreign_keys")
    result = cursor.fetchone()
    
    assert result[0] == 1, "Foreign keys are not enabled"
    
    conn.close()


def test_indexes_created(test_db):
    """Test that all indexes are created."""
    from db.database import get_db
    
    os.environ['SUPERFINANCE_DB_PATH'] = test_db
    
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT name FROM sqlite_master 
        WHERE type='index' AND sql IS NOT NULL
        ORDER BY name
    """)
    indexes = [row[0] for row in cursor.fetchall()]
    
    expected_indexes = [
        'idx_accounts_user',
        'idx_api_tokens_user',
        'idx_connections_user',
        'idx_dashboards_user',
        'idx_holdings_account',
        'idx_holdings_symbol',
        'idx_transactions_account',
        'idx_transactions_date',
        'idx_transactions_symbol',
        'idx_widgets_dashboard'
    ]
    
    for index in expected_indexes:
        assert index in indexes, f"Index '{index}' not found"
    
    conn.close()
