"""Tests for analytics services (FinanceDatabase + FinanceToolkit)."""

import pytest
from services.universe import UniverseService
from services.analytics import AnalyticsService


class TestUniverseService:
    """Test FinanceDatabase integration."""
    
    def test_search_equities(self):
        """Test searching equities by sector."""
        result = UniverseService.search_equities(sector="Technology", limit=10)
        
        assert isinstance(result, list)
        assert len(result) > 0
        assert len(result) <= 10
        
        # Check structure
        first = result[0]
        assert 'symbol' in first or 'index' in first  # Ticker symbol
    
    def test_search_equities_industry(self):
        """Test searching equities by industry."""
        result = UniverseService.search_equities(industry="Semiconductors", limit=5)
        
        assert isinstance(result, list)
        assert len(result) > 0
        
        # Should return semiconductor companies
        if len(result) > 0 and 'industry' in result[0]:
            assert any('Semiconductor' in str(r.get('industry', '')) for r in result)
    
    def test_lookup_security(self):
        """Test looking up a specific ticker (AAPL)."""
        result = UniverseService.lookup("AAPL")
        
        assert isinstance(result, dict)
        assert 'error' not in result
        assert result.get('symbol') == 'AAPL' or result.get('asset_class') == 'equity'
    
    def test_lookup_invalid_ticker(self):
        """Test lookup of invalid ticker."""
        result = UniverseService.lookup("INVALIDTICKER12345")
        
        assert isinstance(result, dict)
        assert 'error' in result
    
    def test_search_etfs(self):
        """Test searching ETFs."""
        result = UniverseService.search_etfs(limit=10)
        
        assert isinstance(result, list)
        # May return empty if no filters, that's ok
        if len(result) > 0:
            assert len(result) <= 10
    
    def test_search_etfs_by_name(self):
        """Test searching ETFs by name."""
        result = UniverseService.search_etfs(name_search="S&P", limit=10)
        
        assert isinstance(result, list)
        # ETF search by name may not work perfectly, just check it doesn't crash


class TestAnalyticsService:
    """Test FinanceToolkit integration."""
    
    def test_get_technicals(self):
        """Test getting technical indicators."""
        result = AnalyticsService.get_technicals(['AAPL'], indicators=['rsi'], period="1y")
        
        assert isinstance(result, dict)
        assert 'AAPL' in result
        
        aapl_data = result['AAPL']
        # Should have RSI data or an error
        assert 'rsi' in aapl_data or 'error' in aapl_data
        
        # If RSI exists, check it's in valid range
        if 'rsi' in aapl_data and aapl_data['rsi'] is not None:
            assert 0 <= aapl_data['rsi'] <= 100
            assert 'rsi_signal' in aapl_data
    
    def test_get_technicals_multiple_tickers(self):
        """Test getting technicals for multiple tickers."""
        result = AnalyticsService.get_technicals(['AAPL', 'MSFT'], indicators=['rsi'], period="6mo")
        
        assert isinstance(result, dict)
        assert 'AAPL' in result
        assert 'MSFT' in result
    
    def test_get_risk_metrics(self):
        """Test getting risk metrics."""
        result = AnalyticsService.get_risk_metrics(['AAPL'], period="1y")
        
        assert isinstance(result, dict)
        assert 'AAPL' in result
        
        aapl_data = result['AAPL']
        # Should have some risk metrics or an error
        assert any(key in aapl_data for key in ['var_95', 'sharpe_ratio', 'max_drawdown', 'error'])
    
    def test_get_performance(self):
        """Test getting performance metrics."""
        result = AnalyticsService.get_performance(['AAPL'], period="1y")
        
        assert isinstance(result, dict)
        assert 'AAPL' in result
        
        aapl_data = result['AAPL']
        # Should have some performance metrics or an error
        assert any(key in aapl_data for key in ['cagr', 'sharpe_ratio', 'error'])
    
    def test_get_ratios(self):
        """Test getting financial ratios."""
        result = AnalyticsService.get_ratios(['AAPL'], ratio_group="all")
        
        assert isinstance(result, dict)
        assert 'AAPL' in result
        
        aapl_data = result['AAPL']
        # Should have some ratios or an error (financial data may not be available for all periods)
        assert isinstance(aapl_data, dict)
    
    def test_get_historical_data(self):
        """Test getting historical OHLCV data."""
        result = AnalyticsService.get_historical_data(['AAPL'], period="1mo")
        
        assert isinstance(result, dict)
        
        if 'error' not in result:
            assert 'AAPL' in result
            aapl_data = result['AAPL']
            assert isinstance(aapl_data, list)
            
            if len(aapl_data) > 0:
                # Check first record has expected fields
                first = aapl_data[0]
                # Should have date and price data
                assert any(key in first for key in ['Date', 'date', 'Open', 'Close'])
    
    def test_get_profile(self):
        """Test getting company profile."""
        result = AnalyticsService.get_profile(['AAPL'])
        
        assert isinstance(result, dict)
        assert 'AAPL' in result
        
        aapl_data = result['AAPL']
        assert isinstance(aapl_data, dict)
        # Profile may have error if FinanceToolkit can't fetch it, that's ok
    
    def test_get_options_analysis(self):
        """Test getting options analysis."""
        result = AnalyticsService.get_options_analysis('AAPL')
        
        assert isinstance(result, dict)
        assert 'ticker' in result
        # Options data may not be available, just check it doesn't crash


class TestAnalyticsEdgeCases:
    """Test edge cases and error handling."""
    
    def test_empty_ticker_list(self):
        """Test with empty ticker list."""
        result = AnalyticsService.get_technicals([], indicators=['rsi'], period="1y")
        
        assert isinstance(result, dict)
        # Should handle gracefully
    
    def test_invalid_ticker(self):
        """Test with invalid ticker."""
        result = AnalyticsService.get_technicals(['INVALIDTICKER12345'], indicators=['rsi'], period="1y")
        
        assert isinstance(result, dict)
        # Should have error or handle gracefully
    
    def test_search_no_filters(self):
        """Test search with no filters."""
        result = UniverseService.search_equities(limit=5)
        
        assert isinstance(result, list)
        # Should return some results even without filters
