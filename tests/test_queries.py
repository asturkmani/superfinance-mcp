"""Tests for database queries."""

import os
import tempfile
import pytest
from datetime import datetime
from pathlib import Path


@pytest.fixture
def test_db():
    """Create a temporary test database."""
    with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.db') as f:
        db_path = f.name
    
    os.environ['SUPERFINANCE_DB_PATH'] = db_path
    
    yield db_path
    
    # Cleanup
    if os.path.exists(db_path):
        os.unlink(db_path)


def test_create_and_get_user(test_db):
    """Test creating and retrieving a user."""
    from db import queries
    
    # Create user
    user_id = queries.create_user(email="test@example.com", name="Test User")
    assert user_id is not None
    
    # Get user by ID
    user = queries.get_user(user_id)
    assert user is not None
    assert user['email'] == "test@example.com"
    assert user['name'] == "Test User"
    
    # Get user by email
    user_by_email = queries.get_user_by_email("test@example.com")
    assert user_by_email is not None
    assert user_by_email['id'] == user_id


def test_create_duplicate_email_fails(test_db):
    """Test that creating a user with duplicate email fails."""
    from db import queries
    
    queries.create_user(email="dupe@example.com", name="User 1")
    
    # Should raise an error
    with pytest.raises(Exception):
        queries.create_user(email="dupe@example.com", name="User 2")


def test_upsert_brokerage(test_db):
    """Test upserting a brokerage."""
    from db import queries
    
    # First insert
    brokerage_id = queries.upsert_brokerage(
        provider="snaptrade",
        provider_institution_id="INST123",
        name="Test Brokerage",
        logo_url="https://example.com/logo.png"
    )
    assert brokerage_id is not None
    
    # Get brokerage
    brokerage = queries.get_brokerage(brokerage_id)
    assert brokerage is not None
    assert brokerage['name'] == "Test Brokerage"
    assert brokerage['provider'] == "snaptrade"
    
    # Upsert again with same provider + institution_id (should update)
    brokerage_id_2 = queries.upsert_brokerage(
        provider="snaptrade",
        provider_institution_id="INST123",
        name="Updated Brokerage"
    )
    
    # Should be same ID
    assert brokerage_id_2 == brokerage_id
    
    # Check name was updated
    updated = queries.get_brokerage(brokerage_id)
    assert updated['name'] == "Updated Brokerage"


def test_create_account(test_db):
    """Test creating an account."""
    from db import queries
    
    # Create user first
    user_id = queries.create_user(email="user@example.com", name="User")
    
    # Create manual account
    account_id = queries.create_account(
        user_id=user_id,
        name="My Portfolio",
        account_type="brokerage",
        currency="USD",
        is_manual=True
    )
    assert account_id is not None
    
    # Get account
    account = queries.get_account(account_id)
    assert account is not None
    assert account['name'] == "My Portfolio"
    assert account['user_id'] == user_id
    assert account['is_manual'] == 1


def test_get_accounts_for_user(test_db):
    """Test retrieving all accounts for a user."""
    from db import queries
    
    user_id = queries.create_user(email="user@example.com", name="User")
    
    # Create multiple accounts
    acc1 = queries.create_account(user_id=user_id, name="Portfolio 1", is_manual=True)
    acc2 = queries.create_account(user_id=user_id, name="Portfolio 2", is_manual=True)
    
    # Get all accounts
    accounts = queries.get_accounts_for_user(user_id)
    assert len(accounts) == 2
    
    account_names = [acc['name'] for acc in accounts]
    assert "Portfolio 1" in account_names
    assert "Portfolio 2" in account_names


def test_multi_user_isolation(test_db):
    """Test that user A cannot see user B's accounts."""
    from db import queries
    
    # Create two users
    user_a_id = queries.create_user(email="usera@example.com", name="User A")
    user_b_id = queries.create_user(email="userb@example.com", name="User B")
    
    # Create accounts for each user
    acc_a = queries.create_account(user_id=user_a_id, name="A's Account", is_manual=True)
    acc_b = queries.create_account(user_id=user_b_id, name="B's Account", is_manual=True)
    
    # User A should only see their account
    accounts_a = queries.get_accounts_for_user(user_a_id)
    assert len(accounts_a) == 1
    assert accounts_a[0]['name'] == "A's Account"
    
    # User B should only see their account
    accounts_b = queries.get_accounts_for_user(user_b_id)
    assert len(accounts_b) == 1
    assert accounts_b[0]['name'] == "B's Account"


def test_upsert_holding(test_db):
    """Test upserting a holding."""
    from db import queries
    
    user_id = queries.create_user(email="user@example.com", name="User")
    account_id = queries.create_account(user_id=user_id, name="Portfolio", is_manual=True)
    
    # Create holding
    holding_id = queries.upsert_holding(
        account_id=account_id,
        symbol="AAPL",
        name="Apple Inc.",
        quantity=10.0,
        average_cost=150.0,
        current_price=160.0,
        market_value=1600.0,
        currency="USD",
        asset_type="equity"
    )
    assert holding_id is not None
    
    # Get holdings
    holdings = queries.get_holdings_for_account(account_id)
    assert len(holdings) == 1
    assert holdings[0]['symbol'] == "AAPL"
    assert holdings[0]['quantity'] == 10.0
    
    # Update same holding (upsert by account_id + symbol)
    holding_id_2 = queries.upsert_holding(
        account_id=account_id,
        symbol="AAPL",
        quantity=15.0,
        current_price=165.0,
        market_value=2475.0
    )
    
    # Should update the same holding
    holdings_updated = queries.get_holdings_for_account(account_id)
    assert len(holdings_updated) == 1
    assert holdings_updated[0]['quantity'] == 15.0
    assert holdings_updated[0]['current_price'] == 165.0


def test_get_all_holdings_for_user(test_db):
    """Test getting all holdings across all accounts for a user."""
    from db import queries
    
    user_id = queries.create_user(email="user@example.com", name="User")
    
    # Create multiple accounts
    acc1 = queries.create_account(user_id=user_id, name="Account 1", is_manual=True)
    acc2 = queries.create_account(user_id=user_id, name="Account 2", is_manual=True)
    
    # Add holdings to each account
    queries.upsert_holding(account_id=acc1, symbol="AAPL", quantity=10.0)
    queries.upsert_holding(account_id=acc1, symbol="GOOGL", quantity=5.0)
    queries.upsert_holding(account_id=acc2, symbol="MSFT", quantity=8.0)
    
    # Get all holdings for user
    all_holdings = queries.get_all_holdings_for_user(user_id)
    assert len(all_holdings) == 3
    
    symbols = [h['symbol'] for h in all_holdings]
    assert "AAPL" in symbols
    assert "GOOGL" in symbols
    assert "MSFT" in symbols


def test_cascade_delete_account(test_db):
    """Test that deleting an account cascades to holdings and transactions."""
    from db import queries
    
    user_id = queries.create_user(email="user@example.com", name="User")
    account_id = queries.create_account(user_id=user_id, name="Portfolio", is_manual=True)
    
    # Add holding and transaction
    queries.upsert_holding(account_id=account_id, symbol="AAPL", quantity=10.0)
    queries.create_transaction(
        account_id=account_id,
        symbol="AAPL",
        date="2024-01-01",
        transaction_type="buy",
        quantity=10.0,
        price=150.0
    )
    
    # Verify they exist
    holdings = queries.get_holdings_for_account(account_id)
    transactions = queries.get_transactions_for_account(account_id)
    assert len(holdings) == 1
    assert len(transactions) == 1
    
    # Delete account
    queries.delete_account(account_id)
    
    # Verify holdings and transactions are gone
    holdings_after = queries.get_holdings_for_account(account_id)
    transactions_after = queries.get_transactions_for_account(account_id)
    assert len(holdings_after) == 0
    assert len(transactions_after) == 0


def test_upsert_classification(test_db):
    """Test upserting a classification."""
    from db import queries
    
    # Create classification
    queries.upsert_classification(
        symbol="AAPL",
        display_name="Apple",
        category="Technology",
        source="manual"
    )
    
    # Get classification
    classification = queries.get_classification("AAPL")
    assert classification is not None
    assert classification['display_name'] == "Apple"
    assert classification['category'] == "Technology"
    
    # Update
    queries.upsert_classification(
        symbol="AAPL",
        display_name="Apple Inc",
        category="Tech"
    )
    
    # Verify update
    updated = queries.get_classification("AAPL")
    assert updated['display_name'] == "Apple Inc"
    assert updated['category'] == "Tech"


def test_get_classifications_by_category(test_db):
    """Test getting classifications by category."""
    from db import queries
    
    queries.upsert_classification("AAPL", "Apple", "Technology")
    queries.upsert_classification("GOOGL", "Google", "Technology")
    queries.upsert_classification("JPM", "JP Morgan", "Finance")
    
    # Get all tech
    tech_classifications = queries.get_classifications_by_category("Technology")
    assert len(tech_classifications) == 2
    
    symbols = [c['symbol'] for c in tech_classifications]
    assert "AAPL" in symbols
    assert "GOOGL" in symbols


def test_create_transaction(test_db):
    """Test creating a transaction."""
    from db import queries
    
    user_id = queries.create_user(email="user@example.com", name="User")
    account_id = queries.create_account(user_id=user_id, name="Portfolio", is_manual=True)
    
    # Create transaction
    txn_id = queries.create_transaction(
        account_id=account_id,
        symbol="AAPL",
        name="Apple Inc.",
        date="2024-01-15",
        transaction_type="buy",
        quantity=10.0,
        price=150.0,
        fees=5.0,
        source="manual"
    )
    assert txn_id is not None
    
    # Get transactions
    transactions = queries.get_transactions_for_account(account_id)
    assert len(transactions) == 1
    assert transactions[0]['symbol'] == "AAPL"
    assert transactions[0]['quantity'] == 10.0


def test_watchlist_operations(test_db):
    """Test creating watchlists and adding tickers."""
    from db import queries
    
    user_id = queries.create_user(email="user@example.com", name="User")
    
    # Create watchlist
    watchlist_id = queries.create_watchlist(user_id=user_id, name="Tech Stocks")
    assert watchlist_id is not None
    
    # Get watchlists
    watchlists = queries.get_watchlists_for_user(user_id)
    assert len(watchlists) == 1
    assert watchlists[0]['name'] == "Tech Stocks"
    
    # Add tickers
    queries.add_ticker_to_watchlist(watchlist_id, "AAPL")
    queries.add_ticker_to_watchlist(watchlist_id, "GOOGL")
    
    # Remove ticker
    queries.remove_ticker_from_watchlist(watchlist_id, "AAPL")
