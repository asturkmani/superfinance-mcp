"""Tests for portfolio analytics tools."""

import pytest
import json
from unittest.mock import AsyncMock, MagicMock, patch
from tools.analysis import _get_portfolio_data, register_analysis_tools

# Mock data
MOCK_HOLDINGS_RESPONSE = {
    "success": True,
    "accounts": [
        {
            "account_id": "acc1",
            "positions": [
                {
                    "symbol": "AAPL",
                    "name": "Apple Inc.",
                    "units": 10,
                    "market_value": 1500.0,
                    "asset_type": "equity"
                },
                {
                    "symbol": "MSFT",
                    "name": "Microsoft Corp.",
                    "units": 5,
                    "market_value": 1500.0,
                    "asset_type": "equity"
                },
                {
                    "symbol": "USD",
                    "units": 100,
                    "market_value": 100.0,
                    "asset_type": "cash"
                }
            ]
        }
    ]
}

@pytest.mark.asyncio
async def test_get_portfolio_data():
    """Test helper function to extract portfolio data."""
    with patch("services.holdings_service.HoldingsService.list_all_holdings", new_callable=AsyncMock) as mock_list:
        with patch("db.queries.get_or_create_default_user", return_value="user1"):
            mock_list.return_value = MOCK_HOLDINGS_RESPONSE
            
            result = await _get_portfolio_data(user_id="user1")
            
            assert len(result) == 2
            assert result[0]["symbol"] in ["AAPL", "MSFT"]
            assert result[1]["symbol"] in ["AAPL", "MSFT"]
            
            # Check weights (equal value = 50% each)
            assert result[0]["weight_pct"] == 50.0
            assert result[1]["weight_pct"] == 50.0
            
            # Check cash is excluded
            symbols = [r["symbol"] for r in result]
            assert "USD" not in symbols

@pytest.mark.asyncio
async def test_portfolio_technicals_tool():
    """Test portfolio_technicals tool."""
    # Mock server
    server = MagicMock()
    server.tool.return_value = lambda x: x
    
    # Mock services
    with patch("services.holdings_service.HoldingsService.list_all_holdings", new_callable=AsyncMock) as mock_list:
        with patch("services.analytics.AnalyticsService.get_technicals") as mock_tech:
            with patch("db.queries.get_or_create_default_user", return_value="user1"):
                # Setup mocks
                mock_list.return_value = MOCK_HOLDINGS_RESPONSE
                mock_tech.return_value = {
                    "AAPL": {"rsi": 60, "macd": 1.5},
                    "MSFT": {"rsi": 55, "macd": 2.0}
                }
                
                # Import the tool function (it's inside register_analysis_tools, so we need to access it differently
                # or just test the logic via a wrapper if we could. 
                # Since we can't easily import the inner function, we'll redefine the logic or structure the code differently.
                # Actually, in tools/analysis.py, the tools are defined inside the register function.
                # This makes them hard to test directly without registering them.
                
                # Alternative: We can import the register function and capture the tool.
                tools = {}
                def mock_tool_decorator(*args, **kwargs):
                    def decorator(func):
                        tools[func.__name__] = func
                        return func
                    return decorator
                
                server.tool = mock_tool_decorator
                register_analysis_tools(server)
                
                # Now we can call the tool
                tool = tools["portfolio_technicals"]
                result_json = await tool(user_id="user1")
                result = json.loads(result_json)
                
                assert "data" in result
                assert "AAPL" in result["data"]
                assert "MSFT" in result["data"]
                assert result["data"]["AAPL"]["technicals"]["rsi"] == 60
                assert result["data"]["AAPL"]["position"]["weight_pct"] == 50.0

@pytest.mark.asyncio
async def test_portfolio_correlation_tool():
    """Test portfolio_correlation tool."""
    server = MagicMock()
    tools = {}
    def mock_tool_decorator(*args, **kwargs):
        def decorator(func):
            tools[func.__name__] = func
            return func
        return decorator
    server.tool = mock_tool_decorator
    
    register_analysis_tools(server)
    tool = tools["portfolio_correlation"]
    
    with patch("services.holdings_service.HoldingsService.list_all_holdings", new_callable=AsyncMock) as mock_list:
        with patch("services.analytics.AnalyticsService.get_historical_data") as mock_hist:
            with patch("db.queries.get_or_create_default_user", return_value="user1"):
                mock_list.return_value = MOCK_HOLDINGS_RESPONSE
                
                # Mock historical data for correlation
                # Perfect correlation for simplicity
                mock_hist.return_value = {
                    "AAPL": [{"date": "2023-01-01", "close": 100}, {"date": "2023-01-02", "close": 101}],
                    "MSFT": [{"date": "2023-01-01", "close": 200}, {"date": "2023-01-02", "close": 202}]
                }
                
                result_json = await tool(user_id="user1")
                result = json.loads(result_json)
                
                assert "correlation_matrix" in result
                assert result["correlation_matrix"]["AAPL"]["MSFT"] > 0.9  # Should be highly correlated
                assert "position_weights" in result
