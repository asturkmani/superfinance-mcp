"""Tests for portfolio service with SQLite backend."""

import os
import tempfile
import pytest
from datetime import datetime
from unittest.mock import patch, MagicMock


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


@pytest.fixture
def test_user(test_db):
    """Create a test user."""
    from db import queries
    user_id = queries.create_user(email="test@example.com", name="Test User")
    return user_id


@pytest.mark.asyncio
async def test_create_manual_account(test_db, test_user):
    """Test creating a manual account."""
    from services.portfolio_service import PortfolioService
    
    result = await PortfolioService.create_portfolio(
        user_id=test_user,
        portfolio_id="test-portfolio",
        name="Test Portfolio",
        description="Test description"
    )
    
    assert result['success'] is True
    assert result['portfolio_id'] == "test-portfolio"
    assert result['name'] == "Test Portfolio"


@pytest.mark.asyncio
async def test_add_holding_to_account(test_db, test_user):
    """Test adding a holding to an account."""
    from services.portfolio_service import PortfolioService
    from db import queries
    
    # Create account
    await PortfolioService.create_portfolio(
        user_id=test_user,
        portfolio_id="test-portfolio",
        name="Test Portfolio"
    )
    
    # Add position
    result = await PortfolioService.add_position(
        user_id=test_user,
        portfolio_id="test-portfolio",
        name="Apple",
        symbol="AAPL",
        units=10.0,
        average_cost=150.0,
        currency="USD"
    )
    
    assert result['success'] is True
    assert 'position_id' in result
    
    # Verify it's in the database
    accounts = queries.get_accounts_for_user(test_user)
    assert len(accounts) > 0
    
    account = accounts[0]
    holdings = queries.get_holdings_for_account(account['id'])
    assert len(holdings) == 1
    assert holdings[0]['symbol'] == "AAPL"
    assert holdings[0]['quantity'] == 10.0


@pytest.mark.asyncio
async def test_get_portfolio_with_live_prices(test_db, test_user):
    """Test getting portfolio with mocked live prices."""
    from services.portfolio_service import PortfolioService
    
    # Create portfolio
    await PortfolioService.create_portfolio(
        user_id=test_user,
        portfolio_id="test-portfolio",
        name="Test Portfolio"
    )
    
    # Add position
    await PortfolioService.add_position(
        user_id=test_user,
        portfolio_id="test-portfolio",
        name="Apple",
        symbol="AAPL",
        units=10.0,
        average_cost=150.0,
        currency="USD"
    )
    
    # Mock get_live_price to return a test price
    with patch('services.portfolio_service.get_live_price') as mock_price:
        mock_price.return_value = {'price': 160.0, 'source': 'yahoo_finance'}
        
        # Get portfolio
        result = await PortfolioService.get_portfolio(
            user_id=test_user,
            portfolio_id="test-portfolio"
        )
        
        assert result['success'] is True
        assert result['positions_count'] == 1
        
        position = result['positions'][0]
        assert position['symbol'] == "AAPL"
        assert position['live_price'] == 160.0
        assert position['market_value'] == 1600.0  # 10 * 160
        assert position['unrealized_pnl'] == 100.0  # 1600 - 1500


@pytest.mark.asyncio
async def test_net_worth_calculation_with_liability(test_db, test_user):
    """Test that net worth correctly includes liabilities (negative holdings)."""
    from services.portfolio_service import PortfolioService
    from db import queries
    
    # Create account
    await PortfolioService.create_portfolio(
        user_id=test_user,
        portfolio_id="test-portfolio",
        name="Test Portfolio"
    )
    
    # Add regular holding (positive)
    await PortfolioService.add_position(
        user_id=test_user,
        portfolio_id="test-portfolio",
        name="Cash",
        symbol="USD.CASH",
        units=10000.0,
        average_cost=1.0,
        currency="USD",
        manual_price=1.0
    )
    
    # Add liability as negative holding (e.g., mortgage)
    # Get the account ID first
    accounts = queries.get_accounts_for_user(test_user)
    account_id = accounts[0]['id']
    
    queries.upsert_holding(
        account_id=account_id,
        symbol="MORTGAGE",
        name="Home Mortgage",
        quantity=1.0,
        average_cost=-350000.0,
        current_price=-350000.0,
        market_value=-350000.0,
        currency="USD",
        asset_type="liability"
    )
    
    # Mock get_live_price to return appropriate values
    def mock_get_live_price(symbol):
        if symbol == "USD.CASH":
            return {'price': 1.0, 'source': 'manual'}
        elif symbol == "MORTGAGE":
            return {'price': None, 'source': 'none'}  # No live price for liabilities
        return {'price': None, 'source': 'none'}
    
    with patch('services.portfolio_service.get_live_price', side_effect=mock_get_live_price):
        # Get portfolio
        result = await PortfolioService.get_portfolio(
            user_id=test_user,
            portfolio_id="test-portfolio"
        )
        
        # Net worth = 10000 + (-350000) = -340000
        assert result['success'] is True
        assert result['positions_count'] == 2
        
        # Total market value should include both positive and negative
        total_market_value = result['total_market_value']
        assert total_market_value == -340000.0


@pytest.mark.asyncio
async def test_delete_portfolio_cascades(test_db, test_user):
    """Test that deleting a portfolio deletes holdings."""
    from services.portfolio_service import PortfolioService
    from db import queries
    
    # Create portfolio and add holding
    await PortfolioService.create_portfolio(
        user_id=test_user,
        portfolio_id="test-portfolio",
        name="Test Portfolio"
    )
    
    await PortfolioService.add_position(
        user_id=test_user,
        portfolio_id="test-portfolio",
        name="Apple",
        symbol="AAPL",
        units=10.0,
        average_cost=150.0
    )
    
    # Verify holdings exist
    accounts = queries.get_accounts_for_user(test_user)
    account_id = accounts[0]['id']
    holdings = queries.get_holdings_for_account(account_id)
    assert len(holdings) == 1
    
    # Delete portfolio
    result = await PortfolioService.delete_portfolio(
        user_id=test_user,
        portfolio_id="test-portfolio"
    )
    
    assert result['success'] is True
    
    # Verify holdings are gone (cascade delete)
    holdings_after = queries.get_holdings_for_account(account_id)
    assert len(holdings_after) == 0
    
    # Verify account is gone
    accounts_after = queries.get_accounts_for_user(test_user)
    assert len(accounts_after) == 0
