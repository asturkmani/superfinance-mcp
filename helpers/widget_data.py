"""Fetch real data for dashboard widgets."""

import json
import asyncio
from typing import Optional, Dict, List
from db import queries
from services.analytics import AnalyticsService


async def fetch_all_widget_data(widgets: List[Dict], user_id: str) -> Dict:
    """
    Fetch real data for all widgets based on their type and config.
    
    Args:
        widgets: List of widget dicts with id, widget_type, config
        user_id: User ID for context
        
    Returns:
        Dict mapping widget_id -> data dict
    """
    data = {}
    
    for widget in widgets:
        widget_id = widget["id"]
        widget_type = widget["widget_type"]
        
        try:
            config_str = widget.get("config", "{}")
            config = json.loads(config_str) if config_str else {}
        except json.JSONDecodeError:
            config = {}
        
        try:
            if widget_type == "holdings_list":
                # Sync call
                data[widget_id] = await asyncio.to_thread(
                    fetch_holdings_data, user_id, config
                )
            elif widget_type == "portfolio_pie":
                data[widget_id] = await asyncio.to_thread(
                    fetch_portfolio_allocation, user_id, config
                )
            elif widget_type == "portfolio_treemap":
                data[widget_id] = await asyncio.to_thread(
                    fetch_portfolio_treemap, user_id, config
                )
            elif widget_type == "stock_chart":
                data[widget_id] = await asyncio.to_thread(
                    fetch_stock_chart_data, config
                )
            elif widget_type == "performance_chart":
                data[widget_id] = await asyncio.to_thread(
                    fetch_performance_data, config
                )
            elif widget_type == "correlation_heatmap":
                data[widget_id] = await asyncio.to_thread(
                    fetch_correlation_data, user_id, config
                )
            elif widget_type == "analysis_table":
                data[widget_id] = await asyncio.to_thread(
                    fetch_analysis_data, user_id, config
                )
            else:
                # Unknown widget type - return empty dict
                data[widget_id] = {}
                
        except Exception as e:
            # Catch errors per widget so one failure doesn't break the whole dashboard
            data[widget_id] = {"error": str(e)}
    
    return data


def fetch_holdings_data(user_id: str, config: dict) -> dict:
    """
    Fetch real holdings from SQLite for holdings_list widget.
    
    Args:
        user_id: User ID
        config: Widget config (optional account_id)
        
    Returns:
        Dict with "holdings" list
    """
    account_id = config.get("account_id")
    
    if account_id:
        holdings = queries.get_holdings_for_account(account_id)
    else:
        holdings = queries.get_all_holdings_for_user(user_id)
    
    # Format for the widget
    rows = []
    for h in holdings:
        asset_type = (h.get("asset_type") or "").lower()
        if asset_type == "cash":
            continue  # Skip cash in holdings list (or make configurable)
        
        rows.append({
            "symbol": h["symbol"],
            "name": h.get("name") or h["symbol"],
            "quantity": h.get("quantity", 0),
            "current_price": h.get("current_price"),
            "market_value": h.get("market_value"),
            "average_cost": h.get("average_cost"),
            "return_pct": _calc_return(h),
            "asset_type": h.get("asset_type"),
        })
    
    # Sort by market value descending
    rows.sort(key=lambda x: abs(x.get("market_value") or 0), reverse=True)
    
    return {"holdings": rows}


def fetch_portfolio_allocation(user_id: str, config: dict) -> dict:
    """
    Fetch portfolio data for pie chart.
    
    Args:
        user_id: User ID
        config: Widget config (optional account_id, group_by)
        
    Returns:
        Dict with "labels" and "values" lists
    """
    account_id = config.get("account_id")
    group_by = config.get("group_by", "ticker")
    
    if account_id:
        holdings = queries.get_holdings_for_account(account_id)
    else:
        holdings = queries.get_all_holdings_for_user(user_id)
    
    # Group by ticker, category, or asset_type
    groups = {}
    for h in holdings:
        asset_type = (h.get("asset_type") or "").lower()
        if asset_type == "cash":
            continue
        
        if group_by == "ticker":
            key = h["symbol"]
        elif group_by == "category":
            # Use classification if available
            from helpers.classification import get_classification
            cls = get_classification(h["symbol"])
            key = cls.get("category", "Other") if cls else "Other"
        elif group_by == "asset_type":
            key = h.get("asset_type", "Other") or "Other"
        else:
            key = h["symbol"]
        
        mv = abs(h.get("market_value") or 0)
        groups[key] = groups.get(key, 0) + mv
    
    # Sort by value
    sorted_groups = sorted(groups.items(), key=lambda x: x[1], reverse=True)
    labels = [g[0] for g in sorted_groups]
    values = [g[1] for g in sorted_groups]
    
    return {"labels": labels, "values": values}


def fetch_portfolio_treemap(user_id: str, config: dict) -> dict:
    """
    Fetch portfolio data for treemap.
    
    Args:
        user_id: User ID
        config: Widget config (optional account_id, group_by)
        
    Returns:
        Dict with "labels", "parents", "values" lists
    """
    account_id = config.get("account_id")
    group_by = config.get("group_by", "category")
    
    if account_id:
        holdings = queries.get_holdings_for_account(account_id)
    else:
        holdings = queries.get_all_holdings_for_user(user_id)
    
    # Build treemap hierarchy: Portfolio -> Category -> Ticker
    labels = ["Portfolio"]
    parents = [""]
    values = [0]
    
    categories = {}
    for h in holdings:
        asset_type = (h.get("asset_type") or "").lower()
        if asset_type == "cash":
            continue
        
        from helpers.classification import get_classification
        cls = get_classification(h["symbol"])
        category = cls.get("category", "Other") if cls else "Other"
        
        mv = abs(h.get("market_value") or 0)
        if category not in categories:
            categories[category] = {}
        
        sym = h["symbol"]
        categories[category][sym] = categories[category].get(sym, 0) + mv
    
    for cat, tickers in categories.items():
        labels.append(cat)
        parents.append("Portfolio")
        values.append(0)  # parent nodes have 0
        
        for ticker, mv in tickers.items():
            labels.append(ticker)
            parents.append(cat)
            values.append(mv)
    
    return {"labels": labels, "parents": parents, "values": values}


def fetch_stock_chart_data(config: dict) -> dict:
    """
    Fetch OHLCV data for stock chart.
    
    Args:
        config: Widget config (tickers, period)
        
    Returns:
        Dict with "charts" mapping ticker -> candle data
    """
    tickers = config.get("tickers", "AAPL")
    period = config.get("period", "1y")
    ticker_list = [t.strip() for t in tickers.split(",")]
    
    # Use AnalyticsService to get historical data
    result = AnalyticsService.get_historical_data(tickers=ticker_list, period=period)
    
    # Format for lightweight-charts
    charts = {}
    for ticker, data in result.get("tickers", {}).items():
        if isinstance(data, list):
            candles = []
            for d in data:
                candle = {
                    "time": d.get("date", d.get("Date", "")),
                    "open": d.get("open", d.get("Open")),
                    "high": d.get("high", d.get("High")),
                    "low": d.get("low", d.get("Low")),
                    "close": d.get("close", d.get("Close")),
                }
                # Skip if missing data
                if all(v is not None for k, v in candle.items() if k != "time"):
                    candles.append(candle)
            charts[ticker] = candles
    
    return {"charts": charts}


def fetch_performance_data(config: dict) -> dict:
    """
    Fetch historical performance data for performance chart.
    
    Args:
        config: Widget config (tickers, period)
        
    Returns:
        Dict with "series" mapping ticker -> [{date, value}]
    """
    tickers = config.get("tickers", "SPY")
    period = config.get("period", "1y")
    ticker_list = [t.strip() for t in tickers.split(",")]
    
    result = AnalyticsService.get_historical_data(tickers=ticker_list, period=period)
    
    # Normalize to percentage returns from start
    series = {}
    for ticker, data in result.get("tickers", {}).items():
        if isinstance(data, list) and len(data) > 0:
            first_close = None
            points = []
            for d in data:
                close = d.get("close", d.get("Close"))
                date = d.get("date", d.get("Date", ""))
                if close is not None:
                    if first_close is None:
                        first_close = close
                    pct = ((close - first_close) / first_close) if first_close else 0
                    points.append({"date": date, "value": round(pct, 4)})
            series[ticker] = points
    
    return {"series": series}


def fetch_correlation_data(user_id: str, config: dict) -> dict:
    """
    Fetch correlation matrix for portfolio positions.
    
    Args:
        user_id: User ID
        config: Widget config (optional account_id, period)
        
    Returns:
        Dict with "tickers" list and "z" 2D correlation matrix
    """
    account_id = config.get("account_id")
    period = config.get("period", "1y")
    
    # Get equity tickers from portfolio
    if account_id:
        holdings = queries.get_holdings_for_account(account_id)
    else:
        holdings = queries.get_all_holdings_for_user(user_id)
    
    tickers = []
    seen = set()
    for h in holdings:
        sym = h["symbol"]
        asset_type = (h.get("asset_type") or "").lower()
        if asset_type == "cash" or " " in sym or len(sym) > 10:
            continue
        if sym not in seen:
            seen.add(sym)
            tickers.append(sym)
    
    if len(tickers) < 2:
        return {"error": "Need at least 2 positions", "tickers": [], "z": []}
    
    # Fetch historical data and compute correlation
    result = AnalyticsService.get_historical_data(tickers=tickers, period=period)
    
    import pandas as pd
    close_data = {}
    for ticker, data in result.get("tickers", {}).items():
        if isinstance(data, list):
            closes = [
                d.get("close", d.get("Close")) 
                for d in data 
                if d.get("close", d.get("Close")) is not None
            ]
            if closes:
                close_data[ticker] = closes
    
    if len(close_data) < 2:
        return {"error": "Not enough data", "tickers": [], "z": []}
    
    # Align all series to same length (take minimum)
    min_len = min(len(v) for v in close_data.values())
    df = pd.DataFrame({k: v[-min_len:] for k, v in close_data.items()})
    corr = df.corr()
    
    ticker_labels = list(corr.columns)
    z = [[round(corr.loc[r, c], 3) for c in ticker_labels] for r in ticker_labels]
    
    return {"tickers": ticker_labels, "z": z}


def fetch_analysis_data(user_id: str, config: dict) -> dict:
    """
    Fetch analysis metrics for table widget.
    
    Args:
        user_id: User ID
        config: Widget config (optional tickers, metrics type)
        
    Returns:
        Analysis data from AnalyticsService
    """
    tickers_str = config.get("tickers")
    metrics = config.get("metrics", "risk")
    
    # If no tickers specified, use portfolio tickers
    if tickers_str:
        tickers = [t.strip() for t in tickers_str.split(",")]
    else:
        holdings = queries.get_all_holdings_for_user(user_id)
        tickers = list(set(
            h["symbol"] for h in holdings 
            if (h.get("asset_type") or "").lower() != "cash" 
            and " " not in h["symbol"] 
            and len(h["symbol"]) <= 10
        ))
    
    if not tickers:
        return {"error": "No tickers", "rows": []}
    
    if metrics == "risk":
        result = AnalyticsService.get_risk_metrics(tickers=tickers)
    elif metrics == "technicals":
        result = AnalyticsService.get_technicals(tickers=tickers)
    elif metrics == "performance":
        result = AnalyticsService.get_performance(tickers=tickers)
    else:
        result = AnalyticsService.get_risk_metrics(tickers=tickers)
    
    return result


def _calc_return(holding: dict) -> Optional[float]:
    """
    Calculate return percentage for a holding.
    
    Args:
        holding: Holding dict with average_cost and current_price
        
    Returns:
        Return percentage or None
    """
    cost = holding.get("average_cost")
    price = holding.get("current_price")
    if cost and price and cost > 0:
        return round((price - cost) / cost * 100, 2)
    return None
