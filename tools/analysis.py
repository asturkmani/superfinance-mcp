"""Analysis tools - financial analytics via FinanceToolkit."""

import json
import pandas as pd
from typing import Optional
from services.analytics import AnalyticsService
from services.holdings_service import HoldingsService
from db import queries
from helpers.user_context import get_current_user_id


async def _get_portfolio_data(user_id: Optional[str] = None, account_id: Optional[str] = None) -> list:
    """Helper to get aggregated portfolio holdings with weights."""
    if not user_id:
        user_id = get_current_user_id()
        
    # Get all holdings (this handles price fetching too)
    data = await HoldingsService.list_all_holdings(user_id=user_id)
    
    if "error" in data:
        return []
        
    holdings = []
    
    # Filter by account if provided
    accounts = data.get("accounts", [])
    if account_id:
        accounts = [a for a in accounts if a["account_id"] == account_id]
        
    for account in accounts:
        for pos in account.get("positions", []):
            # Skip cash, liabilities, etc.
            asset_type = (pos.get("asset_type") or "").lower()
            symbol = pos.get("symbol", "").upper()
            
            # Skip obvious non-tickers
            if not symbol or symbol == "LIABILITY" or " " in symbol:
                continue
                
            # Skip cash
            if asset_type == "cash":
                continue
                
            holdings.append({
                "symbol": symbol,
                "market_value": pos.get("market_value", 0) or 0,
                "quantity": pos.get("units", 0) or 0,
                "name": pos.get("name")
            })
            
    # Aggregate by symbol
    grouped = {}
    total_mv = 0
    for h in holdings:
        sym = h["symbol"]
        mv = h["market_value"]
        qty = h["quantity"]
        
        if sym not in grouped:
            grouped[sym] = {"market_value": 0, "quantity": 0, "name": h["name"]}
            
        grouped[sym]["market_value"] += mv
        grouped[sym]["quantity"] += qty
        total_mv += mv
        
    # Calculate weights
    results = []
    for sym, data in grouped.items():
        weight = 0
        if total_mv > 0:
            weight = (data["market_value"] / total_mv) * 100
            
        results.append({
            "symbol": sym,
            "weight_pct": round(weight, 2),
            "market_value": round(data["market_value"], 2),
            "quantity": round(data["quantity"], 4),
            "name": data["name"]
        })
        
    # Sort by weight descending
    results.sort(key=lambda x: x["weight_pct"], reverse=True)
    
    return results


def register_analysis_tools(server):
    """Register FinanceToolkit analysis tools."""
    
    @server.tool()
    def get_technicals(
        tickers: str,
        indicators: str = "rsi,macd,bollinger",
        period: str = "1y"
    ) -> str:
        """
        Get technical indicators for one or more tickers.
        
        Args:
            tickers: Comma-separated ticker symbols (e.g., "AAPL,MSFT,GOOGL")
            indicators: Comma-separated indicator names (default: "rsi,macd,bollinger")
                Available: rsi, macd, bollinger, ema
            period: Time period (e.g., "1mo", "3mo", "6mo", "1y", "2y", "5y")
            
        Returns:
            JSON string with latest technical indicator values
            
        Technical Indicators:
            - RSI (Relative Strength Index): Momentum indicator (0-100)
              * >70 = overbought, <30 = oversold
            - MACD (Moving Average Convergence Divergence): Trend indicator
              * Includes MACD line, signal line, and histogram
            - Bollinger Bands: Volatility indicator
              * Upper/middle/lower bands for price volatility
            - EMA (Exponential Moving Average): Trend indicator
            
        Examples:
            - Get RSI for Apple: tickers="AAPL", indicators="rsi"
            - Get all indicators for tech stocks: tickers="AAPL,MSFT,GOOGL"
            - Get MACD for 2 years: tickers="TSLA", indicators="macd", period="2y"
        """
        try:
            ticker_list = [t.strip().upper() for t in tickers.split(",") if t.strip()]
            indicator_list = [i.strip().lower() for i in indicators.split(",") if i.strip()]
            
            if not ticker_list:
                return json.dumps({"error": "No valid tickers provided"})
            
            result = AnalyticsService.get_technicals(
                tickers=ticker_list,
                indicators=indicator_list,
                period=period
            )
            
            return json.dumps(result, indent=2)
            
        except Exception as e:
            return json.dumps({"error": str(e)})
    
    @server.tool()
    def get_risk_metrics(
        tickers: str,
        period: str = "3y"
    ) -> str:
        """
        Get risk metrics: VaR, CVaR, max drawdown, beta, Sharpe, Sortino.
        
        Args:
            tickers: Comma-separated ticker symbols (e.g., "AAPL,MSFT")
            period: Time period for analysis (default: "3y")
                Recommended: "3y" or "5y" for stable metrics
            
        Returns:
            JSON string with risk metrics
            
        Risk Metrics:
            - VaR (Value at Risk): Potential loss at 95% confidence
            - CVaR (Conditional VaR): Expected loss beyond VaR
            - Max Drawdown: Largest peak-to-trough decline
            - Beta: Volatility relative to market (SPY)
            - Sharpe Ratio: Risk-adjusted return (higher is better)
            - Sortino Ratio: Like Sharpe but only penalizes downside risk
            
        Examples:
            - Risk analysis for Apple: tickers="AAPL"
            - Compare tech stocks: tickers="AAPL,MSFT,GOOGL"
            - 5-year risk profile: tickers="TSLA", period="5y"
        """
        try:
            ticker_list = [t.strip().upper() for t in tickers.split(",") if t.strip()]
            
            if not ticker_list:
                return json.dumps({"error": "No valid tickers provided"})
            
            result = AnalyticsService.get_risk_metrics(
                tickers=ticker_list,
                period=period
            )
            
            return json.dumps(result, indent=2)
            
        except Exception as e:
            return json.dumps({"error": str(e)})
    
    @server.tool()
    def get_performance(
        tickers: str,
        period: str = "3y"
    ) -> str:
        """
        Get performance metrics: CAGR, alpha, Sharpe, Sortino.
        
        Args:
            tickers: Comma-separated ticker symbols (e.g., "AAPL,MSFT")
            period: Time period for analysis (default: "3y")
            
        Returns:
            JSON string with performance metrics
            
        Performance Metrics:
            - CAGR (Compound Annual Growth Rate): Annualized return
            - Alpha: Excess return vs. market benchmark
            - Sharpe Ratio: Risk-adjusted return
            - Sortino Ratio: Downside risk-adjusted return
            
        Examples:
            - Performance for Apple: tickers="AAPL"
            - Compare stocks: tickers="AAPL,MSFT,GOOGL,TSLA"
            - 5-year performance: tickers="SPY", period="5y"
        """
        try:
            ticker_list = [t.strip().upper() for t in tickers.split(",") if t.strip()]
            
            if not ticker_list:
                return json.dumps({"error": "No valid tickers provided"})
            
            result = AnalyticsService.get_performance(
                tickers=ticker_list,
                period=period
            )
            
            return json.dumps(result, indent=2)
            
        except Exception as e:
            return json.dumps({"error": str(e)})
    
    @server.tool()
    def get_ratios(
        tickers: str,
        group: str = "all"
    ) -> str:
        """
        Get financial ratios. Groups: profitability, valuation, solvency, all.
        
        Args:
            tickers: Comma-separated ticker symbols (e.g., "AAPL,MSFT")
            group: Ratio group (default: "all")
                - "profitability": ROE, ROA, profit margins
                - "valuation": P/E, P/B, P/S ratios
                - "solvency": Debt ratios, interest coverage
                - "all": All ratio groups
            
        Returns:
            JSON string with financial ratios
            
        Financial Ratios:
            Profitability:
            - ROE (Return on Equity): Net income / shareholder equity
            - ROA (Return on Assets): Net income / total assets
            
            Valuation:
            - P/E (Price-to-Earnings): Price / earnings per share
            - P/B (Price-to-Book): Price / book value per share
            
            Solvency:
            - Debt-to-Equity: Total debt / shareholder equity
            - Interest Coverage: EBIT / interest expense
            
        Examples:
            - All ratios for Apple: tickers="AAPL"
            - Valuation only: tickers="AAPL,MSFT", group="valuation"
            - Profitability check: tickers="TSLA", group="profitability"
        """
        try:
            ticker_list = [t.strip().upper() for t in tickers.split(",") if t.strip()]
            
            if not ticker_list:
                return json.dumps({"error": "No valid tickers provided"})
            
            result = AnalyticsService.get_ratios(
                tickers=ticker_list,
                ratio_group=group
            )
            
            return json.dumps(result, indent=2)
            
        except Exception as e:
            return json.dumps({"error": str(e)})
    
    @server.tool()
    def get_options_analysis(ticker: str) -> str:
        """
        Get options chain with Greeks for a ticker.
        
        Args:
            ticker: Ticker symbol (e.g., "AAPL")
            
        Returns:
            JSON string with options chain data including:
            - Strike prices
            - Expiration dates
            - Greeks (Delta, Gamma, Theta, Vega)
            - Implied volatility
            - Open interest
            
        Examples:
            - Get Apple options: ticker="AAPL"
            - Get Tesla options: ticker="TSLA"
        """
        try:
            ticker = ticker.strip().upper()
            
            result = AnalyticsService.get_options_analysis(ticker)
            
            return json.dumps(result, indent=2)
            
        except Exception as e:
            return json.dumps({"error": str(e)})
    
    @server.tool()
    def get_historical_data(
        tickers: str,
        period: str = "1y"
    ) -> str:
        """
        Get OHLCV historical price data.
        
        Args:
            tickers: Comma-separated ticker symbols (e.g., "AAPL,MSFT")
            period: Time period (e.g., "1mo", "3mo", "6mo", "1y", "2y", "5y")
            
        Returns:
            JSON string with historical OHLCV data:
            - Date
            - Open, High, Low, Close prices
            - Volume
            
        Examples:
            - Get Apple history: tickers="AAPL", period="1y"
            - Get multiple stocks: tickers="AAPL,MSFT,GOOGL", period="6mo"
            - Get 5-year data: tickers="SPY", period="5y"
        """
        try:
            ticker_list = [t.strip().upper() for t in tickers.split(",") if t.strip()]
            
            if not ticker_list:
                return json.dumps({"error": "No valid tickers provided"})
            
            result = AnalyticsService.get_historical_data(
                tickers=ticker_list,
                period=period
            )
            
            return json.dumps(result, indent=2)
            
        except Exception as e:
            return json.dumps({"error": str(e)})
    
    @server.tool()
    def get_profile(tickers: str) -> str:
        """
        Get company profile and key information.
        
        Args:
            tickers: Comma-separated ticker symbols (e.g., "AAPL,MSFT")
            
        Returns:
            JSON string with company profile:
            - Company name
            - Business description
            - Sector and industry
            - Market cap
            - Employee count
            - Headquarters location
            - Key executives
            
        Examples:
            - Get Apple profile: tickers="AAPL"
            - Get multiple profiles: tickers="AAPL,MSFT,GOOGL"
        """
        try:
            ticker_list = [t.strip().upper() for t in tickers.split(",") if t.strip()]
            
            if not ticker_list:
                return json.dumps({"error": "No valid tickers provided"})
            
            result = AnalyticsService.get_profile(tickers=ticker_list)
            
            return json.dumps(result, indent=2)
            
        except Exception as e:
            return json.dumps({"error": str(e)})

    # =========================================================================
    # PORTFOLIO-AWARE ANALYTICS
    # =========================================================================

    @server.tool()
    async def portfolio_technicals(
        user_id: Optional[str] = None,
        account_id: Optional[str] = None,
        indicators: str = "rsi,macd,bollinger"
    ) -> str:
        """
        Get technical indicators for all equity positions in your portfolio.
        No need to list tickers — reads directly from your holdings.

        Args:
            user_id: User ID (uses default if not provided)
            account_id: Optional specific account (omit for all accounts)
            indicators: Comma-separated indicators (default: rsi,macd,bollinger)
        """
        try:
            holdings = await _get_portfolio_data(user_id, account_id)
            if not holdings:
                return json.dumps({"error": "No equity holdings found"})
                
            tickers = [h["symbol"] for h in holdings]
            indicator_list = [i.strip().lower() for i in indicators.split(",") if i.strip()]
            
            # Get technicals
            tech_data = AnalyticsService.get_technicals(tickers=tickers, indicators=indicator_list)
            
            # Merge with holdings data
            result = {}
            for h in holdings:
                sym = h["symbol"]
                if sym in tech_data:
                    result[sym] = {
                        "position": {
                            "weight_pct": h["weight_pct"],
                            "market_value": h["market_value"],
                            "quantity": h["quantity"]
                        },
                        "technicals": tech_data[sym]
                    }
            
            final_result = {
                "portfolio_tickers": len(tickers),
                "data": result
            }
            return json.dumps(final_result, indent=2)
            
        except Exception as e:
            return json.dumps({"error": str(e)})

    @server.tool()
    async def portfolio_risk(
        user_id: Optional[str] = None,
        account_id: Optional[str] = None,
        period: str = "3y"
    ) -> str:
        """
        Get risk metrics for your portfolio: VaR, CVaR, max drawdown, beta, Sharpe, Sortino.
        Reads positions from your holdings automatically.

        Args:
            user_id: User ID (uses default if not provided)
            account_id: Optional specific account
            period: Lookback period (default: 3y)
        """
        try:
            holdings = await _get_portfolio_data(user_id, account_id)
            if not holdings:
                return json.dumps({"error": "No equity holdings found"})
                
            tickers = [h["symbol"] for h in holdings]
            
            # Get risk metrics
            risk_data = AnalyticsService.get_risk_metrics(tickers=tickers, period=period)
            
            # Merge with holdings data
            result = {}
            for h in holdings:
                sym = h["symbol"]
                if sym in risk_data:
                    result[sym] = {
                        "position": {
                            "weight_pct": h["weight_pct"],
                            "market_value": h["market_value"]
                        },
                        "risk": risk_data[sym]
                    }
                    
            final_result = {
                "portfolio_tickers": len(tickers),
                "data": result
            }
            return json.dumps(final_result, indent=2)
            
        except Exception as e:
            return json.dumps({"error": str(e)})

    @server.tool()
    async def portfolio_performance(
        user_id: Optional[str] = None,
        account_id: Optional[str] = None,
        period: str = "1y"
    ) -> str:
        """
        Get performance metrics for your portfolio positions.

        Args:
            user_id: User ID (uses default if not provided)
            account_id: Optional specific account
            period: Lookback period (default: 1y)
        """
        try:
            holdings = await _get_portfolio_data(user_id, account_id)
            if not holdings:
                return json.dumps({"error": "No equity holdings found"})
                
            tickers = [h["symbol"] for h in holdings]
            
            # Get performance metrics
            perf_data = AnalyticsService.get_performance(tickers=tickers, period=period)
            
            # Merge with holdings data
            result = {}
            for h in holdings:
                sym = h["symbol"]
                if sym in perf_data:
                    result[sym] = {
                        "position": {
                            "weight_pct": h["weight_pct"],
                            "market_value": h["market_value"]
                        },
                        "performance": perf_data[sym]
                    }
                    
            final_result = {
                "portfolio_tickers": len(tickers),
                "data": result
            }
            return json.dumps(final_result, indent=2)
            
        except Exception as e:
            return json.dumps({"error": str(e)})

    @server.tool()
    async def portfolio_ratios(
        user_id: Optional[str] = None,
        account_id: Optional[str] = None,
        group: str = "all"
    ) -> str:
        """
        Get financial ratios for all equity holdings.

        Args:
            user_id: User ID (uses default if not provided)
            account_id: Optional specific account
            group: Ratio group — profitability, valuation, solvency, or all
        """
        try:
            holdings = await _get_portfolio_data(user_id, account_id)
            if not holdings:
                return json.dumps({"error": "No equity holdings found"})
                
            tickers = [h["symbol"] for h in holdings]
            
            # Get ratios
            ratio_data = AnalyticsService.get_ratios(tickers=tickers, ratio_group=group)
            
            # Merge with holdings data
            result = {}
            for h in holdings:
                sym = h["symbol"]
                if sym in ratio_data:
                    result[sym] = {
                        "position": {
                            "weight_pct": h["weight_pct"],
                            "market_value": h["market_value"]
                        },
                        "ratios": ratio_data[sym]
                    }
                    
            final_result = {
                "portfolio_tickers": len(tickers),
                "data": result
            }
            return json.dumps(final_result, indent=2)
            
        except Exception as e:
            return json.dumps({"error": str(e)})

    @server.tool()
    async def portfolio_correlation(
        user_id: Optional[str] = None,
        account_id: Optional[str] = None,
        period: str = "1y"
    ) -> str:
        """
        Get correlation matrix for portfolio positions.
        Shows how correlated your holdings are with each other.

        Args:
            user_id: User ID (uses default if not provided)
            account_id: Optional specific account
            period: Lookback period (default: 1y)
        """
        try:
            holdings = await _get_portfolio_data(user_id, account_id)
            if len(holdings) < 2:
                return json.dumps({"error": "Need at least 2 equity positions for correlation analysis"})
                
            tickers = [h["symbol"] for h in holdings]
            
            # Get historical data
            hist_data = AnalyticsService.get_historical_data(tickers=tickers, period=period)
            
            if "error" in hist_data:
                return json.dumps(hist_data)
                
            # Construct DataFrame for correlation
            prices = {}
            for ticker, data in hist_data.items():
                if isinstance(data, list) and len(data) > 0:
                    # Extract close prices
                    df = pd.DataFrame(data)
                    # Check for variations of Close column name
                    close_col = None
                    for col in ["Close", "close", "Adj Close", "adj close"]:
                        if col in df.columns:
                            close_col = col
                            break
                            
                    if close_col:
                        # Ensure we have date index
                        if "Date" in df.columns:
                            df = df.set_index("Date")
                        elif "date" in df.columns:
                            df = df.set_index("date")
                            
                        prices[ticker] = df[close_col]
            
            if len(prices) < 2:
                return json.dumps({"error": "Insufficient historical data for correlation analysis"})
                
            # Combine into a single DataFrame
            price_df = pd.DataFrame(prices)
            
            # Calculate correlation
            corr_matrix = price_df.corr().round(4)
            
            # Convert to dict for JSON
            # Format: {'AAPL': {'MSFT': 0.8, 'GOOG': 0.7}, ...}
            corr_dict = corr_matrix.to_dict()
            
            # Add position weights for context
            weights = {h["symbol"]: h["weight_pct"] for h in holdings if h["symbol"] in corr_dict}
            
            return json.dumps({
                "correlation_matrix": corr_dict,
                "position_weights": weights,
                "period": period
            }, indent=2)
            
        except Exception as e:
            return json.dumps({"error": str(e)})
