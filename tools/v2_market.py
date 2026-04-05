"""Consolidated market data tool."""

import json

import pandas as pd
import yfinance as yf


class FinancialType(str, Enum):
    income_stmt = "income_stmt"
    quarterly_income_stmt = "quarterly_income_stmt"
    balance_sheet = "balance_sheet"
    quarterly_balance_sheet = "quarterly_balance_sheet"
    cashflow = "cashflow"
    quarterly_cashflow = "quarterly_cashflow"


class HolderType(str, Enum):
    major_holders = "major_holders"
    institutional_holders = "institutional_holders"
    mutualfund_holders = "mutualfund_holders"
    insider_transactions = "insider_transactions"
    insider_purchases = "insider_purchases"
    insider_roster_holders = "insider_roster_holders"


class RecommendationType(str, Enum):
    recommendations = "recommendations"
    upgrades_downgrades = "upgrades_downgrades"


def register_market_v2(server):
    """Register consolidated market data tool."""

    @server.tool()
    def market(
        action: str,
        tickers: str = None,
        ticker: str = None,
        period: str = "1mo",
        interval: str = "1d",
        from_currency: str = None,
        to_currency: str = None,
        financial_type: str = None,
        holder_type: str = None,
        recommendation_type: str = "recommendations",
        months_back: int = 12
    ) -> str:
        """
        Get market data from Yahoo Finance.

        Actions:
        - profile: Company info, metrics, and key stats (uses tickers)
        - history: Historical OHLCV data (uses tickers, period, interval)
        - quote: Current price and trading info (uses tickers)
        - fx: Foreign exchange rate (uses from_currency, to_currency)
        - actions: Dividends and stock splits (uses ticker)
        - financials: Financial statements (uses ticker, financial_type)
        - holders: Holder information (uses ticker, holder_type)
        - recommendations: Analyst recommendations (uses ticker, recommendation_type, months_back)
        - news: Latest news (uses ticker)

        Args:
            action: Action to perform (profile|history|quote|fx|actions|financials|holders|recommendations|news)
            tickers: Comma-separated ticker symbols (for profile|history|quote)
            ticker: Single ticker symbol (for actions|financials|holders|recommendations|news)
            period: Time period for history - 1d,5d,1mo,3mo,6mo,1y,2y,5y,10y,ytd,max
            interval: Data interval for history - 1m,2m,5m,15m,30m,60m,90m,1h,1d,5d,1wk,1mo,3mo
            from_currency: Source currency for FX (e.g., "GBP")
            to_currency: Target currency for FX (e.g., "USD")
            financial_type: Type for financials - income_stmt, quarterly_income_stmt, balance_sheet, quarterly_balance_sheet, cashflow, quarterly_cashflow
            holder_type: Type for holders - major_holders, institutional_holders, mutualfund_holders, insider_transactions, insider_purchases, insider_roster_holders
            recommendation_type: Type for recommendations - recommendations, upgrades_downgrades
            months_back: Lookback for upgrades_downgrades (default 12)

        Returns:
            JSON with market data

        Examples:
            market(action="quote", tickers="AAPL,MSFT")
            market(action="history", tickers="AAPL", period="1y", interval="1d")
            market(action="profile", tickers="AAPL")
            market(action="fx", from_currency="GBP", to_currency="USD")
            market(action="financials", ticker="AAPL", financial_type="income_stmt")
        """
        try:
            if action == "profile":
                if not tickers:
                    return json.dumps({"error": "tickers required for profile action"}, indent=2)
                return _get_profile(tickers)

            elif action == "history":
                if not tickers:
                    return json.dumps({"error": "tickers required for history action"}, indent=2)
                return _get_historical_prices(tickers, period, interval)

            elif action == "quote":
                if not tickers:
                    return json.dumps({"error": "tickers required for quote action"}, indent=2)
                return _get_stock_info(tickers)

            elif action == "fx":
                if not from_currency or not to_currency:
                    return json.dumps({"error": "from_currency and to_currency required for fx action"}, indent=2)
                return _get_fx_rate(from_currency, to_currency)

            elif action == "actions":
                if not ticker:
                    return json.dumps({"error": "ticker required for actions action"}, indent=2)
                return _get_stock_actions(ticker)

            elif action == "financials":
                if not ticker or not financial_type:
                    return json.dumps({"error": "ticker and financial_type required for financials action"}, indent=2)
                return _get_financial_statement(ticker, financial_type)

            elif action == "holders":
                if not ticker or not holder_type:
                    return json.dumps({"error": "ticker and holder_type required for holders action"}, indent=2)
                return _get_holder_info(ticker, holder_type)

            elif action == "recommendations":
                if not ticker:
                    return json.dumps({"error": "ticker required for recommendations action"}, indent=2)
                return _get_recommendations(ticker, recommendation_type, months_back)

            elif action == "news":
                if not ticker:
                    return json.dumps({"error": "ticker required for news action"}, indent=2)
                return _get_news(ticker)

            else:
                return json.dumps({
                    "error": f"Invalid action: {action}",
                    "valid_actions": ["profile", "history", "quote", "fx", "actions", "financials", "holders", "recommendations", "news"]
                }, indent=2)

        except Exception as e:
            return json.dumps({"error": str(e)}, indent=2)


def _get_profile(tickers: str) -> str:
    """Get company profile and info."""
    ticker_list = [t.strip().upper() for t in tickers.split(",") if t.strip()]
    if len(ticker_list) == 1:
        company = yf.Ticker(ticker_list[0])
        try:
            if company.isin is None:
                return json.dumps({"error": f"Ticker {ticker_list[0]} not found"})
        except Exception as e:
            return json.dumps({"error": str(e)})
        info = company.info
        return json.dumps(info, indent=2)
    else:
        result = {}
        ticker_str = " ".join(ticker_list)
        try:
            batch = yf.Tickers(ticker_str)
            for tkr in ticker_list:
                try:
                    company = batch.tickers.get(tkr)
                    if company:
                        info = company.info
                        if info and info.get("regularMarketPrice") is not None:
                            result[tkr] = info
                        else:
                            result[tkr] = {"error": f"No data available for {tkr}"}
                    else:
                        result[tkr] = {"error": f"Ticker {tkr} not found"}
                except Exception as e:
                    result[tkr] = {"error": str(e)}
        except Exception as e:
            return json.dumps({"error": f"Batch fetch failed: {str(e)}"})
        return json.dumps(result, indent=2)


def _get_historical_prices(tickers: str, period: str, interval: str) -> str:
    """Get historical OHLCV data."""
    ticker_list = [t.strip().upper() for t in tickers.split(",") if t.strip()]
    if len(ticker_list) == 1:
        company = yf.Ticker(ticker_list[0])
        try:
            if company.isin is None:
                return json.dumps({"error": f"Ticker {ticker_list[0]} not found"})
        except Exception as e:
            return json.dumps({"error": str(e)})
        hist_data = company.history(period=period, interval=interval)
        hist_data = hist_data.reset_index(names="Date")
        return hist_data.to_json(orient="records", date_format="iso")
    else:
        result = {}
        for tkr in ticker_list:
            try:
                company = yf.Ticker(tkr)
                hist_data = company.history(period=period, interval=interval)
                hist_data = hist_data.reset_index(names="Date")
                result[tkr] = json.loads(hist_data.to_json(orient="records", date_format="iso"))
            except Exception as e:
                result[tkr] = {"error": str(e)}
        return json.dumps(result, indent=2)


def _get_stock_info(tickers: str) -> str:
    """Get current quote/price info."""
    ticker_list = [t.strip().upper() for t in tickers.split(",") if t.strip()]
    if not ticker_list:
        return json.dumps({"error": "No valid tickers provided"})

    if len(ticker_list) == 1:
        company = yf.Ticker(ticker_list[0])
        try:
            if company.isin is None:
                return json.dumps({"error": f"Ticker {ticker_list[0]} not found"})
        except Exception as e:
            return json.dumps({"error": str(e)})
        info = company.info
        return json.dumps(info, indent=2)
    else:
        result = {}
        ticker_str = " ".join(ticker_list)
        try:
            batch = yf.Tickers(ticker_str)
            for tkr in ticker_list:
                try:
                    company = batch.tickers.get(tkr)
                    if company:
                        info = company.info
                        if info and info.get("regularMarketPrice") is not None:
                            result[tkr] = info
                        else:
                            result[tkr] = {"error": f"No data for {tkr}"}
                    else:
                        result[tkr] = {"error": f"Ticker {tkr} not found"}
                except Exception as e:
                    result[tkr] = {"error": str(e)}
        except Exception as e:
            return json.dumps({"error": f"Batch fetch failed: {str(e)}"})
        return json.dumps(result, indent=2)


def _get_fx_rate(from_currency: str, to_currency: str) -> str:
    """Get FX rate."""
    try:
        ticker_symbol = f"{from_currency.upper()}{to_currency.upper()}=X"
        ticker = yf.Ticker(ticker_symbol)
        info = ticker.info

        rate = info.get("regularMarketPrice")
        if rate is None:
            return json.dumps({
                "error": f"Could not get rate for {from_currency}/{to_currency}",
                "message": "Check that both currency codes are valid"
            })

        return json.dumps({
            "success": True,
            "from": from_currency.upper(),
            "to": to_currency.upper(),
            "rate": rate,
            "bid": info.get("bid"),
            "ask": info.get("ask"),
            "day_high": info.get("dayHigh"),
            "day_low": info.get("dayLow"),
            "description": f"1 {from_currency.upper()} = {rate} {to_currency.upper()}"
        }, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)}, indent=2)


def _get_stock_actions(ticker: str) -> str:
    """Get dividends and splits."""
    try:
        company = yf.Ticker(ticker)
        actions_df = company.actions
        actions_df = actions_df.reset_index(names="Date")
        return actions_df.to_json(orient="records", date_format="iso")
    except Exception as e:
        return json.dumps({"error": str(e)})


def _get_financial_statement(ticker: str, financial_type: str) -> str:
    """Get financial statements."""
    company = yf.Ticker(ticker)
    try:
        if company.isin is None:
            return json.dumps({"error": f"Ticker {ticker} not found"})
    except Exception as e:
        return json.dumps({"error": str(e)})

    if financial_type == "income_stmt":
        financial_statement = company.income_stmt
    elif financial_type == "quarterly_income_stmt":
        financial_statement = company.quarterly_income_stmt
    elif financial_type == "balance_sheet":
        financial_statement = company.balance_sheet
    elif financial_type == "quarterly_balance_sheet":
        financial_statement = company.quarterly_balance_sheet
    elif financial_type == "cashflow":
        financial_statement = company.cashflow
    elif financial_type == "quarterly_cashflow":
        financial_statement = company.quarterly_cashflow
    else:
        return json.dumps({"error": f"Invalid financial_type: {financial_type}"})

    result = []
    for column in financial_statement.columns:
        if isinstance(column, pd.Timestamp):
            date_str = column.strftime("%Y-%m-%d")
        else:
            date_str = str(column)

        date_obj = {"date": date_str}
        for index, value in financial_statement[column].items():
            date_obj[index] = None if pd.isna(value) else value

        result.append(date_obj)

    return json.dumps(result, indent=2)


def _get_holder_info(ticker: str, holder_type: str) -> str:
    """Get holder information."""
    company = yf.Ticker(ticker)
    try:
        if company.isin is None:
            return json.dumps({"error": f"Ticker {ticker} not found"})
    except Exception as e:
        return json.dumps({"error": str(e)})

    if holder_type == "major_holders":
        return company.major_holders.reset_index(names="metric").to_json(orient="records")
    elif holder_type == "institutional_holders":
        return company.institutional_holders.to_json(orient="records")
    elif holder_type == "mutualfund_holders":
        return company.mutualfund_holders.to_json(orient="records", date_format="iso")
    elif holder_type == "insider_transactions":
        return company.insider_transactions.to_json(orient="records", date_format="iso")
    elif holder_type == "insider_purchases":
        return company.insider_purchases.to_json(orient="records", date_format="iso")
    elif holder_type == "insider_roster_holders":
        return company.insider_roster_holders.to_json(orient="records", date_format="iso")
    else:
        return json.dumps({"error": f"Invalid holder_type: {holder_type}"})


def _get_recommendations(ticker: str, recommendation_type: str, months_back: int) -> str:
    """Get recommendations."""
    company = yf.Ticker(ticker)
    try:
        if company.isin is None:
            return json.dumps({"error": f"Ticker {ticker} not found"})
    except Exception as e:
        return json.dumps({"error": str(e)})

    try:
        if recommendation_type == "recommendations":
            return company.recommendations.to_json(orient="records")
        elif recommendation_type == "upgrades_downgrades":
            upgrades_downgrades = company.upgrades_downgrades.reset_index()
            cutoff_date = pd.Timestamp.now() - pd.DateOffset(months=months_back)
            upgrades_downgrades = upgrades_downgrades[
                upgrades_downgrades["GradeDate"] >= cutoff_date
            ]
            upgrades_downgrades = upgrades_downgrades.sort_values("GradeDate", ascending=False)
            latest_by_firm = upgrades_downgrades.drop_duplicates(subset=["Firm"])
            return latest_by_firm.to_json(orient="records", date_format="iso")
    except Exception as e:
        return json.dumps({"error": str(e)})


def _get_news(ticker: str) -> str:
    """Get news."""
    company = yf.Ticker(ticker)
    try:
        if company.isin is None:
            return json.dumps({"error": f"Ticker {ticker} not found"})
    except Exception as e:
        return json.dumps({"error": str(e)})

    try:
        news = company.news
    except Exception as e:
        return json.dumps({"error": str(e)})

    news_list = []
    for news_item in company.news:
        if news_item.get("content", {}).get("contentType", "") == "STORY":
            title = news_item.get("content", {}).get("title", "")
            summary = news_item.get("content", {}).get("summary", "")
            description = news_item.get("content", {}).get("description", "")
            url = news_item.get("content", {}).get("canonicalUrl", {}).get("url", "")
            news_list.append(
                f"Title: {title}\nSummary: {summary}\nDescription: {description}\nURL: {url}"
            )
    if not news_list:
        return json.dumps({"message": f"No news found for {ticker}"})
    return json.dumps({"news": news_list}, indent=2)
