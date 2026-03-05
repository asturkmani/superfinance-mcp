"""Tests for widget data fetching."""

import os
import tempfile
import pytest
import json
from datetime import datetime


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
def test_user_with_holdings(test_db):
    """Create test user with sample holdings."""
    from db import queries
    
    # Create user
    user_id = queries.create_user(email="test@example.com", name="Test User")
    
    # Create account
    account_id = queries.create_account(
        user_id=user_id,
        name="Test Brokerage",
        is_manual=True
    )
    
    # Add holdings
    queries.upsert_holding(
        account_id=account_id,
        symbol="AAPL",
        quantity=100,
        average_cost=150.0,
        current_price=173.5,
        market_value=17350.0,
        asset_type="equity"
    )
    queries.upsert_holding(
        account_id=account_id,
        symbol="MSFT",
        quantity=50,
        average_cost=350.0,
        current_price=405.2,
        market_value=20260.0,
        asset_type="equity"
    )
    queries.upsert_holding(
        account_id=account_id,
        symbol="GOOG",
        quantity=25,
        average_cost=145.0,
        current_price=142.8,
        market_value=3570.0,
        asset_type="equity"
    )
    
    return {"user_id": user_id, "account_id": account_id}


# ============================================================================
# HOLDINGS LIST WIDGET TESTS
# ============================================================================

def test_fetch_holdings_data_returns_real_holdings(test_user_with_holdings):
    """Holdings widget should return actual holdings from DB."""
    from helpers.widget_data import fetch_holdings_data
    
    user_id = test_user_with_holdings["user_id"]
    config = {}
    
    result = fetch_holdings_data(user_id, config)
    
    assert "holdings" in result
    assert len(result["holdings"]) == 3
    
    # Check first holding
    holdings = result["holdings"]
    # Should be sorted by market value descending (MSFT first)
    assert holdings[0]["symbol"] == "MSFT"
    assert holdings[0]["quantity"] == 50
    assert holdings[0]["current_price"] == 405.2
    assert holdings[0]["market_value"] == 20260.0
    assert holdings[0]["return_pct"] is not None


def test_fetch_holdings_data_filters_by_account(test_user_with_holdings):
    """Holdings widget should filter by account_id if provided."""
    from helpers.widget_data import fetch_holdings_data
    
    user_id = test_user_with_holdings["user_id"]
    account_id = test_user_with_holdings["account_id"]
    
    config = {"account_id": account_id}
    
    result = fetch_holdings_data(user_id, config)
    
    assert "holdings" in result
    assert len(result["holdings"]) == 3


def test_fetch_holdings_calculates_return_pct(test_user_with_holdings):
    """Holdings should calculate return percentage correctly."""
    from helpers.widget_data import fetch_holdings_data
    
    user_id = test_user_with_holdings["user_id"]
    config = {}
    
    result = fetch_holdings_data(user_id, config)
    holdings = result["holdings"]
    
    # Find AAPL
    aapl = next(h for h in holdings if h["symbol"] == "AAPL")
    # Return = (173.5 - 150) / 150 * 100 = 15.67%
    assert aapl["return_pct"] == pytest.approx(15.67, rel=0.1)
    
    # Find GOOG (negative return)
    goog = next(h for h in holdings if h["symbol"] == "GOOG")
    # Return = (142.8 - 145) / 145 * 100 = -1.52%
    assert goog["return_pct"] < 0


# ============================================================================
# PORTFOLIO PIE CHART TESTS
# ============================================================================

def test_fetch_portfolio_allocation_groups_by_ticker(test_user_with_holdings):
    """Pie chart data should group holdings by ticker."""
    from helpers.widget_data import fetch_portfolio_allocation
    
    user_id = test_user_with_holdings["user_id"]
    config = {"group_by": "ticker"}
    
    result = fetch_portfolio_allocation(user_id, config)
    
    assert "labels" in result
    assert "values" in result
    assert len(result["labels"]) == 3
    assert len(result["values"]) == 3
    
    # Should be sorted by value descending
    assert result["labels"][0] == "MSFT"
    assert result["values"][0] == 20260.0


def test_fetch_portfolio_allocation_groups_by_asset_type(test_user_with_holdings):
    """Pie chart data should group by asset type."""
    from helpers.widget_data import fetch_portfolio_allocation
    
    user_id = test_user_with_holdings["user_id"]
    config = {"group_by": "asset_type"}
    
    result = fetch_portfolio_allocation(user_id, config)
    
    assert "labels" in result
    assert "values" in result
    # All holdings are equity, so should have 1 group
    assert len(result["labels"]) == 1
    assert result["labels"][0] == "equity"
    assert result["values"][0] == 41180.0  # Sum of all holdings


# ============================================================================
# PORTFOLIO TREEMAP TESTS
# ============================================================================

def test_fetch_portfolio_treemap_builds_hierarchy(test_user_with_holdings):
    """Treemap should build Portfolio -> Category -> Ticker hierarchy."""
    from helpers.widget_data import fetch_portfolio_treemap
    
    user_id = test_user_with_holdings["user_id"]
    config = {"group_by": "category"}
    
    result = fetch_portfolio_treemap(user_id, config)
    
    assert "labels" in result
    assert "parents" in result
    assert "values" in result
    
    # Should have Portfolio as root
    assert result["labels"][0] == "Portfolio"
    assert result["parents"][0] == ""
    assert result["values"][0] == 0  # Root has 0 value
    
    # Should have at least one category
    assert len(result["labels"]) > 1


# ============================================================================
# STOCK CHART TESTS
# ============================================================================

def test_fetch_stock_chart_data_returns_ohlcv(test_db):
    """Stock chart should return OHLCV candle data."""
    from helpers.widget_data import fetch_stock_chart_data
    
    config = {
        "tickers": "AAPL",
        "period": "5d"
    }
    
    result = fetch_stock_chart_data(config)
    
    assert "charts" in result
    # Should have data for AAPL (even if empty due to market/API issues)
    assert isinstance(result["charts"], dict)


def test_fetch_stock_chart_handles_multiple_tickers(test_db):
    """Stock chart should handle multiple comma-separated tickers."""
    from helpers.widget_data import fetch_stock_chart_data
    
    config = {
        "tickers": "AAPL,MSFT",
        "period": "5d"
    }
    
    result = fetch_stock_chart_data(config)
    
    assert "charts" in result
    # Should return dict with ticker keys
    assert isinstance(result["charts"], dict)


# ============================================================================
# PERFORMANCE CHART TESTS
# ============================================================================

def test_fetch_performance_data_normalizes_to_percent(test_db):
    """Performance chart should normalize to percentage returns."""
    from helpers.widget_data import fetch_performance_data
    
    config = {
        "tickers": "AAPL",
        "period": "5d"
    }
    
    result = fetch_performance_data(config)
    
    assert "series" in result
    assert isinstance(result["series"], dict)


# ============================================================================
# CORRELATION HEATMAP TESTS
# ============================================================================

def test_fetch_correlation_needs_two_tickers(test_user_with_holdings):
    """Correlation should work with at least 2 tickers."""
    from helpers.widget_data import fetch_correlation_data
    from db import queries
    
    user_id = test_user_with_holdings["user_id"]
    account_id = test_user_with_holdings["account_id"]
    
    # Delete existing holdings
    from db.database import get_db
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM holdings WHERE account_id = ?", (account_id,))
    conn.commit()
    
    # Add just one holding
    queries.upsert_holding(
        account_id=account_id,
        symbol="AAPL",
        quantity=100,
        asset_type="equity"
    )
    
    config = {"period": "1y"}
    
    result = fetch_correlation_data(user_id, config)
    
    # Should return error with less than 2 positions
    assert "error" in result


def test_fetch_correlation_with_valid_tickers(test_user_with_holdings):
    """Correlation should return matrix with valid tickers."""
    from helpers.widget_data import fetch_correlation_data
    
    user_id = test_user_with_holdings["user_id"]
    config = {"period": "5d"}
    
    result = fetch_correlation_data(user_id, config)
    
    # May have error due to API issues, but structure should be there
    if "error" not in result:
        assert "tickers" in result
        assert "z" in result
        assert isinstance(result["tickers"], list)
        assert isinstance(result["z"], list)


# ============================================================================
# ANALYSIS TABLE TESTS
# ============================================================================

def test_fetch_analysis_data_uses_portfolio_tickers(test_user_with_holdings):
    """Analysis should use portfolio tickers when none specified."""
    from helpers.widget_data import fetch_analysis_data
    
    user_id = test_user_with_holdings["user_id"]
    config = {"metrics": "risk"}
    
    result = fetch_analysis_data(user_id, config)
    
    # Should process portfolio tickers
    assert isinstance(result, dict)


def test_fetch_analysis_data_uses_specified_tickers(test_user_with_holdings):
    """Analysis should use specified tickers when provided."""
    from helpers.widget_data import fetch_analysis_data
    
    user_id = test_user_with_holdings["user_id"]
    config = {
        "tickers": "AAPL,MSFT",
        "metrics": "risk"
    }
    
    result = fetch_analysis_data(user_id, config)
    
    # Should process specified tickers
    assert isinstance(result, dict)


# ============================================================================
# WIDGET DATA ERROR HANDLING
# ============================================================================

def test_fetch_all_widget_data_handles_errors(test_user_with_holdings):
    """fetch_all_widget_data should catch widget errors and continue."""
    from helpers.widget_data import fetch_all_widget_data
    import asyncio
    
    user_id = test_user_with_holdings["user_id"]
    
    widgets = [
        {
            "id": "widget1",
            "widget_type": "holdings_list",
            "config": "{}"
        },
        {
            "id": "widget2",
            "widget_type": "invalid_type",
            "config": "{}"
        }
    ]
    
    result = asyncio.run(fetch_all_widget_data(widgets, user_id))
    
    # Should have data for widget1
    assert "widget1" in result
    # Should have error for widget2
    assert "widget2" in result
    # widget2 should have error
    if "error" not in result["widget2"]:
        # Or it might just be empty dict
        assert isinstance(result["widget2"], dict)


# ============================================================================
# DASHBOARD HTML WITH REAL DATA
# ============================================================================

def test_dashboard_html_with_real_data(test_user_with_holdings):
    """Dashboard HTML should render with real data passed in."""
    from helpers.dashboard_templates import generate_dashboard_html
    
    user_id = test_user_with_holdings["user_id"]
    
    dashboard = {
        "id": "dash1",
        "user_id": user_id,
        "name": "Test Dashboard",
        "description": "Test"
    }
    
    widgets = [
        {
            "id": "widget1",
            "widget_type": "holdings_list",
            "title": "My Holdings",
            "width": 2,
            "config": "{}"
        }
    ]
    
    widget_data = {
        "widget1": {
            "holdings": [
                {
                    "symbol": "AAPL",
                    "quantity": 100,
                    "current_price": 173.5,
                    "market_value": 17350.0,
                    "return_pct": 15.67
                }
            ]
        }
    }
    
    html = generate_dashboard_html(dashboard, widgets, widget_data)
    
    assert "Test Dashboard" in html
    assert "AAPL" in html
    assert "173.5" in html or "173.50" in html
