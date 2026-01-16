import argparse
import json
import math
import os
from enum import Enum
from typing import Any, Optional
from io import StringIO
import sys
from pathlib import Path

import pandas as pd
import numpy as np
import yfinance as yf
from fastmcp import FastMCP
from snaptrade_client import SnapTrade
from dotenv import load_dotenv

# Load environment variables from .env file (for local development)
env_path = Path(__file__).parent / '.env'
if env_path.exists():
    load_dotenv(env_path)


# Define an enum for the type of financial statement
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


# Initialize FastMCP server
yfinance_server = FastMCP(
    "superfinance",
    instructions="""
# SuperFinance MCP Server

This server is used to get information about a given ticker symbol from yahoo finance.

Available tools:
- get_historical_stock_prices: Get historical stock prices for a given ticker symbol from yahoo finance. Include the following information: Date, Open, High, Low, Close, Volume, Adj Close.
- get_stock_info: Get stock information for a given ticker symbol from yahoo finance. Include the following information: Stock Price & Trading Info, Company Information, Financial Metrics, Earnings & Revenue, Margins & Returns, Dividends, Balance Sheet, Ownership, Analyst Coverage, Risk Metrics, Other.
- get_yahoo_finance_news: Get news for a given ticker symbol from yahoo finance.
- get_stock_actions: Get stock dividends and stock splits for a given ticker symbol from yahoo finance.
- get_financial_statement: Get financial statement for a given ticker symbol from yahoo finance. You can choose from the following financial statement types: income_stmt, quarterly_income_stmt, balance_sheet, quarterly_balance_sheet, cashflow, quarterly_cashflow.
- get_holder_info: Get holder information for a given ticker symbol from yahoo finance. You can choose from the following holder types: major_holders, institutional_holders, mutualfund_holders, insider_transactions, insider_purchases, insider_roster_holders.
- get_option_expiration_dates: Fetch the available options expiration dates for a given ticker symbol.
- get_option_chain: Fetch the option chain for a given ticker symbol, expiration date, and option type.
- get_recommendations: Get recommendations or upgrades/downgrades for a given ticker symbol from yahoo finance. You can also specify the number of months back to get upgrades/downgrades for, default is 12.
""",
)

# Initialize SnapTrade client for brokerage integration
# Credentials should be set as environment variables:
# - SNAPTRADE_CONSUMER_KEY
# - SNAPTRADE_CLIENT_ID
# - SNAPTRADE_USER_ID (optional, for single-user setup)
# - SNAPTRADE_USER_SECRET (optional, for single-user setup)
snaptrade_client = None
try:
    consumer_key = os.getenv("SNAPTRADE_CONSUMER_KEY")
    client_id = os.getenv("SNAPTRADE_CLIENT_ID")

    if consumer_key and client_id:
        snaptrade_client = SnapTrade(
            consumer_key=consumer_key,
            client_id=client_id
        )
except Exception as e:
    print(f"Warning: SnapTrade client initialization failed: {e}")


@yfinance_server.tool(
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
    """Get historical stock prices for a given ticker symbol

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
    """
    company = yf.Ticker(ticker)
    try:
        if company.isin is None:
            print(f"Company ticker {ticker} not found.")
            return f"Company ticker {ticker} not found."
    except Exception as e:
        print(f"Error: getting historical stock prices for {ticker}: {e}")
        return f"Error: getting historical stock prices for {ticker}: {e}"

    # If the company is found, get the historical data
    hist_data = company.history(period=period, interval=interval)
    hist_data = hist_data.reset_index(names="Date")
    hist_data = hist_data.to_json(orient="records", date_format="iso")
    return hist_data


@yfinance_server.tool(
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
            print(f"Company ticker {ticker} not found.")
            return f"Company ticker {ticker} not found."
    except Exception as e:
        print(f"Error: getting stock information for {ticker}: {e}")
        return f"Error: getting stock information for {ticker}: {e}"
    info = company.info
    return json.dumps(info)


@yfinance_server.tool(
    name="get_yahoo_finance_news",
    description="""Get news for a given ticker symbol from yahoo finance.

Args:
    ticker: str
        The ticker symbol of the stock to get news for, e.g. "AAPL"
""",
)
async def get_yahoo_finance_news(ticker: str) -> str:
    """Get news for a given ticker symbol

    Args:
        ticker: str
            The ticker symbol of the stock to get news for, e.g. "AAPL"
    """
    company = yf.Ticker(ticker)
    try:
        if company.isin is None:
            print(f"Company ticker {ticker} not found.")
            return f"Company ticker {ticker} not found."
    except Exception as e:
        print(f"Error: getting news for {ticker}: {e}")
        return f"Error: getting news for {ticker}: {e}"

    # If the company is found, get the news
    try:
        news = company.news
    except Exception as e:
        print(f"Error: getting news for {ticker}: {e}")
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
        print(f"No news found for company that searched with {ticker} ticker.")
        return f"No news found for company that searched with {ticker} ticker."
    return "\n\n".join(news_list)


@yfinance_server.tool(
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
        print(f"Error: getting stock actions for {ticker}: {e}")
        return f"Error: getting stock actions for {ticker}: {e}"
    actions_df = company.actions
    actions_df = actions_df.reset_index(names="Date")
    return actions_df.to_json(orient="records", date_format="iso")


@yfinance_server.tool(
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
            print(f"Company ticker {ticker} not found.")
            return f"Company ticker {ticker} not found."
    except Exception as e:
        print(f"Error: getting financial statement for {ticker}: {e}")
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

    # Create a list to store all the json objects
    result = []

    # Loop through each column (date)
    for column in financial_statement.columns:
        if isinstance(column, pd.Timestamp):
            date_str = column.strftime("%Y-%m-%d")  # Format as YYYY-MM-DD
        else:
            date_str = str(column)

        # Create a dictionary for each date
        date_obj = {"date": date_str}

        # Add each metric as a key-value pair
        for index, value in financial_statement[column].items():
            # Add the value, handling NaN values
            date_obj[index] = None if pd.isna(value) else value

        result.append(date_obj)

    return json.dumps(result)


@yfinance_server.tool(
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
            print(f"Company ticker {ticker} not found.")
            return f"Company ticker {ticker} not found."
    except Exception as e:
        print(f"Error: getting holder info for {ticker}: {e}")
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


@yfinance_server.tool(
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
            print(f"Company ticker {ticker} not found.")
            return f"Company ticker {ticker} not found."
    except Exception as e:
        print(f"Error: getting option expiration dates for {ticker}: {e}")
        return f"Error: getting option expiration dates for {ticker}: {e}"
    return json.dumps(company.options)


@yfinance_server.tool(
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
    """Fetch the option chain for a given ticker symbol, expiration date, and option type.

    Args:
        ticker: The ticker symbol of the stock
        expiration_date: The expiration date for the options chain (format: 'YYYY-MM-DD')
        option_type: The type of option to fetch ('calls' or 'puts')

    Returns:
        str: JSON string containing the option chain data
    """

    company = yf.Ticker(ticker)
    try:
        if company.isin is None:
            print(f"Company ticker {ticker} not found.")
            return f"Company ticker {ticker} not found."
    except Exception as e:
        print(f"Error: getting option chain for {ticker}: {e}")
        return f"Error: getting option chain for {ticker}: {e}"

    # Check if the expiration date is valid
    if expiration_date not in company.options:
        return f"Error: No options available for the date {expiration_date}. You can use `get_option_expiration_dates` to get the available expiration dates."

    # Check if the option type is valid
    if option_type not in ["calls", "puts"]:
        return "Error: Invalid option type. Please use 'calls' or 'puts'."

    # Get the option chain
    option_chain = company.option_chain(expiration_date)
    if option_type == "calls":
        return option_chain.calls.to_json(orient="records", date_format="iso")
    elif option_type == "puts":
        return option_chain.puts.to_json(orient="records", date_format="iso")
    else:
        return f"Error: invalid option type {option_type}. Please use one of the following: calls, puts."


@yfinance_server.tool(
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
            print(f"Company ticker {ticker} not found.")
            return f"Company ticker {ticker} not found."
    except Exception as e:
        print(f"Error: getting recommendations for {ticker}: {e}")
        return f"Error: getting recommendations for {ticker}: {e}"
    try:
        if recommendation_type == RecommendationType.recommendations:
            return company.recommendations.to_json(orient="records")
        elif recommendation_type == RecommendationType.upgrades_downgrades:
            # Get the upgrades/downgrades based on the cutoff date
            upgrades_downgrades = company.upgrades_downgrades.reset_index()
            cutoff_date = pd.Timestamp.now() - pd.DateOffset(months=months_back)
            upgrades_downgrades = upgrades_downgrades[
                upgrades_downgrades["GradeDate"] >= cutoff_date
            ]
            upgrades_downgrades = upgrades_downgrades.sort_values("GradeDate", ascending=False)
            # Get the first occurrence (most recent) for each firm
            latest_by_firm = upgrades_downgrades.drop_duplicates(subset=["Firm"])
            return latest_by_firm.to_json(orient="records", date_format="iso")
    except Exception as e:
        print(f"Error: getting recommendations for {ticker}: {e}")
        return f"Error: getting recommendations for {ticker}: {e}"


@yfinance_server.tool()
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
    
    Example:
        expression = '''
        stock_price = 186.23
        strike_prices = [180, 185, 190, 195]
        intrinsic_values = [max(0, stock_price - strike) for strike in strike_prices]
        print(f"Intrinsic values: {intrinsic_values}")
        intrinsic_values
        '''
    """
    try:
        # Create a safe execution environment with common libraries
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
        
        # Capture stdout to get print statements
        old_stdout = sys.stdout
        sys.stdout = StringIO()
        
        # Create a local namespace for execution
        local_vars = {}
        
        # Execute the code
        exec(expression, safe_globals, local_vars)
        
        # Get the printed output
        output = sys.stdout.getvalue()
        sys.stdout = old_stdout
        
        # Get the last expression's value if any
        # Look for the last line that isn't an assignment or import
        lines = expression.strip().split('\n')
        last_line = lines[-1].strip() if lines else ''
        
        result_parts = []
        if output:
            result_parts.append(f"Output:\n{output}")
        
        # If the last line is an expression (not assignment), it will be in local_vars
        # Try to get a result value
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


@yfinance_server.tool()
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
        # Yahoo Finance uses format like "GBPUSD=X"
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


# ============================================================================
# SnapTrade Tools - Brokerage Account Integration
# ============================================================================

@yfinance_server.tool()
def snaptrade_register_user(user_id: Optional[str] = None) -> str:
    """
    Register a new SnapTrade user to connect brokerage accounts.

    This is a one-time setup step. Returns a user_secret that must be stored securely
    and used for all subsequent SnapTrade operations.

    Args:
        user_id: Unique identifier for the user. If not provided, uses SNAPTRADE_USER_ID
                 from environment variables.

    Returns:
        JSON string containing user_id and user_secret (IMPORTANT: Save this!)

    Note: If SnapTrade is not configured (missing API credentials), returns an error message.
    """
    if not snaptrade_client:
        return json.dumps({
            "error": "SnapTrade not configured",
            "message": "Set SNAPTRADE_CONSUMER_KEY and SNAPTRADE_CLIENT_ID environment variables"
        })

    try:
        # Use provided user_id or fall back to environment variable
        if not user_id:
            user_id = os.getenv("SNAPTRADE_USER_ID")
            if not user_id:
                return json.dumps({
                    "error": "user_id required",
                    "message": "Provide user_id parameter or set SNAPTRADE_USER_ID environment variable"
                })

        response = snaptrade_client.authentication.register_snap_trade_user(
            user_id=user_id
        )

        # Handle SDK response object
        data = response.body if hasattr(response, 'body') else response
        if hasattr(data, 'to_dict'):
            data = data.to_dict()

        return json.dumps({
            "success": True,
            "user_id": user_id,
            "user_secret": data.get("userSecret") if isinstance(data, dict) else getattr(data, 'user_secret', None),
            "message": "User registered successfully. IMPORTANT: Save the user_secret!"
        }, indent=2)

    except Exception as e:
        return json.dumps({
            "error": str(e),
            "message": "Failed to register user"
        }, indent=2)


@yfinance_server.tool()
def snaptrade_get_connection_url(
    user_id: Optional[str] = None,
    user_secret: Optional[str] = None
) -> str:
    """
    Get URL for user to connect their brokerage account.

    Returns a redirect URL that the user must visit in their browser to authenticate
    with their brokerage and grant SnapTrade access.

    Args:
        user_id: SnapTrade user ID. If not provided, uses SNAPTRADE_USER_ID env var.
        user_secret: SnapTrade user secret. If not provided, uses SNAPTRADE_USER_SECRET env var.

    Returns:
        JSON string containing the connection URL
    """
    if not snaptrade_client:
        return json.dumps({
            "error": "SnapTrade not configured",
            "message": "Set SNAPTRADE_CONSUMER_KEY and SNAPTRADE_CLIENT_ID environment variables"
        })

    try:
        # Use provided credentials or fall back to environment variables
        user_id = user_id or os.getenv("SNAPTRADE_USER_ID")
        user_secret = user_secret or os.getenv("SNAPTRADE_USER_SECRET")

        if not user_id or not user_secret:
            return json.dumps({
                "error": "Credentials required",
                "message": "Provide user_id and user_secret, or set SNAPTRADE_USER_ID and SNAPTRADE_USER_SECRET"
            })

        response = snaptrade_client.authentication.login_snap_trade_user(
            user_id=user_id,
            user_secret=user_secret
        )

        # Handle SDK response object
        data = response.body if hasattr(response, 'body') else response
        if hasattr(data, 'to_dict'):
            data = data.to_dict()

        redirect_uri = data.get("redirectURI") if isinstance(data, dict) else getattr(data, 'redirect_uri', None)

        return json.dumps({
            "success": True,
            "connection_url": redirect_uri,
            "message": "Open this URL in your browser to connect your brokerage account"
        }, indent=2)

    except Exception as e:
        return json.dumps({
            "error": str(e),
            "message": "Failed to get connection URL"
        }, indent=2)


@yfinance_server.tool()
def snaptrade_list_accounts(
    user_id: Optional[str] = None,
    user_secret: Optional[str] = None
) -> str:
    """
    List all connected brokerage accounts for a SnapTrade user.

    Returns account details including IDs, names, institutions, and current balances.

    Args:
        user_id: SnapTrade user ID. If not provided, uses SNAPTRADE_USER_ID env var.
        user_secret: SnapTrade user secret. If not provided, uses SNAPTRADE_USER_SECRET env var.

    Returns:
        JSON string containing list of connected accounts
    """
    if not snaptrade_client:
        return json.dumps({
            "error": "SnapTrade not configured"
        })

    try:
        user_id = user_id or os.getenv("SNAPTRADE_USER_ID")
        user_secret = user_secret or os.getenv("SNAPTRADE_USER_SECRET")

        if not user_id or not user_secret:
            return json.dumps({
                "error": "Credentials required"
            })

        response = snaptrade_client.account_information.list_user_accounts(
            user_id=user_id,
            user_secret=user_secret
        )

        # Handle SDK response object - get the actual data
        accounts = response.body if hasattr(response, 'body') else response

        # Format the response for better readability
        formatted_accounts = []
        for account in accounts:
            # Handle both dict and object responses
            if hasattr(account, 'to_dict'):
                account = account.to_dict()
            elif hasattr(account, '__dict__'):
                account = vars(account)

            formatted_accounts.append({
                "account_id": account.get("id"),
                "brokerage_authorization": account.get("brokerage_authorization"),  # Needed for disconnect
                "name": account.get("name"),
                "number": account.get("number"),
                "institution": account.get("institution_name"),
                "balance": account.get("balance"),
                "meta": account.get("meta", {})
            })

        return json.dumps({
            "success": True,
            "count": len(formatted_accounts),
            "accounts": formatted_accounts
        }, indent=2)

    except Exception as e:
        return json.dumps({
            "error": str(e)
        }, indent=2)


@yfinance_server.tool()
def snaptrade_get_holdings(
    account_id: str,
    user_id: Optional[str] = None,
    user_secret: Optional[str] = None
) -> str:
    """
    Get holdings/positions for a specific brokerage account.

    Returns detailed information about all positions including stocks, ETFs, options,
    and cryptocurrencies held in the account.

    Args:
        account_id: The SnapTrade account ID (UUID from snaptrade_list_accounts)
        user_id: SnapTrade user ID. If not provided, uses SNAPTRADE_USER_ID env var.
        user_secret: SnapTrade user secret. If not provided, uses SNAPTRADE_USER_SECRET env var.

    Returns:
        JSON string containing account holdings with positions and balances
    """
    if not snaptrade_client:
        return json.dumps({
            "error": "SnapTrade not configured"
        })

    try:
        user_id = user_id or os.getenv("SNAPTRADE_USER_ID")
        user_secret = user_secret or os.getenv("SNAPTRADE_USER_SECRET")

        if not user_id or not user_secret:
            return json.dumps({
                "error": "Credentials required"
            })

        response = snaptrade_client.account_information.get_user_holdings(
            account_id=account_id,
            user_id=user_id,
            user_secret=user_secret
        )

        # Handle SDK response object
        holdings = response.body if hasattr(response, 'body') else response
        if hasattr(holdings, 'to_dict'):
            holdings = holdings.to_dict()

        # Helper to safely get nested dict values
        def safe_get(obj, key, default=None):
            if isinstance(obj, dict):
                return obj.get(key, default)
            return getattr(obj, key, default)

        account_data = safe_get(holdings, "account", {})
        if hasattr(account_data, 'to_dict'):
            account_data = account_data.to_dict()

        # Format the response for better readability
        result = {
            "success": True,
            "account": {
                "id": safe_get(account_data, "id"),
                "name": safe_get(account_data, "name"),
                "number": safe_get(account_data, "number"),
                "institution": safe_get(account_data, "institution_name")
            },
            "balances": safe_get(holdings, "balances", []),
            "positions": []
        }

        # Format positions
        positions = safe_get(holdings, "positions", [])
        for position in positions:
            if hasattr(position, 'to_dict'):
                position = position.to_dict()
            symbol = safe_get(position, "symbol", {})
            if hasattr(symbol, 'to_dict'):
                symbol = symbol.to_dict()
            currency = safe_get(symbol, "currency", {})
            if hasattr(currency, 'to_dict'):
                currency = currency.to_dict()

            result["positions"].append({
                "symbol": safe_get(symbol, "symbol"),
                "description": safe_get(symbol, "description"),
                "units": safe_get(position, "units"),
                "price": safe_get(position, "price"),
                "open_pnl": safe_get(position, "open_pnl"),
                "fractional_units": safe_get(position, "fractional_units"),
                "currency": safe_get(currency, "code") if currency else None
            })

        result["total_value"] = safe_get(holdings, "total_value")

        return json.dumps(result, indent=2)

    except Exception as e:
        return json.dumps({
            "error": str(e)
        }, indent=2)


def _get_live_price(symbol: str) -> dict:
    """
    Helper to fetch live price from Yahoo Finance for a symbol.
    Returns dict with price info or error.
    """
    try:
        ticker = yf.Ticker(symbol)
        info = ticker.info
        price = info.get("regularMarketPrice")
        if price is not None:
            return {
                "price": price,
                "source": "yahoo_finance",
                "currency": info.get("currency"),
                "name": info.get("shortName") or info.get("longName")
            }
        return {"price": None, "source": "unavailable", "error": f"No price for {symbol}"}
    except Exception as e:
        return {"price": None, "source": "error", "error": str(e)}


def _get_fx_rate_cached(from_currency: str, to_currency: str, cache: dict) -> Optional[float]:
    """
    Helper to get FX rate with caching to avoid repeated API calls.
    """
    if from_currency == to_currency:
        return 1.0

    cache_key = f"{from_currency}_{to_currency}"
    if cache_key in cache:
        return cache[cache_key]

    try:
        ticker_symbol = f"{from_currency.upper()}{to_currency.upper()}=X"
        ticker = yf.Ticker(ticker_symbol)
        rate = ticker.info.get("regularMarketPrice")
        if rate:
            cache[cache_key] = rate
            return rate
    except:
        pass

    return None


@yfinance_server.tool()
def snaptrade_list_all_holdings(
    user_id: Optional[str] = None,
    user_secret: Optional[str] = None,
    target_currency: Optional[str] = None
) -> str:
    """
    Get holdings for ALL connected brokerage accounts with live prices from Yahoo Finance.

    This tool fetches holdings from all connected brokerages and enriches them with:
    - Live prices from Yahoo Finance (more current than brokerage data)
    - Currency conversion to a target currency (optional)
    - Calculated market values and P&L

    Args:
        user_id: SnapTrade user ID. If not provided, uses SNAPTRADE_USER_ID env var.
        user_secret: SnapTrade user secret. If not provided, uses SNAPTRADE_USER_SECRET env var.
        target_currency: Optional currency code (e.g., "GBP", "EUR") to convert all values to.
                        If not provided, values are shown in their original currencies.

    Returns:
        JSON string containing all accounts with enriched holdings including live prices
    """
    if not snaptrade_client:
        return json.dumps({
            "error": "SnapTrade not configured"
        })

    try:
        user_id = user_id or os.getenv("SNAPTRADE_USER_ID")
        user_secret = user_secret or os.getenv("SNAPTRADE_USER_SECRET")

        if not user_id or not user_secret:
            return json.dumps({
                "error": "Credentials required"
            })

        # Step 1: Get all accounts
        accounts_response = snaptrade_client.account_information.list_user_accounts(
            user_id=user_id,
            user_secret=user_secret
        )
        accounts = accounts_response.body if hasattr(accounts_response, 'body') else accounts_response

        # FX rate cache to avoid repeated lookups
        fx_cache = {}
        fx_rates_used = {}

        # Step 2: Get holdings for each account
        all_holdings = []
        total_value_by_currency = {}
        total_value_converted = 0.0 if target_currency else None

        for account in accounts:
            if hasattr(account, 'to_dict'):
                account = account.to_dict()

            account_id = account.get("id")

            try:
                holdings_response = snaptrade_client.account_information.get_user_holdings(
                    account_id=account_id,
                    user_id=user_id,
                    user_secret=user_secret
                )
                holdings = holdings_response.body if hasattr(holdings_response, 'body') else holdings_response
                if hasattr(holdings, 'to_dict'):
                    holdings = holdings.to_dict()

                # Extract balance info
                balance = account.get("balance", {})
                if isinstance(balance, dict) and "total" in balance:
                    total = balance["total"]
                    currency = total.get("currency", "USD")
                    amount = total.get("amount", 0)
                    total_value_by_currency[currency] = total_value_by_currency.get(currency, 0) + amount

                # Format positions with live prices
                positions = []
                account_value_converted = 0.0

                for position in holdings.get("positions", []):
                    if hasattr(position, 'to_dict'):
                        position = position.to_dict()
                    symbol_data = position.get("symbol", {})
                    if hasattr(symbol_data, 'to_dict'):
                        symbol_data = symbol_data.to_dict()

                    # Handle nested symbol structure
                    if "symbol" in symbol_data and isinstance(symbol_data["symbol"], dict):
                        inner_symbol = symbol_data["symbol"]
                        symbol_ticker = inner_symbol.get("symbol")
                        description = inner_symbol.get("description")
                        pos_currency = inner_symbol.get("currency", {}).get("code") if isinstance(inner_symbol.get("currency"), dict) else None
                    else:
                        symbol_ticker = symbol_data.get("symbol")
                        description = symbol_data.get("description")
                        pos_currency = symbol_data.get("currency", {}).get("code") if isinstance(symbol_data.get("currency"), dict) else None

                    units = position.get("units") or 0
                    snaptrade_price = position.get("price")
                    average_cost = position.get("average_purchase_price")

                    # Fetch live price from Yahoo Finance
                    live_data = _get_live_price(symbol_ticker) if symbol_ticker else {"price": None, "source": "no_symbol"}
                    live_price = live_data.get("price")
                    price_source = live_data.get("source", "unknown")

                    # Use live price if available, fallback to SnapTrade price
                    current_price = live_price if live_price is not None else snaptrade_price

                    # Calculate market value
                    market_value = (units * current_price) if current_price and units else None

                    # Calculate cost basis
                    cost_basis = (units * average_cost) if average_cost and units else None

                    # Calculate P&L
                    unrealized_pnl = None
                    unrealized_pnl_pct = None
                    if market_value is not None and cost_basis is not None and cost_basis > 0:
                        unrealized_pnl = market_value - cost_basis
                        unrealized_pnl_pct = round((unrealized_pnl / cost_basis) * 100, 2)

                    # Build position data
                    pos_data = {
                        "symbol": symbol_ticker,
                        "description": description,
                        "units": units,
                        "currency": pos_currency,
                        "live_price": live_price,
                        "snaptrade_price": snaptrade_price,
                        "price_source": price_source,
                        "market_value": round(market_value, 2) if market_value else None,
                        "average_cost": average_cost,
                        "cost_basis": round(cost_basis, 2) if cost_basis else None,
                        "unrealized_pnl": round(unrealized_pnl, 2) if unrealized_pnl else None,
                        "unrealized_pnl_pct": unrealized_pnl_pct
                    }

                    # Currency conversion if target_currency specified
                    if target_currency and pos_currency and pos_currency != target_currency:
                        fx_rate = _get_fx_rate_cached(pos_currency, target_currency, fx_cache)
                        if fx_rate:
                            fx_key = f"{pos_currency}_{target_currency}"
                            fx_rates_used[fx_key] = fx_rate

                            pos_data["converted"] = {
                                "currency": target_currency,
                                "fx_rate": fx_rate,
                                "live_price": round(live_price * fx_rate, 2) if live_price else None,
                                "market_value": round(market_value * fx_rate, 2) if market_value else None,
                                "cost_basis": round(cost_basis * fx_rate, 2) if cost_basis else None,
                                "unrealized_pnl": round(unrealized_pnl * fx_rate, 2) if unrealized_pnl else None
                            }
                            if market_value:
                                account_value_converted += market_value * fx_rate
                    elif target_currency and pos_currency == target_currency:
                        if market_value:
                            account_value_converted += market_value

                    positions.append(pos_data)

                # Process option positions
                option_positions = []
                for opt_pos in holdings.get("option_positions", []):
                    if hasattr(opt_pos, 'to_dict'):
                        opt_pos = opt_pos.to_dict()

                    # Extract option symbol info
                    opt_symbol = opt_pos.get("option_symbol", {})
                    if hasattr(opt_symbol, 'to_dict'):
                        opt_symbol = opt_symbol.to_dict()

                    underlying = opt_symbol.get("underlying_symbol", {})
                    if hasattr(underlying, 'to_dict'):
                        underlying = underlying.to_dict()

                    opt_currency = underlying.get("currency", {})
                    if hasattr(opt_currency, 'to_dict'):
                        opt_currency = opt_currency.to_dict()

                    units = opt_pos.get("units") or 0
                    snaptrade_price = opt_pos.get("price")
                    average_cost = opt_pos.get("average_purchase_price")

                    # Options are typically 100 shares per contract
                    multiplier = 100 if not opt_symbol.get("is_mini_option") else 10
                    market_value = (units * snaptrade_price * multiplier) if snaptrade_price and units else None
                    cost_basis = (units * average_cost * multiplier) if average_cost and units else None

                    unrealized_pnl = None
                    unrealized_pnl_pct = None
                    if market_value is not None and cost_basis is not None and cost_basis != 0:
                        unrealized_pnl = market_value - cost_basis
                        unrealized_pnl_pct = round((unrealized_pnl / abs(cost_basis)) * 100, 2)

                    opt_data = {
                        "type": "option",
                        "ticker": opt_symbol.get("ticker"),
                        "underlying": underlying.get("symbol"),
                        "option_type": opt_symbol.get("option_type"),  # CALL or PUT
                        "strike_price": opt_symbol.get("strike_price"),
                        "expiration_date": opt_symbol.get("expiration_date"),
                        "units": units,  # Number of contracts
                        "multiplier": multiplier,
                        "currency": opt_currency.get("code") if isinstance(opt_currency, dict) else None,
                        "price_per_share": snaptrade_price,
                        "market_value": round(market_value, 2) if market_value else None,
                        "average_cost": average_cost,
                        "cost_basis": round(cost_basis, 2) if cost_basis else None,
                        "unrealized_pnl": round(unrealized_pnl, 2) if unrealized_pnl else None,
                        "unrealized_pnl_pct": unrealized_pnl_pct
                    }

                    # Currency conversion for options
                    opt_curr = opt_data.get("currency")
                    if target_currency and opt_curr and opt_curr != target_currency:
                        fx_rate = _get_fx_rate_cached(opt_curr, target_currency, fx_cache)
                        if fx_rate:
                            fx_key = f"{opt_curr}_{target_currency}"
                            fx_rates_used[fx_key] = fx_rate

                            opt_data["converted"] = {
                                "currency": target_currency,
                                "fx_rate": fx_rate,
                                "market_value": round(market_value * fx_rate, 2) if market_value else None,
                                "cost_basis": round(cost_basis * fx_rate, 2) if cost_basis else None,
                                "unrealized_pnl": round(unrealized_pnl * fx_rate, 2) if unrealized_pnl else None
                            }
                            if market_value:
                                account_value_converted += market_value * fx_rate
                    elif target_currency and opt_curr == target_currency:
                        if market_value:
                            account_value_converted += market_value

                    option_positions.append(opt_data)

                if target_currency and total_value_converted is not None:
                    total_value_converted += account_value_converted

                all_holdings.append({
                    "account_id": account_id,
                    "name": account.get("name"),
                    "institution": account.get("institution_name"),
                    "balance": balance,
                    "positions_count": len(positions),
                    "positions": positions,
                    "option_positions_count": len(option_positions),
                    "option_positions": option_positions
                })

            except Exception as e:
                all_holdings.append({
                    "account_id": account_id,
                    "name": account.get("name"),
                    "institution": account.get("institution_name"),
                    "error": str(e)
                })

        result = {
            "success": True,
            "accounts_count": len(all_holdings),
            "total_value_by_currency": total_value_by_currency,
            "accounts": all_holdings
        }

        if target_currency:
            result["target_currency"] = target_currency
            result["fx_rates_used"] = fx_rates_used
            result["total_value_converted"] = {
                target_currency: round(total_value_converted, 2)
            } if total_value_converted else None

        return json.dumps(result, indent=2)

    except Exception as e:
        return json.dumps({
            "error": str(e)
        }, indent=2)


@yfinance_server.tool()
def snaptrade_get_transactions(
    account_id: str,
    start_date: str,
    end_date: str,
    user_id: Optional[str] = None,
    user_secret: Optional[str] = None,
    transaction_type: Optional[str] = None
) -> str:
    """
    Get transaction history for a brokerage account.

    Returns historical transactions including buys, sells, dividends, deposits, and withdrawals.
    Data is refreshed once daily. Results are paginated with max 1000 per request.

    Args:
        account_id: The SnapTrade account ID (UUID from snaptrade_list_accounts)
        start_date: Start date in YYYY-MM-DD format (e.g., "2024-01-01")
        end_date: End date in YYYY-MM-DD format (e.g., "2024-12-31")
        user_id: SnapTrade user ID. If not provided, uses SNAPTRADE_USER_ID env var.
        user_secret: SnapTrade user secret. If not provided, uses SNAPTRADE_USER_SECRET env var.
        transaction_type: Optional filter by type (e.g., "BUY,SELL,DIVIDEND")

    Returns:
        JSON string containing transaction history
    """
    if not snaptrade_client:
        return json.dumps({
            "error": "SnapTrade not configured"
        })

    try:
        user_id = user_id or os.getenv("SNAPTRADE_USER_ID")
        user_secret = user_secret or os.getenv("SNAPTRADE_USER_SECRET")

        if not user_id or not user_secret:
            return json.dumps({
                "error": "Credentials required"
            })

        # Build request parameters
        params = {
            "account_id": account_id,
            "user_id": user_id,
            "user_secret": user_secret,
            "start_date": start_date,
            "end_date": end_date
        }

        if transaction_type:
            params["type"] = transaction_type

        response = snaptrade_client.account_information.get_account_activities(**params)

        # Handle SDK response object
        activities = response.body if hasattr(response, 'body') else response

        # Helper to safely get values
        def safe_get(obj, key, default=None):
            if isinstance(obj, dict):
                return obj.get(key, default)
            return getattr(obj, key, default)

        # Format the response
        formatted_activities = []
        for activity in activities:
            if hasattr(activity, 'to_dict'):
                activity = activity.to_dict()

            formatted_activities.append({
                "id": safe_get(activity, "id"),
                "type": safe_get(activity, "type"),
                "symbol": safe_get(activity, "symbol"),
                "description": safe_get(activity, "description"),
                "trade_date": safe_get(activity, "trade_date"),
                "settlement_date": safe_get(activity, "settlement_date"),
                "units": safe_get(activity, "units"),
                "price": safe_get(activity, "price"),
                "amount": safe_get(activity, "amount"),
                "currency": safe_get(activity, "currency"),
                "fee": safe_get(activity, "fee"),
                "institution": safe_get(activity, "institution")
            })

        return json.dumps({
            "success": True,
            "count": len(formatted_activities),
            "transactions": formatted_activities,
            "note": "Data refreshed once daily. Max 1000 transactions per request."
        }, indent=2)

    except Exception as e:
        return json.dumps({
            "error": str(e)
        }, indent=2)


@yfinance_server.tool()
def snaptrade_disconnect_account(
    authorization_id: str,
    user_id: Optional[str] = None,
    user_secret: Optional[str] = None
) -> str:
    """
    Disconnect/remove a brokerage connection from SnapTrade.

    WARNING: This is irreversible! It will remove the brokerage connection and ALL
    associated accounts and holdings data from SnapTrade.

    Args:
        authorization_id: The brokerage authorization ID (get from snaptrade_list_accounts,
                         it's the 'brokerage_authorization' field in each account)
        user_id: SnapTrade user ID. If not provided, uses SNAPTRADE_USER_ID env var.
        user_secret: SnapTrade user secret. If not provided, uses SNAPTRADE_USER_SECRET env var.

    Returns:
        JSON string confirming disconnection or error message
    """
    if not snaptrade_client:
        return json.dumps({
            "error": "SnapTrade not configured"
        })

    try:
        user_id = user_id or os.getenv("SNAPTRADE_USER_ID")
        user_secret = user_secret or os.getenv("SNAPTRADE_USER_SECRET")

        if not user_id or not user_secret:
            return json.dumps({
                "error": "Credentials required"
            })

        snaptrade_client.connections.remove_brokerage_authorization(
            authorization_id=authorization_id,
            user_id=user_id,
            user_secret=user_secret
        )

        return json.dumps({
            "success": True,
            "message": f"Brokerage connection {authorization_id} has been disconnected and all associated data removed."
        }, indent=2)

    except Exception as e:
        return json.dumps({
            "error": str(e)
        }, indent=2)


@yfinance_server.tool()
def snaptrade_refresh_account(
    authorization_id: str,
    user_id: Optional[str] = None,
    user_secret: Optional[str] = None
) -> str:
    """
    Trigger a manual refresh of holdings data for a brokerage connection.

    SnapTrade syncs holdings once daily by default. Use this to force an immediate
    refresh of all accounts under a brokerage connection. The refresh is queued
    asynchronously - data may take a few moments to update.

    Args:
        authorization_id: The brokerage authorization ID (get from snaptrade_list_accounts,
                         it's the 'brokerage_authorization' field in each account)
        user_id: SnapTrade user ID. If not provided, uses SNAPTRADE_USER_ID env var.
        user_secret: SnapTrade user secret. If not provided, uses SNAPTRADE_USER_SECRET env var.

    Returns:
        JSON string confirming refresh has been scheduled

    Note: Each refresh call may incur additional charges depending on your SnapTrade plan.
    """
    if not snaptrade_client:
        return json.dumps({
            "error": "SnapTrade not configured"
        })

    try:
        user_id = user_id or os.getenv("SNAPTRADE_USER_ID")
        user_secret = user_secret or os.getenv("SNAPTRADE_USER_SECRET")

        if not user_id or not user_secret:
            return json.dumps({
                "error": "Credentials required"
            })

        response = snaptrade_client.connections.refresh_brokerage_authorization(
            authorization_id=authorization_id,
            user_id=user_id,
            user_secret=user_secret
        )

        # Handle SDK response object
        data = response.body if hasattr(response, 'body') else response
        if hasattr(data, 'to_dict'):
            data = data.to_dict()

        return json.dumps({
            "success": True,
            "authorization_id": authorization_id,
            "message": "Refresh scheduled. Holdings will be updated shortly.",
            "detail": data.get("detail") if isinstance(data, dict) else str(data)
        }, indent=2)

    except Exception as e:
        return json.dumps({
            "error": str(e)
        }, indent=2)


if __name__ == "__main__":
    # For local testing, use stdio
    # For remote deployment, use HTTP transport
    import os
    
    # Check if we're running in Fly.io or remote environment
    if os.getenv("FLY_APP_NAME") or os.getenv("PORT"):
        # Remote deployment - use HTTP
        port = int(os.getenv("PORT", "8080"))
        print(f"Starting SuperFinance MCP server on HTTP at 0.0.0.0:{port}")
        
        # Create the MCP app
        app = yfinance_server.http_app()
        
        # Add a simple health check endpoint for Fly.io
        from starlette.responses import JSONResponse
        from starlette.routing import Route
        
        async def health_check(request):
            return JSONResponse({"status": "ok", "service": "superfinance-mcp"})
        
        # Add health check route
        app.routes.insert(0, Route("/", health_check))
        app.routes.insert(1, Route("/health", health_check))
        
        # Run with uvicorn
        import uvicorn
        uvicorn.run(app, host="0.0.0.0", port=port)
    else:
        # Local development - use stdio
        print("Starting SuperFinance MCP server with stdio transport")
        yfinance_server.run()
