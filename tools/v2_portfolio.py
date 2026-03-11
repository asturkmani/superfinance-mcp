"""Consolidated portfolio analytics tool."""

import json
import pandas as pd
from typing import Optional

from services.analytics import AnalyticsService
from services.holdings_service import HoldingsService
from services.reconciliation import reconcile_account, reconcile_user
from helpers.user_context import get_current_user_id


async def _get_portfolio_data(user_id: Optional[str] = None, account_id: Optional[str] = None) -> list:
    """Helper to get aggregated portfolio holdings with weights."""
    if not user_id:
        user_id = get_current_user_id()
        
    # Get all holdings
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
            # Skip cash, liabilities
            asset_type = (pos.get("asset_type") or "").lower()
            symbol = pos.get("symbol", "").upper()
            
            if not symbol or symbol == "LIABILITY" or " " in symbol:
                continue
                
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
        
    results.sort(key=lambda x: x["weight_pct"], reverse=True)
    
    return results


def register_portfolio_v2(server):
    """Register consolidated portfolio analytics tool."""

    @server.tool()
    async def portfolio(
        action: str,
        user_id: Optional[str] = None,
        account_id: Optional[str] = None,
        period: str = "1y",
        indicators: str = "rsi,macd,bollinger",
        group: str = "all"
    ) -> str:
        """
        Portfolio-aware analytics and reconciliation.

        Actions:
        - technicals: Technical indicators for all positions
        - risk: Risk metrics for all positions
        - performance: Performance metrics for all positions
        - ratios: Financial ratios for all positions
        - correlation: Correlation matrix for positions
        - reconcile: Reconcile holdings vs transaction history

        Args:
            action: Action to perform (technicals|risk|performance|ratios|correlation|reconcile)
            user_id: User ID (uses default if not provided)
            account_id: Optional specific account (omit for all accounts)
            period: Lookback period for analysis
            indicators: For technicals - comma-separated indicators
            group: For ratios - ratio group (profitability|valuation|solvency|all)

        Returns:
            JSON with portfolio analysis or reconciliation results

        Examples:
            portfolio(action="technicals", indicators="rsi")
            portfolio(action="risk", period="3y")
            portfolio(action="performance")
            portfolio(action="correlation", period="1y")
            portfolio(action="reconcile")
            portfolio(action="reconcile", account_id="acc_123")
        """
        try:
            if not user_id:
                user_id = get_current_user_id()

            if action == "reconcile":
                if account_id:
                    result = reconcile_account(account_id)
                    result["note"] = (
                        "SnapTrade transactions may take 24-48 hours to sync after execution. "
                        "Recent discrepancies are expected and should resolve on the next sync."
                    )
                    return json.dumps(result, indent=2, default=str)
                else:
                    result = reconcile_user(user_id)
                    result["note"] = (
                        "SnapTrade transactions may take 24-48 hours to sync after execution. "
                        "Recent discrepancies are expected and should resolve on the next sync."
                    )
                    for acc in result.get("results", []):
                        acc.pop("matched_details", None)
                    return json.dumps(result, indent=2, default=str)

            # For analytics actions, get portfolio data first
            holdings = await _get_portfolio_data(user_id, account_id)
            if not holdings:
                return json.dumps({"error": "No equity holdings found"})
                
            tickers = [h["symbol"] for h in holdings]

            if action == "technicals":
                indicator_list = [i.strip().lower() for i in indicators.split(",") if i.strip()]
                tech_data = AnalyticsService.get_technicals(tickers=tickers, indicators=indicator_list, period=period)
                
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
                
                return json.dumps({
                    "portfolio_tickers": len(tickers),
                    "data": result
                }, indent=2)

            elif action == "risk":
                risk_data = AnalyticsService.get_risk_metrics(tickers=tickers, period=period)
                
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
                        
                return json.dumps({
                    "portfolio_tickers": len(tickers),
                    "data": result
                }, indent=2)

            elif action == "performance":
                perf_data = AnalyticsService.get_performance(tickers=tickers, period=period)
                
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
                        
                return json.dumps({
                    "portfolio_tickers": len(tickers),
                    "data": result
                }, indent=2)

            elif action == "ratios":
                ratio_data = AnalyticsService.get_ratios(tickers=tickers, ratio_group=group)
                
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
                        
                return json.dumps({
                    "portfolio_tickers": len(tickers),
                    "data": result
                }, indent=2)

            elif action == "correlation":
                if len(holdings) < 2:
                    return json.dumps({"error": "Need at least 2 equity positions for correlation analysis"})
                    
                hist_data = AnalyticsService.get_historical_data(tickers=tickers, period=period)
                
                if "error" in hist_data:
                    return json.dumps(hist_data)
                    
                # Construct DataFrame for correlation
                prices = {}
                for ticker, data in hist_data.items():
                    if isinstance(data, list) and len(data) > 0:
                        df = pd.DataFrame(data)
                        close_col = None
                        for col in ["Close", "close", "Adj Close", "adj close"]:
                            if col in df.columns:
                                close_col = col
                                break
                                
                        if close_col:
                            if "Date" in df.columns:
                                df = df.set_index("Date")
                            elif "date" in df.columns:
                                df = df.set_index("date")
                                
                            prices[ticker] = df[close_col]
                
                if len(prices) < 2:
                    return json.dumps({"error": "Insufficient historical data for correlation analysis"})
                    
                price_df = pd.DataFrame(prices)
                corr_matrix = price_df.corr().round(4)
                corr_dict = corr_matrix.to_dict()
                
                weights = {h["symbol"]: h["weight_pct"] for h in holdings if h["symbol"] in corr_dict}
                
                return json.dumps({
                    "correlation_matrix": corr_dict,
                    "position_weights": weights,
                    "period": period
                }, indent=2)

            else:
                return json.dumps({
                    "error": f"Invalid action: {action}",
                    "valid_actions": ["technicals", "risk", "performance", "ratios", "correlation", "reconcile"]
                }, indent=2)

        except Exception as e:
            return json.dumps({"error": str(e)}, indent=2)
