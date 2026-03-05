"""FinanceToolkit service - financial analytics and ratios."""

from financetoolkit import Toolkit
import pandas as pd
import yfinance as yf
from typing import Optional, List
from datetime import datetime, timedelta


class AnalyticsService:
    """Financial analytics via FinanceToolkit."""
    
    @staticmethod
    def get_toolkit(
        tickers: list,
        start_date: Optional[str] = None,
        period: str = "5y"
    ) -> Toolkit:
        """
        Create a Toolkit instance. No API key needed (uses Yahoo Finance).
        
        Args:
            tickers: List of ticker symbols
            start_date: Start date (YYYY-MM-DD format), overrides period if provided
            period: Period string (e.g., "1mo", "3mo", "6mo", "1y", "3y", "5y")
            
        Returns:
            Toolkit instance
        """
        # Convert period to start_date if not provided
        if start_date is None:
            # Parse period string
            if 'mo' in period:
                months = int(period.replace('mo', ''))
                start_date = (datetime.now() - timedelta(days=months*30)).strftime('%Y-%m-%d')
            elif 'y' in period:
                years = int(period.replace('y', ''))
                start_date = (datetime.now() - timedelta(days=years*365)).strftime('%Y-%m-%d')
            elif 'd' in period:
                days = int(period.replace('d', ''))
                start_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
            else:
                # Default to 5 years if can't parse
                start_date = (datetime.now() - timedelta(days=5*365)).strftime('%Y-%m-%d')
        
        # Create toolkit WITHOUT api_key - falls back to Yahoo Finance
        toolkit = Toolkit(
            tickers=tickers,
            start_date=start_date
        )
        
        return toolkit
    
    @staticmethod
    def _df_to_dict(df, latest_only: bool = True):
        """Convert DataFrame to dict, handling NaN values."""
        if df is None or df.empty:
            return {}
        
        if latest_only:
            # Get only the latest row
            latest = df.iloc[-1] if len(df) > 0 else df.iloc[0]
            result = latest.to_dict()
        else:
            result = df.to_dict(orient='records')
        
        # Replace NaN with None
        if isinstance(result, dict):
            for key, value in result.items():
                if pd.isna(value):
                    result[key] = None
        elif isinstance(result, list):
            for record in result:
                for key, value in record.items():
                    if pd.isna(value):
                        record[key] = None
        
        return result
    
    @staticmethod
    def get_technicals(
        tickers: list,
        indicators: Optional[list] = None,
        period: str = "1y"
    ) -> dict:
        """
        Get technical indicators (RSI, MACD, Bollinger, EMA, etc.).
        
        Args:
            tickers: List of ticker symbols
            indicators: List of indicator names (None = all common indicators)
            period: Time period (default "1y")
            
        Returns:
            dict with latest technical indicator values per ticker
        """
        try:
            toolkit = AnalyticsService.get_toolkit(tickers, period=period)
            
            # Default indicators if none specified
            if indicators is None:
                indicators = ['rsi', 'macd', 'bollinger', 'ema']
            
            result = {}
            
            for ticker in tickers:
                ticker_result = {}
                
                try:
                    if 'rsi' in indicators:
                        rsi = toolkit.technicals.get_relative_strength_index()
                        if ticker in rsi.columns:
                            latest_rsi = rsi[ticker].iloc[-1]
                            ticker_result['rsi'] = None if pd.isna(latest_rsi) else float(latest_rsi)
                            
                            # Add interpretation
                            if ticker_result['rsi'] is not None:
                                if ticker_result['rsi'] > 70:
                                    ticker_result['rsi_signal'] = 'overbought'
                                elif ticker_result['rsi'] < 30:
                                    ticker_result['rsi_signal'] = 'oversold'
                                else:
                                    ticker_result['rsi_signal'] = 'neutral'
                    
                    if 'macd' in indicators:
                        macd_data = toolkit.technicals.get_moving_average_convergence_divergence()
                        if ticker in macd_data.columns.get_level_values(0):
                            latest_macd = macd_data[ticker].iloc[-1]
                            ticker_result['macd'] = {
                                'macd': None if pd.isna(latest_macd.get('MACD')) else float(latest_macd.get('MACD', 0)),
                                'signal': None if pd.isna(latest_macd.get('Signal')) else float(latest_macd.get('Signal', 0)),
                                'histogram': None if pd.isna(latest_macd.get('Histogram')) else float(latest_macd.get('Histogram', 0))
                            }
                    
                    if 'bollinger' in indicators:
                        bb = toolkit.technicals.get_bollinger_bands()
                        if ticker in bb.columns.get_level_values(0):
                            latest_bb = bb[ticker].iloc[-1]
                            ticker_result['bollinger'] = {
                                'upper': None if pd.isna(latest_bb.get('Upper Band')) else float(latest_bb.get('Upper Band', 0)),
                                'middle': None if pd.isna(latest_bb.get('Middle Band')) else float(latest_bb.get('Middle Band', 0)),
                                'lower': None if pd.isna(latest_bb.get('Lower Band')) else float(latest_bb.get('Lower Band', 0))
                            }
                    
                    if 'ema' in indicators:
                        ema = toolkit.technicals.get_exponential_moving_average()
                        if ticker in ema.columns:
                            latest_ema = ema[ticker].iloc[-1]
                            ticker_result['ema'] = None if pd.isna(latest_ema) else float(latest_ema)
                
                except Exception as e:
                    ticker_result['error'] = str(e)
                
                result[ticker] = ticker_result
            
            return result
            
        except Exception as e:
            return {"error": f"Technical analysis failed: {str(e)}"}
    
    @staticmethod
    def get_risk_metrics(tickers: list, period: str = "3y") -> dict:
        """
        Get risk metrics (VaR, CVaR, max drawdown, beta, etc.).
        
        Args:
            tickers: List of ticker symbols
            period: Time period (default "3y")
            
        Returns:
            dict with risk metrics per ticker
        """
        try:
            toolkit = AnalyticsService.get_toolkit(tickers, period=period)
            result = {}
            
            for ticker in tickers:
                ticker_result = {}
                
                try:
                    # Value at Risk (95% confidence)
                    var = toolkit.risk.get_value_at_risk(alpha=0.05)
                    if ticker in var.columns:
                        latest_var = var[ticker].iloc[-1]
                        ticker_result['var_95'] = None if pd.isna(latest_var) else float(latest_var)
                    
                    # Conditional VaR (CVaR)
                    cvar = toolkit.risk.get_conditional_value_at_risk(alpha=0.05)
                    if ticker in cvar.columns:
                        latest_cvar = cvar[ticker].iloc[-1]
                        ticker_result['cvar_95'] = None if pd.isna(latest_cvar) else float(latest_cvar)
                    
                    # Max Drawdown
                    max_dd = toolkit.risk.get_maximum_drawdown()
                    if ticker in max_dd.columns:
                        latest_dd = max_dd[ticker].iloc[-1]
                        ticker_result['max_drawdown'] = None if pd.isna(latest_dd) else float(latest_dd)
                    
                    # Beta (vs market)
                    try:
                        beta = toolkit.risk.get_beta()
                        if ticker in beta.columns:
                            latest_beta = beta[ticker].iloc[-1]
                            ticker_result['beta'] = None if pd.isna(latest_beta) else float(latest_beta)
                    except:
                        pass  # Beta may not be available for all tickers
                    
                    # Sharpe Ratio
                    sharpe = toolkit.performance.get_sharpe_ratio()
                    if ticker in sharpe.columns:
                        latest_sharpe = sharpe[ticker].iloc[-1]
                        ticker_result['sharpe_ratio'] = None if pd.isna(latest_sharpe) else float(latest_sharpe)
                    
                    # Sortino Ratio
                    sortino = toolkit.performance.get_sortino_ratio()
                    if ticker in sortino.columns:
                        latest_sortino = sortino[ticker].iloc[-1]
                        ticker_result['sortino_ratio'] = None if pd.isna(latest_sortino) else float(latest_sortino)
                
                except Exception as e:
                    ticker_result['error'] = str(e)
                
                result[ticker] = ticker_result
            
            return result
            
        except Exception as e:
            return {"error": f"Risk analysis failed: {str(e)}"}
    
    @staticmethod
    def get_performance(tickers: list, period: str = "3y") -> dict:
        """
        Get performance metrics (Sharpe, Sortino, alpha, CAGR, etc.).
        
        Args:
            tickers: List of ticker symbols
            period: Time period (default "3y")
            
        Returns:
            dict with performance metrics per ticker
        """
        try:
            toolkit = AnalyticsService.get_toolkit(tickers, period=period)
            result = {}
            
            for ticker in tickers:
                ticker_result = {}
                
                try:
                    # CAGR
                    cagr = toolkit.performance.get_cagr()
                    if ticker in cagr.columns:
                        latest_cagr = cagr[ticker].iloc[-1]
                        ticker_result['cagr'] = None if pd.isna(latest_cagr) else float(latest_cagr)
                    
                    # Alpha
                    try:
                        alpha = toolkit.performance.get_alpha()
                        if ticker in alpha.columns:
                            latest_alpha = alpha[ticker].iloc[-1]
                            ticker_result['alpha'] = None if pd.isna(latest_alpha) else float(latest_alpha)
                    except:
                        pass
                    
                    # Sharpe Ratio
                    sharpe = toolkit.performance.get_sharpe_ratio()
                    if ticker in sharpe.columns:
                        latest_sharpe = sharpe[ticker].iloc[-1]
                        ticker_result['sharpe_ratio'] = None if pd.isna(latest_sharpe) else float(latest_sharpe)
                    
                    # Sortino Ratio
                    sortino = toolkit.performance.get_sortino_ratio()
                    if ticker in sortino.columns:
                        latest_sortino = sortino[ticker].iloc[-1]
                        ticker_result['sortino_ratio'] = None if pd.isna(latest_sortino) else float(latest_sortino)
                
                except Exception as e:
                    ticker_result['error'] = str(e)
                
                result[ticker] = ticker_result
            
            return result
            
        except Exception as e:
            return {"error": f"Performance analysis failed: {str(e)}"}
    
    @staticmethod
    def get_ratios(tickers: list, ratio_group: str = "all") -> dict:
        """
        Get financial ratios (profitability, valuation, solvency).
        
        Args:
            tickers: List of ticker symbols
            ratio_group: "profitability", "valuation", "solvency", or "all"
            
        Returns:
            dict with financial ratios per ticker
        """
        try:
            toolkit = AnalyticsService.get_toolkit(tickers, period="5y")
            result = {}
            
            for ticker in tickers:
                ticker_result = {}
                
                try:
                    if ratio_group in ["profitability", "all"]:
                        # ROE, ROA, etc.
                        try:
                            roe = toolkit.ratios.get_return_on_equity()
                            if ticker in roe.columns:
                                latest_roe = roe[ticker].iloc[-1]
                                ticker_result['roe'] = None if pd.isna(latest_roe) else float(latest_roe)
                        except:
                            pass
                    
                    if ratio_group in ["valuation", "all"]:
                        # P/E, P/B, etc.
                        try:
                            pe = toolkit.ratios.get_price_earnings_ratio()
                            if ticker in pe.columns:
                                latest_pe = pe[ticker].iloc[-1]
                                ticker_result['pe_ratio'] = None if pd.isna(latest_pe) else float(latest_pe)
                        except:
                            pass
                    
                    if ratio_group in ["solvency", "all"]:
                        # Debt ratios
                        try:
                            debt_equity = toolkit.ratios.get_debt_to_equity_ratio()
                            if ticker in debt_equity.columns:
                                latest_de = debt_equity[ticker].iloc[-1]
                                ticker_result['debt_to_equity'] = None if pd.isna(latest_de) else float(latest_de)
                        except:
                            pass
                
                except Exception as e:
                    ticker_result['error'] = str(e)
                
                result[ticker] = ticker_result
            
            return result
            
        except Exception as e:
            return {"error": f"Ratio analysis failed: {str(e)}"}
    
    @staticmethod
    def get_options_analysis(ticker: str) -> dict:
        """
        Get options chain + Greeks.
        
        Args:
            ticker: Ticker symbol
            
        Returns:
            dict with options data
        """
        try:
            toolkit = AnalyticsService.get_toolkit([ticker], period="1y")
            
            # Get options chain
            options_data = toolkit.options.get_option_chains()
            
            if options_data is None or options_data.empty:
                return {"ticker": ticker, "message": "No options data available"}
            
            result = AnalyticsService._df_to_dict(options_data, latest_only=False)
            
            return {"ticker": ticker, "options": result}
            
        except Exception as e:
            return {"error": f"Options analysis failed: {str(e)}"}
    
    @staticmethod
    def get_historical_data(tickers: list, period: str = "1y") -> dict:
        """
        Get OHLCV historical data.
        
        Args:
            tickers: List of ticker symbols
            period: Time period (default "1y")
            
        Returns:
            dict with historical OHLCV data per ticker
        """
        try:
            toolkit = AnalyticsService.get_toolkit(tickers, period=period)
            
            # Get historical data
            hist_data = toolkit.get_historical_data()
            
            if hist_data is None or hist_data.empty:
                return {"error": "No historical data available"}
            
            result = {}
            
            # FinanceToolkit returns MultiIndex columns: (field, ticker)
            # We need to transpose to get ticker-first structure
            for ticker in tickers:
                # Extract OHLCV fields for this ticker
                ohlcv_fields = ['Open', 'High', 'Low', 'Close', 'Volume']
                ticker_columns = [(field, ticker) for field in ohlcv_fields if (field, ticker) in hist_data.columns]
                
                if ticker_columns:
                    # Select just these columns and rename them
                    ticker_data = hist_data[ticker_columns].copy()
                    # Flatten the MultiIndex column names
                    ticker_data.columns = [col[0] for col in ticker_data.columns]
                    
                    # Convert to records
                    # Ensure index is converted to string format (YYYY-MM-DD)
                    if isinstance(ticker_data.index, pd.PeriodIndex):
                        ticker_data.index = ticker_data.index.astype(str)
                    elif isinstance(ticker_data.index, pd.DatetimeIndex):
                        ticker_data.index = ticker_data.index.strftime('%Y-%m-%d')
                        
                    records = ticker_data.reset_index().to_dict(orient='records')
                    
                    # Replace NaN with None
                    for record in records:
                        for key, value in record.items():
                            if pd.isna(value):
                                record[key] = None
                    
                    result[ticker] = records
            
            return result
            
        except Exception as e:
            return {"error": f"Historical data fetch failed: {str(e)}"}
    
    @staticmethod
    def get_profile(tickers: list) -> dict:
        """
        Get company profile (replaces get_stock_info).
        Uses yfinance directly since FinanceToolkit's profile requires FMP API key.
        
        Args:
            tickers: List of ticker symbols
            
        Returns:
            dict with company profile per ticker
        """
        try:
            result = {}
            
            for ticker in tickers:
                try:
                    # Use yfinance directly for profile info
                    stock = yf.Ticker(ticker)
                    info = stock.info
                    
                    if info and info.get('regularMarketPrice') is not None:
                        # Extract key profile fields
                        profile_dict = {
                            'symbol': ticker,
                            'name': info.get('longName') or info.get('shortName'),
                            'sector': info.get('sector'),
                            'industry': info.get('industry'),
                            'country': info.get('country'),
                            'website': info.get('website'),
                            'description': info.get('longBusinessSummary'),
                            'market_cap': info.get('marketCap'),
                            'employees': info.get('fullTimeEmployees'),
                            'city': info.get('city'),
                            'state': info.get('state'),
                            'currency': info.get('currency'),
                            'exchange': info.get('exchange')
                        }
                        
                        # Replace NaN with None
                        for key, value in profile_dict.items():
                            if pd.isna(value):
                                profile_dict[key] = None
                        
                        result[ticker] = profile_dict
                    else:
                        result[ticker] = {"error": "Profile not available"}
                
                except Exception as e:
                    result[ticker] = {"error": str(e)}
            
            return result
            
        except Exception as e:
            return {"error": f"Profile fetch failed: {str(e)}"}
