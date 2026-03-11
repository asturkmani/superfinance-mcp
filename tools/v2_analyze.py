"""Consolidated analysis tool."""

import json
from typing import Optional

from services.analytics import AnalyticsService


def register_analyze_v2(server):
    """Register consolidated analysis tool."""

    @server.tool()
    def analyze(
        action: str,
        tickers: str,
        period: str = "3y",
        indicators: str = "rsi,macd,bollinger",
        group: str = "all"
    ) -> str:
        """
        Analyze stocks with technical indicators, risk metrics, performance, and financial ratios.

        Actions:
        - technicals: Technical indicators (RSI, MACD, Bollinger, EMA)
        - risk: Risk metrics (VaR, CVaR, max drawdown, beta, Sharpe, Sortino)
        - performance: Performance metrics (CAGR, alpha, Sharpe, Sortino)
        - ratios: Financial ratios (profitability, valuation, solvency)

        Args:
            action: Action to perform (technicals|risk|performance|ratios)
            tickers: Comma-separated ticker symbols (e.g., "AAPL,MSFT,GOOGL")
            period: Time period for analysis (e.g., "1mo", "3mo", "1y", "3y", "5y")
            indicators: For technicals - comma-separated indicators (rsi,macd,bollinger,ema)
            group: For ratios - ratio group (profitability|valuation|solvency|all)

        Returns:
            JSON with analysis results

        Examples:
            analyze(action="technicals", tickers="AAPL", indicators="rsi,macd")
            analyze(action="risk", tickers="AAPL,MSFT", period="3y")
            analyze(action="performance", tickers="AAPL,MSFT,GOOGL", period="1y")
            analyze(action="ratios", tickers="AAPL", group="valuation")
        """
        try:
            ticker_list = [t.strip().upper() for t in tickers.split(",") if t.strip()]

            if not ticker_list:
                return json.dumps({"error": "No valid tickers provided"})

            if action == "technicals":
                indicator_list = [i.strip().lower() for i in indicators.split(",") if i.strip()]
                result = AnalyticsService.get_technicals(
                    tickers=ticker_list,
                    indicators=indicator_list,
                    period=period
                )
                return json.dumps(result, indent=2)

            elif action == "risk":
                result = AnalyticsService.get_risk_metrics(
                    tickers=ticker_list,
                    period=period
                )
                return json.dumps(result, indent=2)

            elif action == "performance":
                result = AnalyticsService.get_performance(
                    tickers=ticker_list,
                    period=period
                )
                return json.dumps(result, indent=2)

            elif action == "ratios":
                result = AnalyticsService.get_ratios(
                    tickers=ticker_list,
                    ratio_group=group
                )
                return json.dumps(result, indent=2)

            else:
                return json.dumps({
                    "error": f"Invalid action: {action}",
                    "valid_actions": ["technicals", "risk", "performance", "ratios"]
                }, indent=2)

        except Exception as e:
            return json.dumps({"error": str(e)}, indent=2)
