"""Stock data API routes."""

from typing import Literal, Optional

from fastapi import APIRouter, Query

from services.yahoo_finance_service import YahooFinanceService


router = APIRouter()


@router.get("/{ticker}/prices")
async def get_historical_prices(
    ticker: str,
    period: str = Query("1mo", description="Time period: 1d,5d,1mo,3mo,6mo,1y,2y,5y,10y,ytd,max"),
    interval: str = Query("1d", description="Data interval: 1m,2m,5m,15m,30m,60m,90m,1h,1d,5d,1wk,1mo,3mo")
):
    """
    Get historical OHLCV data for a stock.

    - **ticker**: Stock symbol (e.g., AAPL)
    - **period**: Time period (default: 1mo)
    - **interval**: Data interval (default: 1d)
    """
    return await YahooFinanceService.get_historical_prices(ticker, period, interval)


@router.get("/{ticker}/info")
async def get_stock_info(ticker: str):
    """
    Get comprehensive stock information.

    - **ticker**: Stock symbol or comma-separated symbols (e.g., AAPL or AAPL,MSFT,GOOG)
    """
    return await YahooFinanceService.get_stock_info(ticker)


@router.get("/{ticker}/news")
async def get_news(ticker: str):
    """
    Get latest news articles for a stock.

    - **ticker**: Stock symbol (e.g., AAPL)
    """
    return await YahooFinanceService.get_news(ticker)


@router.get("/{ticker}/actions")
async def get_stock_actions(ticker: str):
    """
    Get dividends and stock splits.

    - **ticker**: Stock symbol (e.g., AAPL)
    """
    return await YahooFinanceService.get_stock_actions(ticker)


@router.get("/{ticker}/financials/{statement_type}")
async def get_financial_statement(
    ticker: str,
    statement_type: Literal[
        "income_stmt", "quarterly_income_stmt",
        "balance_sheet", "quarterly_balance_sheet",
        "cashflow", "quarterly_cashflow"
    ]
):
    """
    Get financial statement data.

    - **ticker**: Stock symbol (e.g., AAPL)
    - **statement_type**: Type of financial statement
    """
    return await YahooFinanceService.get_financial_statement(ticker, statement_type)


@router.get("/{ticker}/holders/{holder_type}")
async def get_holder_info(
    ticker: str,
    holder_type: Literal[
        "major_holders", "institutional_holders", "mutualfund_holders",
        "insider_transactions", "insider_purchases", "insider_roster_holders"
    ]
):
    """
    Get holder/ownership information.

    - **ticker**: Stock symbol (e.g., AAPL)
    - **holder_type**: Type of holder information
    """
    return await YahooFinanceService.get_holder_info(ticker, holder_type)


@router.get("/{ticker}/options/expirations")
async def get_option_expirations(ticker: str):
    """
    Get available options expiration dates.

    - **ticker**: Stock symbol (e.g., AAPL)
    """
    return await YahooFinanceService.get_option_expirations(ticker)


@router.get("/{ticker}/options/{expiration_date}/{option_type}")
async def get_option_chain(
    ticker: str,
    expiration_date: str,
    option_type: Literal["calls", "puts"]
):
    """
    Get options chain data.

    - **ticker**: Stock symbol (e.g., AAPL)
    - **expiration_date**: Expiration date (YYYY-MM-DD)
    - **option_type**: calls or puts
    """
    return await YahooFinanceService.get_option_chain(ticker, expiration_date, option_type)


@router.get("/{ticker}/recommendations/{recommendation_type}")
async def get_recommendations(
    ticker: str,
    recommendation_type: Literal["recommendations", "upgrades_downgrades"],
    months_back: int = Query(12, description="Months of history for upgrades/downgrades")
):
    """
    Get analyst recommendations.

    - **ticker**: Stock symbol (e.g., AAPL)
    - **recommendation_type**: Type of recommendations
    - **months_back**: History period for upgrades/downgrades
    """
    return await YahooFinanceService.get_recommendations(ticker, recommendation_type, months_back)


@router.get("/fx/{from_currency}/{to_currency}")
async def get_fx_rate(from_currency: str, to_currency: str):
    """
    Get foreign exchange rate.

    - **from_currency**: Source currency (e.g., GBP)
    - **to_currency**: Target currency (e.g., USD)

    Returns: How many {to_currency} per 1 {from_currency}
    """
    return await YahooFinanceService.get_fx_rate(from_currency, to_currency)
