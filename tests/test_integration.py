"""Integration tests for SQLite persistence across services and tools.

Tests:
1. SnapTrade mock data persists to SQLite
2. Holdings read from SQLite (not API)
3. Manual portfolio CRUD works through tools
4. User isolation (user A can't see user B's holdings)
"""

import os
import pytest
from datetime import datetime
from unittest.mock import Mock, patch, MagicMock

from db import queries
from db.database import get_db
from services.snaptrade_service import SnapTradeService
from services.holdings_service import HoldingsService
from services.portfolio_service import PortfolioService


@pytest.fixture
def clean_db(tmp_path):
    """Create a clean database for each test."""
    # Use a temporary file for each test
    db_path = str(tmp_path / "test.db")
    os.environ['SUPERFINANCE_DB_PATH'] = db_path
    
    # Get fresh connection (creates schema)
    conn = get_db()
    
    yield conn
    
    # Cleanup
    conn.close()
    if os.path.exists(db_path):
        os.unlink(db_path)
    if 'SUPERFINANCE_DB_PATH' in os.environ:
        del os.environ['SUPERFINANCE_DB_PATH']


@pytest.fixture
def test_users(clean_db):
    """Create test users."""
    user_a = queries.create_user("user_a@test.com", "User A")
    user_b = queries.create_user("user_b@test.com", "User B")
    return {"user_a": user_a, "user_b": user_b}


@pytest.mark.asyncio
async def test_snaptrade_sync_persists_to_sqlite(clean_db):
    """Test that SnapTrade data can be persisted to SQLite."""
    
    # Create a test user
    user_id = queries.create_user("test@snaptrade.com", "SnapTrade Test User")
    
    # Simulate SnapTrade sync by creating account and holdings directly
    # (In real usage, this would be done by SnapTradeService.sync_to_db)
    
    # Create a brokerage
    brokerage_id = queries.upsert_brokerage(
        provider="snaptrade",
        provider_institution_id="test_brokerage",
        name="Test Brokerage"
    )
    
    # Create an account (simulating synced account from SnapTrade)
    account_id = "st_acc_123"
    queries.create_account(
        user_id=user_id,
        name="Test Brokerage Account",
        currency="USD",
        is_manual=False,
        last_sync_at=datetime.utcnow().isoformat() + "Z"
    )
    
    # Override with SnapTrade account ID
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE accounts SET id = ? WHERE id = (SELECT id FROM accounts WHERE user_id = ? ORDER BY created_at DESC LIMIT 1)",
        (account_id, user_id)
    )
    conn.commit()
    
    # Add holdings (simulating SnapTrade positions)
    queries.upsert_holding(
        account_id=account_id,
        symbol="AAPL",
        name="Apple Inc.",
        quantity=10,
        current_price=150.50,
        currency="USD"
    )
    
    queries.upsert_holding(
        account_id=account_id,
        symbol="GOOGL",
        name="Alphabet Inc.",
        quantity=5,
        current_price=140.25,
        currency="USD"
    )
    
    # Verify data persisted to SQLite
    accounts = queries.get_accounts_for_user(user_id)
    assert len(accounts) == 1
    assert accounts[0]["id"] == "st_acc_123"
    assert accounts[0]["name"] == "Test Brokerage Account"
    assert accounts[0]["is_manual"] == 0  # Synced account
    
    # Verify holdings persisted
    holdings = queries.get_holdings_for_account("st_acc_123")
    assert len(holdings) == 2
    
    symbols = {h["symbol"] for h in holdings}
    assert "AAPL" in symbols
    assert "GOOGL" in symbols
    
    # Find AAPL holding
    aapl = next(h for h in holdings if h["symbol"] == "AAPL")
    assert aapl["name"] == "Apple Inc."
    assert aapl["quantity"] == 10
    assert aapl["current_price"] == 150.50


@pytest.mark.asyncio
async def test_holdings_read_from_sqlite_not_api(clean_db):
    """Test that holdings service reads from SQLite, not SnapTrade API."""
    
    # Create a test user and account
    user_id = queries.create_user("test@holdings.com", "Holdings Test User")
    account_id = queries.create_account(
        user_id=user_id,
        name="Test Account",
        currency="USD",
        is_manual=False
    )
    
    # Add holdings directly to SQLite
    queries.upsert_holding(
        account_id=account_id,
        symbol="TSLA",
        name="Tesla Inc.",
        quantity=20,
        average_cost=200.00,
        current_price=250.00,
        currency="USD"
    )
    
    queries.upsert_holding(
        account_id=account_id,
        symbol="MSFT",
        name="Microsoft Corporation",
        quantity=15,
        average_cost=300.00,
        current_price=350.00,
        currency="USD"
    )
    
    # Mock get_live_price to return stored prices (simulating offline mode)
    with patch('services.holdings_service.get_live_price') as mock_price:
        def mock_live_price(symbol):
            prices = {
                "TSLA": {"price": 250.00, "source": "manual"},
                "MSFT": {"price": 350.00, "source": "manual"}
            }
            return prices.get(symbol, {})
        
        mock_price.side_effect = mock_live_price
        
        # Call holdings service (should read from SQLite, not call SnapTrade API)
        result = await HoldingsService.list_all_holdings(user_id=user_id)
    
    assert result["success"] is True
    assert result["accounts_count"] == 1
    
    # Verify holdings are from SQLite
    account = result["accounts"][0]
    assert len(account["positions"]) == 2
    
    symbols = {p["symbol"] for p in account["positions"]}
    assert "TSLA" in symbols
    assert "MSFT" in symbols
    
    # Verify totals calculated correctly
    # TSLA: 20 * 250 = 5000
    # MSFT: 15 * 350 = 5250
    # Total: 10250
    assert result["totals"]["holdings"]["USD"] == 10250.00
    
    # Verify cost basis
    # TSLA: 20 * 200 = 4000
    # MSFT: 15 * 300 = 4500
    # Total: 8500
    assert result["totals"]["cost_basis"]["USD"] == 8500.00
    
    # Verify P&L
    # 10250 - 8500 = 1750
    assert result["totals"]["unrealized_pnl"]["USD"] == 1750.00


@pytest.mark.asyncio
async def test_manual_portfolio_crud_through_tools(clean_db):
    """Test that manual portfolio CRUD works through service layer."""
    
    user_id = queries.create_user("test@manual.com", "Manual Portfolio User")
    
    # Create portfolio
    create_result = await PortfolioService.create_portfolio(
        user_id=user_id,
        portfolio_id="private-equity",
        name="Private Equity Holdings",
        description="Private investments"
    )
    
    assert create_result["success"] is True
    assert create_result["portfolio_id"] == "private-equity"
    
    # Verify account created in SQLite
    account = queries.get_account("private-equity")
    assert account is not None
    assert account["name"] == "Private Equity Holdings"
    assert account["user_id"] == user_id
    assert account["is_manual"] == 1
    
    # Add position
    add_result = await PortfolioService.add_position(
        user_id=user_id,
        portfolio_id="private-equity",
        name="SpaceX Series J",
        units=100,
        average_cost=50.00,
        currency="USD",
        symbol="SPAX.PVT",
        manual_price=75.00
    )
    
    assert add_result["success"] is True
    position_id = add_result["position_id"]
    
    # Verify holding persisted
    holdings = queries.get_holdings_for_account("private-equity")
    assert len(holdings) == 1
    assert holdings[0]["symbol"] == "SPAX.PVT"
    assert holdings[0]["quantity"] == 100
    assert holdings[0]["average_cost"] == 50.00
    
    # Update position
    update_result = await PortfolioService.update_position(
        user_id=user_id,
        portfolio_id="private-equity",
        position_id=position_id,
        units=150,  # Increased holding
        manual_price=80.00  # Price increased
    )
    
    assert update_result["success"] is True
    assert update_result["position"]["units"] == 150
    assert update_result["position"]["manual_price"] == 80.00
    
    # Verify update persisted
    holdings = queries.get_holdings_for_account("private-equity")
    assert holdings[0]["quantity"] == 150
    assert holdings[0]["current_price"] == 80.00
    
    # Remove position
    remove_result = await PortfolioService.remove_position(
        user_id=user_id,
        portfolio_id="private-equity",
        position_id=position_id
    )
    
    assert remove_result["success"] is True
    
    # Verify holding deleted
    holdings = queries.get_holdings_for_account("private-equity")
    assert len(holdings) == 0
    
    # Delete portfolio
    delete_result = await PortfolioService.delete_portfolio(
        user_id=user_id,
        portfolio_id="private-equity"
    )
    
    assert delete_result["success"] is True
    
    # Verify account deleted (cascade)
    account = queries.get_account("private-equity")
    assert account is None


@pytest.mark.asyncio
async def test_user_isolation(test_users, clean_db):
    """Test that user A can't see user B's holdings."""
    
    user_a = test_users["user_a"]
    user_b = test_users["user_b"]
    
    # Create accounts for both users
    account_a = queries.create_account(
        user_id=user_a,
        name="User A Account",
        currency="USD",
        is_manual=True
    )
    
    account_b = queries.create_account(
        user_id=user_b,
        name="User B Account",
        currency="USD",
        is_manual=True
    )
    
    # Add holdings for User A
    queries.upsert_holding(
        account_id=account_a,
        symbol="AAPL",
        name="Apple Inc.",
        quantity=10,
        average_cost=150.00,
        currency="USD"
    )
    
    # Add holdings for User B
    queries.upsert_holding(
        account_id=account_b,
        symbol="GOOGL",
        name="Alphabet Inc.",
        quantity=5,
        average_cost=140.00,
        currency="USD"
    )
    
    # User A should only see their holdings
    holdings_a = await HoldingsService.list_all_holdings(user_id=user_a)
    assert holdings_a["success"] is True
    assert holdings_a["accounts_count"] == 1
    assert holdings_a["accounts"][0]["account_id"] == account_a
    assert len(holdings_a["accounts"][0]["positions"]) == 1
    assert holdings_a["accounts"][0]["positions"][0]["symbol"] == "AAPL"
    
    # User B should only see their holdings
    holdings_b = await HoldingsService.list_all_holdings(user_id=user_b)
    assert holdings_b["success"] is True
    assert holdings_b["accounts_count"] == 1
    assert holdings_b["accounts"][0]["account_id"] == account_b
    assert len(holdings_b["accounts"][0]["positions"]) == 1
    assert holdings_b["accounts"][0]["positions"][0]["symbol"] == "GOOGL"
    
    # Verify User A cannot access User B's portfolio directly
    portfolio_b_result = await PortfolioService.get_portfolio(
        user_id=user_a,  # User A trying to access
        portfolio_id=account_b  # User B's account
    )
    
    assert "error" in portfolio_b_result
    assert "Access denied" in portfolio_b_result["error"]
    
    # Verify database-level isolation
    user_a_accounts = queries.get_accounts_for_user(user_a)
    user_a_account_ids = {acc["id"] for acc in user_a_accounts}
    assert account_b not in user_a_account_ids
    
    user_b_accounts = queries.get_accounts_for_user(user_b)
    user_b_account_ids = {acc["id"] for acc in user_b_accounts}
    assert account_a not in user_b_account_ids


@pytest.mark.asyncio
async def test_default_user_helper(clean_db):
    """Test that get_or_create_default_user works correctly."""
    
    # First call should create the user
    user_id_1 = queries.get_or_create_default_user()
    assert user_id_1 is not None
    
    # Verify user exists
    user = queries.get_user(user_id_1)
    assert user is not None
    assert user["email"] == "default@vault.local"
    assert user["name"] == "Default User"
    
    # Second call should return the same user
    user_id_2 = queries.get_or_create_default_user()
    assert user_id_2 == user_id_1
    
    # Should still be only one user with that email
    all_users = queries.get_user_by_email("default@vault.local")
    assert all_users is not None
    assert all_users["id"] == user_id_1


@pytest.mark.asyncio
async def test_classification_persists_to_sqlite(clean_db):
    """Test that classifications are stored in SQLite."""
    
    from helpers.classification import get_classification, update_classification
    
    # First classification should trigger Perplexity call (or fallback)
    # and persist to SQLite
    with patch('helpers.classification.classify_with_perplexity') as mock_perplexity:
        mock_perplexity.return_value = {
            "name": "Apple",
            "category": "Technology"
        }
        
        result = get_classification("AAPL", "Apple Inc.")
        
        assert result["name"] == "Apple"
        assert result["category"] == "Technology"
        assert result["source"] == "perplexity"
    
    # Verify persisted to SQLite
    classification = queries.get_classification("AAPL")
    assert classification is not None
    assert classification["display_name"] == "Apple"
    assert classification["category"] == "Technology"
    
    # Second call should read from SQLite (no Perplexity call)
    with patch('helpers.classification.classify_with_perplexity') as mock_perplexity:
        result = get_classification("AAPL")
        
        # Perplexity should not be called
        mock_perplexity.assert_not_called()
        
        assert result["name"] == "Apple"
        assert result["category"] == "Technology"
        assert result["source"] == "perplexity"  # From original classification
    
    # Update classification
    update_result = update_classification("AAPL", category="Consumer Electronics")
    assert update_result["success"] is True
    
    # Verify update persisted
    classification = queries.get_classification("AAPL")
    assert classification["category"] == "Consumer Electronics"
