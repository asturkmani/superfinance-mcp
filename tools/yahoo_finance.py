"""Yahoo Finance tools for fetching stock data."""

import json
import math
import sys
from io import StringIO
from enum import Enum

import pandas as pd
import numpy as np
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


def register_yahoo_finance_tools(server):
    """Register all Yahoo Finance tools with the server."""

    @server.tool(
        name="get_historical_stock_prices",
        description="""Get historical stock prices for a given ticker symbol from yahoo finance. Include the following information: Date, Open, High, Low, Close, Volume, Adj Close.
Args:
    ticker: str
        The ticker symbol of the stock to get historical prices for, e.g. "AAPL"
    period : str
        Valid periods: 1d,5d,1mo,3mo,6mo,1y,2y,5y,10y,ytd,max
        Either Use period parameter or use start and end
        Default is "1mo"
    interval : str
        Valid intervals: 1m,2m,5m,15m,30m,60m,90m,1h,1d,5d,1wk,1mo,3mo
        Intraday data cannot extend last 60 days
        Default is "1d"
""",
    )
    async def get_historical_stock_prices(
        ticker: str, period: str = "1mo", interval: str = "1d"
    ) -> str:
        """Get historical stock prices for a given ticker symbol"""
        company = yf.Ticker(ticker)
        try:
            if company.isin is None:
                return f"Company ticker {ticker} not found."
        except Exception as e:
            return f"Error: getting historical stock prices for {ticker}: {e}"

        hist_data = company.history(period=period, interval=interval)
        hist_data = hist_data.reset_index(names="Date")
        hist_data = hist_data.to_json(orient="records", date_format="iso")
        return hist_data

    @server.tool(
        name="get_stock_info",
        description="""Get stock information for a given ticker symbol from yahoo finance. Include the following information:
Stock Price & Trading Info, Company Information, Financial Metrics, Earnings & Revenue, Margins & Returns, Dividends, Balance Sheet, Ownership, Analyst Coverage, Risk Metrics, Other.

Args:
    ticker: str
        The ticker symbol of the stock to get information for, e.g. "AAPL"
""",
    )
    async def get_stock_info(ticker: str) -> str:
        """Get stock information for a given ticker symbol"""
        company = yf.Ticker(ticker)
        try:
            if company.isin is None:
                return f"Company ticker {ticker} not found."
        except Exception as e:
            return f"Error: getting stock information for {ticker}: {e}"
        info = company.info
        return json.dumps(info)

    @server.tool(
        name="get_yahoo_finance_news",
        description="""Get news for a given ticker symbol from yahoo finance.

Args:
    ticker: str
        The ticker symbol of the stock to get news for, e.g. "AAPL"
""",
    )
    async def get_yahoo_finance_news(ticker: str) -> str:
        """Get news for a given ticker symbol"""
        company = yf.Ticker(ticker)
        try:
            if company.isin is None:
                return f"Company ticker {ticker} not found."
        except Exception as e:
            return f"Error: getting news for {ticker}: {e}"

        try:
            news = company.news
        except Exception as e:
            return f"Error: getting news for {ticker}: {e}"

        news_list = []
        for news in company.news:
            if news.get("content", {}).get("contentType", "") == "STORY":
                title = news.get("content", {}).get("title", "")
                summary = news.get("content", {}).get("summary", "")
                description = news.get("content", {}).get("description", "")
                url = news.get("content", {}).get("canonicalUrl", {}).get("url", "")
                news_list.append(
                    f"Title: {title}\nSummary: {summary}\nDescription: {description}\nURL: {url}"
                )
        if not news_list:
            return f"No news found for company that searched with {ticker} ticker."
        return "\n\n".join(news_list)

    @server.tool(
        name="get_stock_actions",
        description="""Get stock dividends and stock splits for a given ticker symbol from yahoo finance.

Args:
    ticker: str
        The ticker symbol of the stock to get stock actions for, e.g. "AAPL"
""",
    )
    async def get_stock_actions(ticker: str) -> str:
        """Get stock dividends and stock splits for a given ticker symbol"""
        try:
            company = yf.Ticker(ticker)
        except Exception as e:
            return f"Error: getting stock actions for {ticker}: {e}"
        actions_df = company.actions
        actions_df = actions_df.reset_index(names="Date")
        return actions_df.to_json(orient="records", date_format="iso")

    @server.tool(
        name="get_financial_statement",
        description="""Get financial statement for a given ticker symbol from yahoo finance. You can choose from the following financial statement types: income_stmt, quarterly_income_stmt, balance_sheet, quarterly_balance_sheet, cashflow, quarterly_cashflow.

Args:
    ticker: str
        The ticker symbol of the stock to get financial statement for, e.g. "AAPL"
    financial_type: str
        The type of financial statement to get. You can choose from the following financial statement types: income_stmt, quarterly_income_stmt, balance_sheet, quarterly_balance_sheet, cashflow, quarterly_cashflow.
""",
    )
    async def get_financial_statement(ticker: str, financial_type: str) -> str:
        """Get financial statement for a given ticker symbol"""
        company = yf.Ticker(ticker)
        try:
            if company.isin is None:
                return f"Company ticker {ticker} not found."
        except Exception as e:
            return f"Error: getting financial statement for {ticker}: {e}"

        if financial_type == FinancialType.income_stmt:
            financial_statement = company.income_stmt
        elif financial_type == FinancialType.quarterly_income_stmt:
            financial_statement = company.quarterly_income_stmt
        elif financial_type == FinancialType.balance_sheet:
            financial_statement = company.balance_sheet
        elif financial_type == FinancialType.quarterly_balance_sheet:
            financial_statement = company.quarterly_balance_sheet
        elif financial_type == FinancialType.cashflow:
            financial_statement = company.cashflow
        elif financial_type == FinancialType.quarterly_cashflow:
            financial_statement = company.quarterly_cashflow
        else:
            return f"Error: invalid financial type {financial_type}. Please use one of the following: {FinancialType.income_stmt}, {FinancialType.quarterly_income_stmt}, {FinancialType.balance_sheet}, {FinancialType.quarterly_balance_sheet}, {FinancialType.cashflow}, {FinancialType.quarterly_cashflow}."

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

        return json.dumps(result)

    @server.tool(
        name="get_holder_info",
        description="""Get holder information for a given ticker symbol from yahoo finance. You can choose from the following holder types: major_holders, institutional_holders, mutualfund_holders, insider_transactions, insider_purchases, insider_roster_holders.

Args:
    ticker: str
        The ticker symbol of the stock to get holder information for, e.g. "AAPL"
    holder_type: str
        The type of holder information to get. You can choose from the following holder types: major_holders, institutional_holders, mutualfund_holders, insider_transactions, insider_purchases, insider_roster_holders.
""",
    )
    async def get_holder_info(ticker: str, holder_type: str) -> str:
        """Get holder information for a given ticker symbol"""
        company = yf.Ticker(ticker)
        try:
            if company.isin is None:
                return f"Company ticker {ticker} not found."
        except Exception as e:
            return f"Error: getting holder info for {ticker}: {e}"

        if holder_type == HolderType.major_holders:
            return company.major_holders.reset_index(names="metric").to_json(orient="records")
        elif holder_type == HolderType.institutional_holders:
            return company.institutional_holders.to_json(orient="records")
        elif holder_type == HolderType.mutualfund_holders:
            return company.mutualfund_holders.to_json(orient="records", date_format="iso")
        elif holder_type == HolderType.insider_transactions:
            return company.insider_transactions.to_json(orient="records", date_format="iso")
        elif holder_type == HolderType.insider_purchases:
            return company.insider_purchases.to_json(orient="records", date_format="iso")
        elif holder_type == HolderType.insider_roster_holders:
            return company.insider_roster_holders.to_json(orient="records", date_format="iso")
        else:
            return f"Error: invalid holder type {holder_type}. Please use one of the following: {HolderType.major_holders}, {HolderType.institutional_holders}, {HolderType.mutualfund_holders}, {HolderType.insider_transactions}, {HolderType.insider_purchases}, {HolderType.insider_roster_holders}."

    @server.tool(
        name="get_option_expiration_dates",
        description="""Fetch the available options expiration dates for a given ticker symbol.

Args:
    ticker: str
        The ticker symbol of the stock to get option expiration dates for, e.g. "AAPL"
""",
    )
    async def get_option_expiration_dates(ticker: str) -> str:
        """Fetch the available options expiration dates for a given ticker symbol."""
        company = yf.Ticker(ticker)
        try:
            if company.isin is None:
                return f"Company ticker {ticker} not found."
        except Exception as e:
            return f"Error: getting option expiration dates for {ticker}: {e}"
        return json.dumps(company.options)

    @server.tool(
        name="get_option_chain",
        description="""Fetch the option chain for a given ticker symbol, expiration date, and option type.

Args:
    ticker: str
        The ticker symbol of the stock to get option chain for, e.g. "AAPL"
    expiration_date: str
        The expiration date for the options chain (format: 'YYYY-MM-DD')
    option_type: str
        The type of option to fetch ('calls' or 'puts')
""",
    )
    async def get_option_chain(ticker: str, expiration_date: str, option_type: str) -> str:
        """Fetch the option chain for a given ticker symbol, expiration date, and option type."""
        company = yf.Ticker(ticker)
        try:
            if company.isin is None:
                return f"Company ticker {ticker} not found."
        except Exception as e:
            return f"Error: getting option chain for {ticker}: {e}"

        if expiration_date not in company.options:
            return f"Error: No options available for the date {expiration_date}. You can use `get_option_expiration_dates` to get the available expiration dates."

        if option_type not in ["calls", "puts"]:
            return "Error: Invalid option type. Please use 'calls' or 'puts'."

        option_chain = company.option_chain(expiration_date)
        if option_type == "calls":
            return option_chain.calls.to_json(orient="records", date_format="iso")
        elif option_type == "puts":
            return option_chain.puts.to_json(orient="records", date_format="iso")
        else:
            return f"Error: invalid option type {option_type}. Please use one of the following: calls, puts."

    @server.tool(
        name="get_recommendations",
        description="""Get recommendations or upgrades/downgrades for a given ticker symbol from yahoo finance. You can also specify the number of months back to get upgrades/downgrades for, default is 12.

Args:
    ticker: str
        The ticker symbol of the stock to get recommendations for, e.g. "AAPL"
    recommendation_type: str
        The type of recommendation to get. You can choose from the following recommendation types: recommendations, upgrades_downgrades.
    months_back: int
        The number of months back to get upgrades/downgrades for, default is 12.
""",
    )
    async def get_recommendations(ticker: str, recommendation_type: str, months_back: int = 12) -> str:
        """Get recommendations or upgrades/downgrades for a given ticker symbol"""
        company = yf.Ticker(ticker)
        try:
            if company.isin is None:
                return f"Company ticker {ticker} not found."
        except Exception as e:
            return f"Error: getting recommendations for {ticker}: {e}"
        try:
            if recommendation_type == RecommendationType.recommendations:
                return company.recommendations.to_json(orient="records")
            elif recommendation_type == RecommendationType.upgrades_downgrades:
                upgrades_downgrades = company.upgrades_downgrades.reset_index()
                cutoff_date = pd.Timestamp.now() - pd.DateOffset(months=months_back)
                upgrades_downgrades = upgrades_downgrades[
                    upgrades_downgrades["GradeDate"] >= cutoff_date
                ]
                upgrades_downgrades = upgrades_downgrades.sort_values("GradeDate", ascending=False)
                latest_by_firm = upgrades_downgrades.drop_duplicates(subset=["Firm"])
                return latest_by_firm.to_json(orient="records", date_format="iso")
        except Exception as e:
            return f"Error: getting recommendations for {ticker}: {e}"

    @server.tool()
    def calculate(expression: str) -> str:
        """
        Execute Python code for calculations and data analysis.

        Useful for:
        - Mathematical calculations
        - Financial analysis with stock data
        - Data manipulation with pandas/numpy
        - Statistical computations

        Available libraries: math, numpy (as np), pandas (as pd), json

        Args:
            expression: Python code to execute. Can include multiple lines.
                       The last expression will be returned.
                       Use print() for intermediate output.

        Returns:
            String containing the result and any printed output
        """
        try:
            safe_globals = {
                '__builtins__': {
                    'abs': abs, 'round': round, 'min': min, 'max': max,
                    'sum': sum, 'len': len, 'range': range, 'enumerate': enumerate,
                    'zip': zip, 'map': map, 'filter': filter, 'sorted': sorted,
                    'list': list, 'dict': dict, 'set': set, 'tuple': tuple,
                    'str': str, 'int': int, 'float': float, 'bool': bool,
                    'print': print, 'True': True, 'False': False, 'None': None,
                },
                'math': math,
                'np': np,
                'pd': pd,
                'json': json,
            }

            old_stdout = sys.stdout
            sys.stdout = StringIO()

            local_vars = {}
            exec(expression, safe_globals, local_vars)

            output = sys.stdout.getvalue()
            sys.stdout = old_stdout

            lines = expression.strip().split('\n')
            last_line = lines[-1].strip() if lines else ''

            result_parts = []
            if output:
                result_parts.append(f"Output:\n{output}")

            if last_line and '=' not in last_line and not last_line.startswith(('import', 'from', 'def', 'class', 'if', 'for', 'while')):
                try:
                    result_value = eval(last_line, safe_globals, local_vars)
                    if result_value is not None:
                        result_parts.append(f"Result:\n{result_value}")
                except:
                    pass

            return '\n\n'.join(result_parts) if result_parts else "Code executed successfully (no output)"

        except Exception as e:
            return f"Error executing code: {type(e).__name__}: {str(e)}"

    @server.tool()
    def get_fx_rate(
        from_currency: str,
        to_currency: str
    ) -> str:
        """
        Get the current foreign exchange rate between two currencies.

        Args:
            from_currency: The source currency code (e.g., "GBP", "EUR", "USD")
            to_currency: The target currency code (e.g., "USD", "GBP", "EUR")

        Returns:
            JSON string containing the exchange rate and related information

        Examples:
            get_fx_rate("GBP", "USD") -> How many USD per 1 GBP
            get_fx_rate("EUR", "GBP") -> How many GBP per 1 EUR
        """
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
            return json.dumps({
                "error": str(e)
            }, indent=2)
