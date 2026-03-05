"""Tests for dashboard system."""

import os
import tempfile
import pytest
import json
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


# ============================================================================
# SCHEMA TESTS
# ============================================================================

def test_dashboard_tables_exist(test_db):
    """Verify dashboards and dashboard_widgets tables are created."""
    from db.database import get_db
    
    conn = get_db()
    cursor = conn.cursor()
    
    # Check dashboards table
    cursor.execute("""
        SELECT name FROM sqlite_master 
        WHERE type='table' AND name='dashboards'
    """)
    assert cursor.fetchone() is not None
    
    # Check dashboard_widgets table
    cursor.execute("""
        SELECT name FROM sqlite_master 
        WHERE type='table' AND name='dashboard_widgets'
    """)
    assert cursor.fetchone() is not None
    
    # Verify indexes
    cursor.execute("""
        SELECT name FROM sqlite_master 
        WHERE type='index' AND name='idx_dashboards_user'
    """)
    assert cursor.fetchone() is not None
    
    cursor.execute("""
        SELECT name FROM sqlite_master 
        WHERE type='index' AND name='idx_widgets_dashboard'
    """)
    assert cursor.fetchone() is not None


# ============================================================================
# DASHBOARD CRUD TESTS
# ============================================================================

def test_create_dashboard(test_db):
    """Create dashboard, verify returned ID and fields."""
    from db import queries
    
    # Create user first
    user_id = queries.create_user(email="test@example.com", name="Test User")
    
    # Create dashboard
    dashboard_id = queries.create_dashboard(
        user_id=user_id,
        name="My Dashboard",
        description="Test dashboard",
        layout="grid"
    )
    
    assert dashboard_id is not None
    assert len(dashboard_id) > 0
    
    # Retrieve dashboard
    dashboard = queries.get_dashboard(dashboard_id)
    assert dashboard is not None
    assert dashboard['id'] == dashboard_id
    assert dashboard['user_id'] == user_id
    assert dashboard['name'] == "My Dashboard"
    assert dashboard['description'] == "Test dashboard"
    assert dashboard['layout'] == "grid"
    assert dashboard['is_default'] == 0


def test_list_dashboards(test_db):
    """Create multiple dashboards, list them, verify count and order."""
    from db import queries
    
    user_id = queries.create_user(email="test@example.com", name="Test User")
    
    # Create multiple dashboards
    dashboard_id1 = queries.create_dashboard(user_id, "Dashboard 1")
    dashboard_id2 = queries.create_dashboard(user_id, "Dashboard 2")
    dashboard_id3 = queries.create_dashboard(user_id, "Dashboard 3")
    
    # List dashboards
    dashboards = queries.list_dashboards(user_id)
    
    assert len(dashboards) == 3
    assert dashboards[0]['id'] == dashboard_id1
    assert dashboards[1]['id'] == dashboard_id2
    assert dashboards[2]['id'] == dashboard_id3


def test_create_dashboard_user_isolation(test_db):
    """Dashboards for user A should not appear in user B's list."""
    from db import queries
    
    user_a = queries.create_user(email="a@example.com", name="User A")
    user_b = queries.create_user(email="b@example.com", name="User B")
    
    # Create dashboards for user A
    queries.create_dashboard(user_a, "A's Dashboard 1")
    queries.create_dashboard(user_a, "A's Dashboard 2")
    
    # Create dashboard for user B
    queries.create_dashboard(user_b, "B's Dashboard")
    
    # User A should only see their dashboards
    a_dashboards = queries.list_dashboards(user_a)
    assert len(a_dashboards) == 2
    assert all(d['user_id'] == user_a for d in a_dashboards)
    
    # User B should only see their dashboard
    b_dashboards = queries.list_dashboards(user_b)
    assert len(b_dashboards) == 1
    assert b_dashboards[0]['user_id'] == user_b


def test_update_dashboard(test_db):
    """Update dashboard fields."""
    from db import queries
    
    user_id = queries.create_user(email="test@example.com", name="Test User")
    dashboard_id = queries.create_dashboard(user_id, "Original Name")
    
    # Update dashboard
    queries.update_dashboard(
        dashboard_id=dashboard_id,
        name="Updated Name",
        description="New description",
        layout="stack",
        is_default=1
    )
    
    # Verify updates
    dashboard = queries.get_dashboard(dashboard_id)
    assert dashboard['name'] == "Updated Name"
    assert dashboard['description'] == "New description"
    assert dashboard['layout'] == "stack"
    assert dashboard['is_default'] == 1


def test_delete_dashboard(test_db):
    """Delete dashboard, verify it's gone."""
    from db import queries
    
    user_id = queries.create_user(email="test@example.com", name="Test User")
    dashboard_id = queries.create_dashboard(user_id, "Test Dashboard")
    
    # Verify it exists
    assert queries.get_dashboard(dashboard_id) is not None
    
    # Delete it
    queries.delete_dashboard(dashboard_id)
    
    # Verify it's gone
    assert queries.get_dashboard(dashboard_id) is None


def test_delete_dashboard_cascades_widgets(test_db):
    """Deleting dashboard should delete all its widgets."""
    from db import queries
    
    user_id = queries.create_user(email="test@example.com", name="Test User")
    dashboard_id = queries.create_dashboard(user_id, "Test Dashboard")
    
    # Add widgets
    widget_id1 = queries.add_widget(
        dashboard_id=dashboard_id,
        widget_type="stock_chart",
        config='{"tickers": "AAPL"}'
    )
    widget_id2 = queries.add_widget(
        dashboard_id=dashboard_id,
        widget_type="portfolio_pie",
        config='{"group_by": "ticker"}'
    )
    
    # Verify widgets exist
    assert queries.get_widget(widget_id1) is not None
    assert queries.get_widget(widget_id2) is not None
    
    # Delete dashboard
    queries.delete_dashboard(dashboard_id)
    
    # Verify widgets are gone
    assert queries.get_widget(widget_id1) is None
    assert queries.get_widget(widget_id2) is None


# ============================================================================
# WIDGET CRUD TESTS
# ============================================================================

def test_add_widget(test_db):
    """Add widget to dashboard, verify fields."""
    from db import queries
    
    user_id = queries.create_user(email="test@example.com", name="Test User")
    dashboard_id = queries.create_dashboard(user_id, "Test Dashboard")
    
    # Add widget
    widget_id = queries.add_widget(
        dashboard_id=dashboard_id,
        widget_type="stock_chart",
        config='{"tickers": "AAPL,MSFT", "period": "1y"}',
        title="Stock Chart",
        position=0,
        width=2,
        height=1
    )
    
    assert widget_id is not None
    
    # Retrieve widget
    widget = queries.get_widget(widget_id)
    assert widget is not None
    assert widget['id'] == widget_id
    assert widget['dashboard_id'] == dashboard_id
    assert widget['widget_type'] == "stock_chart"
    assert widget['title'] == "Stock Chart"
    assert widget['config'] == '{"tickers": "AAPL,MSFT", "period": "1y"}'
    assert widget['position'] == 0
    assert widget['width'] == 2
    assert widget['height'] == 1


def test_list_widgets_ordered(test_db):
    """Widgets should come back ordered by position."""
    from db import queries
    
    user_id = queries.create_user(email="test@example.com", name="Test User")
    dashboard_id = queries.create_dashboard(user_id, "Test Dashboard")
    
    # Add widgets with different positions
    widget_id3 = queries.add_widget(dashboard_id, "stock_chart", '{}', position=2)
    widget_id1 = queries.add_widget(dashboard_id, "portfolio_pie", '{}', position=0)
    widget_id2 = queries.add_widget(dashboard_id, "analysis_table", '{}', position=1)
    
    # List widgets
    widgets = queries.list_widgets(dashboard_id)
    
    assert len(widgets) == 3
    assert widgets[0]['id'] == widget_id1
    assert widgets[1]['id'] == widget_id2
    assert widgets[2]['id'] == widget_id3


def test_update_widget(test_db):
    """Update widget title and config."""
    from db import queries
    
    user_id = queries.create_user(email="test@example.com", name="Test User")
    dashboard_id = queries.create_dashboard(user_id, "Test Dashboard")
    widget_id = queries.add_widget(dashboard_id, "stock_chart", '{"tickers": "AAPL"}')
    
    # Update widget
    queries.update_widget(
        widget_id=widget_id,
        title="Updated Title",
        config='{"tickers": "AAPL,MSFT,GOOG"}',
        width=3,
        height=2
    )
    
    # Verify updates
    widget = queries.get_widget(widget_id)
    assert widget['title'] == "Updated Title"
    assert widget['config'] == '{"tickers": "AAPL,MSFT,GOOG"}'
    assert widget['width'] == 3
    assert widget['height'] == 2


def test_delete_widget(test_db):
    """Delete widget, verify it's gone."""
    from db import queries
    
    user_id = queries.create_user(email="test@example.com", name="Test User")
    dashboard_id = queries.create_dashboard(user_id, "Test Dashboard")
    widget_id = queries.add_widget(dashboard_id, "stock_chart", '{}')
    
    # Verify it exists
    assert queries.get_widget(widget_id) is not None
    
    # Delete it
    queries.delete_widget(widget_id)
    
    # Verify it's gone
    assert queries.get_widget(widget_id) is None


def test_reorder_widgets(test_db):
    """Reorder widgets, verify new positions."""
    from db import queries
    
    user_id = queries.create_user(email="test@example.com", name="Test User")
    dashboard_id = queries.create_dashboard(user_id, "Test Dashboard")
    
    # Add widgets
    widget_id1 = queries.add_widget(dashboard_id, "stock_chart", '{}', position=0)
    widget_id2 = queries.add_widget(dashboard_id, "portfolio_pie", '{}', position=1)
    widget_id3 = queries.add_widget(dashboard_id, "analysis_table", '{}', position=2)
    
    # Reorder: 3, 1, 2
    queries.reorder_widgets(dashboard_id, [widget_id3, widget_id1, widget_id2])
    
    # Verify new order
    widgets = queries.list_widgets(dashboard_id)
    assert widgets[0]['id'] == widget_id3
    assert widgets[0]['position'] == 0
    assert widgets[1]['id'] == widget_id1
    assert widgets[1]['position'] == 1
    assert widgets[2]['id'] == widget_id2
    assert widgets[2]['position'] == 2


# ============================================================================
# WIDGET CONFIG VALIDATION
# ============================================================================

def test_widget_config_stored_as_json(test_db):
    """Config should be stored and retrieved as proper JSON."""
    from db import queries
    
    user_id = queries.create_user(email="test@example.com", name="Test User")
    dashboard_id = queries.create_dashboard(user_id, "Test Dashboard")
    
    config = {
        "tickers": "AAPL,MSFT",
        "period": "1y",
        "chart_type": "candlestick"
    }
    
    widget_id = queries.add_widget(
        dashboard_id=dashboard_id,
        widget_type="stock_chart",
        config=json.dumps(config)
    )
    
    # Retrieve and verify
    widget = queries.get_widget(widget_id)
    stored_config = json.loads(widget['config'])
    
    assert stored_config == config
    assert stored_config['tickers'] == "AAPL,MSFT"
    assert stored_config['period'] == "1y"


# ============================================================================
# HTML RENDERING TESTS
# ============================================================================

def test_dashboard_html_contains_grid(test_db):
    """Generated HTML should contain CSS grid layout."""
    from db import queries
    from helpers.dashboard_templates import generate_dashboard_html
    
    user_id = queries.create_user(email="test@example.com", name="Test User")
    dashboard_id = queries.create_dashboard(user_id, "Test Dashboard")
    
    dashboard = queries.get_dashboard(dashboard_id)
    widgets = queries.list_widgets(dashboard_id)
    
    html = generate_dashboard_html(dashboard, widgets)
    
    assert 'dashboard-grid' in html
    assert 'display: grid' in html
    assert 'grid-template-columns' in html


def test_dashboard_html_contains_widgets(test_db):
    """Generated HTML should render all widgets."""
    from db import queries
    from helpers.dashboard_templates import generate_dashboard_html
    
    user_id = queries.create_user(email="test@example.com", name="Test User")
    dashboard_id = queries.create_dashboard(user_id, "Test Dashboard")
    
    # Add widgets
    queries.add_widget(dashboard_id, "stock_chart", '{"tickers": "AAPL"}', title="Stock Chart")
    queries.add_widget(dashboard_id, "portfolio_pie", '{"group_by": "ticker"}', title="Portfolio")
    
    dashboard = queries.get_dashboard(dashboard_id)
    widgets = queries.list_widgets(dashboard_id)
    
    html = generate_dashboard_html(dashboard, widgets)
    
    assert 'Stock Chart' in html
    assert 'Portfolio' in html
    assert 'widget-card' in html


def test_dashboard_html_responsive(test_db):
    """HTML should contain mobile-first media queries."""
    from db import queries
    from helpers.dashboard_templates import generate_dashboard_html
    
    user_id = queries.create_user(email="test@example.com", name="Test User")
    dashboard_id = queries.create_dashboard(user_id, "Test Dashboard")
    
    dashboard = queries.get_dashboard(dashboard_id)
    widgets = []
    
    html = generate_dashboard_html(dashboard, widgets)
    
    assert '@media' in html
    assert '768px' in html or '767px' in html
    assert '1024px' in html


def test_stock_chart_widget_renders(test_db):
    """Stock chart widget should contain TradingView/lightweight-charts embed."""
    from helpers.dashboard_templates import render_stock_chart_widget
    
    config = {"tickers": "AAPL", "period": "1y", "chart_type": "candlestick"}
    html = render_stock_chart_widget("test-widget-1", config)
    
    assert html is not None
    assert len(html) > 0
    # Should contain chart library reference or container
    assert 'chart' in html.lower() or 'tradingview' in html.lower()


def test_portfolio_pie_widget_renders(test_db):
    """Portfolio pie widget should contain Plotly.js chart."""
    from helpers.dashboard_templates import render_portfolio_pie_widget
    
    config = {"group_by": "category"}
    html = render_portfolio_pie_widget("test-widget-2", config)
    
    assert html is not None
    assert len(html) > 0
    # Should contain Plotly reference
    assert 'plotly' in html.lower() or 'pie' in html.lower()


# ============================================================================
# MCP TOOL TESTS
# ============================================================================

def test_create_dashboard_tool(test_db):
    """MCP tool should create dashboard and return URL."""
    from db import queries
    from tools.dashboards import _create_dashboard_impl
    
    # Create user first
    user_id = queries.create_user(email="test@example.com", name="Test User")
    
    # Call tool implementation
    result_json = _create_dashboard_impl(
        user_id=user_id,
        name="Test Dashboard",
        description="Test",
        layout="grid"
    )
    
    result = json.loads(result_json)
    
    assert 'id' in result
    assert 'name' in result
    assert 'url' in result
    assert result['name'] == "Test Dashboard"
    assert '/d/' in result['url']


def test_add_widget_tool(test_db):
    """MCP tool should add widget with parsed JSON config."""
    from db import queries
    from tools.dashboards import _add_widget_impl
    
    user_id = queries.create_user(email="test@example.com", name="Test User")
    dashboard_id = queries.create_dashboard(user_id, "Test Dashboard")
    
    # Call tool implementation
    config_str = '{"tickers": "AAPL,MSFT", "period": "1y"}'
    result_json = _add_widget_impl(
        dashboard_id=dashboard_id,
        widget_type="stock_chart",
        config=config_str,
        title="Stock Chart",
        width=2,
        height=1
    )
    
    result = json.loads(result_json)
    
    assert 'id' in result
    assert 'widget_type' in result
    assert result['widget_type'] == "stock_chart"


def test_list_dashboards_tool(test_db):
    """MCP tool should return user's dashboards."""
    from db import queries
    from tools.dashboards import _list_dashboards_impl
    
    user_id = queries.create_user(email="test@example.com", name="Test User")
    queries.create_dashboard(user_id, "Dashboard 1")
    queries.create_dashboard(user_id, "Dashboard 2")
    
    # Call tool implementation
    result_json = _list_dashboards_impl(user_id)
    result = json.loads(result_json)
    
    assert isinstance(result, list)
    assert len(result) == 2
    assert result[0]['name'] == "Dashboard 1"
    assert result[1]['name'] == "Dashboard 2"
