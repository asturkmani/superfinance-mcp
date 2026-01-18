"""Yahoo Finance service - core business logic for stock data."""

import json
from typing import Optional, Literal

import pandas as pd
import yfinance as yf


class YahooFinanceService:
    """Service class for Yahoo Finance data operations."""

    @staticmethod
    async def get_historical_prices(
        ticker: str,
        period: str = "1mo",
        interval: str = "1d"
    ) -> dict:
        """
        Get historical OHLCV data for a ticker symbol.

        Args:
            ticker: Stock ticker symbol (e.g., "AAPL")
            period: Time period (1d, 5d, 1mo, 3mo, 6mo, 1y, 2y, 5y, 10y, ytd, max)
            interval: Data interval (1m, 2m, 5m, 15m, 30m, 60m, 90m, 1h, 1d, 5d, 1wk, 1mo, 3mo)

        Returns:
            dict with historical data or error
        """
        try:
            company = yf.Ticker(ticker)
            try:
                if company.isin is None:
                    return {"error": f"Ticker {ticker} not found"}
            except Exception as e:
                return {"error": f"Error validating ticker {ticker}: {e}"}

            hist_data = company.history(period=period, interval=interval)
            hist_data = hist_data.reset_index(names="Date")
            return {
                "ticker": ticker,
                "period": period,
                "interval": interval,
                "data": json.loads(hist_data.to_json(orient="records", date_format="iso"))
            }
        except Exception as e:
            return {"error": str(e)}

    @staticmethod
    async def get_stock_info(tickers: str) -> dict:
        """
        Get comprehensive stock information for one or more tickers.

        Args:
            tickers: Single ticker or comma-separated tickers (e.g., "AAPL" or "AAPL,MSFT")

        Returns:
            dict with stock info for each ticker
        """
        ticker_list = [t.strip().upper() for t in tickers.split(",") if t.strip()]

        if not ticker_list:
            return {"error": "No valid tickers provided"}

        if len(ticker_list) == 1:
            ticker = ticker_list[0]
            company = yf.Ticker(ticker)
            try:
                if company.isin is None:
                    return {"error": f"Ticker {ticker} not found"}
            except Exception as e:
                return {"error": f"Error getting info for {ticker}: {e}"}
            return company.info

        # Multiple tickers - batch fetch
        result = {}
        ticker_str = " ".join(ticker_list)

        try:
            batch = yf.Tickers(ticker_str)
            for ticker in ticker_list:
                try:
                    company = batch.tickers.get(ticker)
                    if company:
                        info = company.info
                        if info and info.get("regularMarketPrice") is not None:
                            result[ticker] = info
                        else:
                            result[ticker] = {"error": f"No data available for {ticker}"}
                    else:
                        result[ticker] = {"error": f"Ticker {ticker} not found"}
                except Exception as e:
                    result[ticker] = {"error": str(e)}
        except Exception as e:
            return {"error": f"Batch fetch failed: {str(e)}"}

        return result

    @staticmethod
    async def get_news(ticker: str) -> dict:
        """
        Get news articles for a ticker.

        Args:
            ticker: Stock ticker symbol

        Returns:
            dict with news articles
        """
        try:
            company = yf.Ticker(ticker)
            try:
                if company.isin is None:
                    return {"error": f"Ticker {ticker} not found"}
            except Exception as e:
                return {"error": f"Error getting news for {ticker}: {e}"}

            news_list = []
            for news in company.news:
                if news.get("content", {}).get("contentType", "") == "STORY":
                    news_list.append({
                        "title": news.get("content", {}).get("title", ""),
                        "summary": news.get("content", {}).get("summary", ""),
                        "description": news.get("content", {}).get("description", ""),
                        "url": news.get("content", {}).get("canonicalUrl", {}).get("url", "")
                    })

            if not news_list:
                return {"ticker": ticker, "news": [], "message": "No news found"}

            return {"ticker": ticker, "news": news_list}
        except Exception as e:
            return {"error": str(e)}

    @staticmethod
    async def get_stock_actions(ticker: str) -> dict:
        """
        Get dividends and stock splits.

        Args:
            ticker: Stock ticker symbol

        Returns:
            dict with dividends and splits data
        """
        try:
            company = yf.Ticker(ticker)
            actions_df = company.actions
            actions_df = actions_df.reset_index(names="Date")
            return {
                "ticker": ticker,
                "actions": json.loads(actions_df.to_json(orient="records", date_format="iso"))
            }
        except Exception as e:
            return {"error": str(e)}

    @staticmethod
    async def get_financial_statement(
        ticker: str,
        statement_type: Literal[
            "income_stmt", "quarterly_income_stmt",
            "balance_sheet", "quarterly_balance_sheet",
            "cashflow", "quarterly_cashflow"
        ]
    ) -> dict:
        """
        Get financial statement data.

        Args:
            ticker: Stock ticker symbol
            statement_type: Type of statement to retrieve

        Returns:
            dict with financial statement data
        """
        try:
            company = yf.Ticker(ticker)
            try:
                if company.isin is None:
                    return {"error": f"Ticker {ticker} not found"}
            except Exception as e:
                return {"error": f"Error getting financial statement for {ticker}: {e}"}

            statement_map = {
                "income_stmt": company.income_stmt,
                "quarterly_income_stmt": company.quarterly_income_stmt,
                "balance_sheet": company.balance_sheet,
                "quarterly_balance_sheet": company.quarterly_balance_sheet,
                "cashflow": company.cashflow,
                "quarterly_cashflow": company.quarterly_cashflow
            }

            if statement_type not in statement_map:
                return {"error": f"Invalid statement type: {statement_type}"}

            financial_statement = statement_map[statement_type]

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

            return {"ticker": ticker, "statement_type": statement_type, "data": result}
        except Exception as e:
            return {"error": str(e)}

    @staticmethod
    async def get_holder_info(
        ticker: str,
        holder_type: Literal[
            "major_holders", "institutional_holders", "mutualfund_holders",
            "insider_transactions", "insider_purchases", "insider_roster_holders"
        ]
    ) -> dict:
        """
        Get holder information.

        Args:
            ticker: Stock ticker symbol
            holder_type: Type of holder info to retrieve

        Returns:
            dict with holder data
        """
        try:
            company = yf.Ticker(ticker)
            try:
                if company.isin is None:
                    return {"error": f"Ticker {ticker} not found"}
            except Exception as e:
                return {"error": f"Error getting holder info for {ticker}: {e}"}

            holder_map = {
                "major_holders": lambda: company.major_holders.reset_index(names="metric"),
                "institutional_holders": lambda: company.institutional_holders,
                "mutualfund_holders": lambda: company.mutualfund_holders,
                "insider_transactions": lambda: company.insider_transactions,
                "insider_purchases": lambda: company.insider_purchases,
                "insider_roster_holders": lambda: company.insider_roster_holders
            }

            if holder_type not in holder_map:
                return {"error": f"Invalid holder type: {holder_type}"}

            data_df = holder_map[holder_type]()
            return {
                "ticker": ticker,
                "holder_type": holder_type,
                "data": json.loads(data_df.to_json(orient="records", date_format="iso"))
            }
        except Exception as e:
            return {"error": str(e)}

    @staticmethod
    async def get_option_expirations(ticker: str) -> dict:
        """
        Get available options expiration dates.

        Args:
            ticker: Stock ticker symbol

        Returns:
            dict with expiration dates
        """
        try:
            company = yf.Ticker(ticker)
            try:
                if company.isin is None:
                    return {"error": f"Ticker {ticker} not found"}
            except Exception as e:
                return {"error": f"Error getting options for {ticker}: {e}"}

            return {"ticker": ticker, "expirations": list(company.options)}
        except Exception as e:
            return {"error": str(e)}

    @staticmethod
    async def get_option_chain(
        ticker: str,
        expiration_date: str,
        option_type: Literal["calls", "puts"]
    ) -> dict:
        """
        Get options chain data.

        Args:
            ticker: Stock ticker symbol
            expiration_date: Expiration date (YYYY-MM-DD)
            option_type: "calls" or "puts"

        Returns:
            dict with options chain data
        """
        try:
            company = yf.Ticker(ticker)
            try:
                if company.isin is None:
                    return {"error": f"Ticker {ticker} not found"}
            except Exception as e:
                return {"error": f"Error getting option chain for {ticker}: {e}"}

            if expiration_date not in company.options:
                return {"error": f"No options available for date {expiration_date}"}

            option_chain = company.option_chain(expiration_date)
            if option_type == "calls":
                data = option_chain.calls
            else:
                data = option_chain.puts

            return {
                "ticker": ticker,
                "expiration_date": expiration_date,
                "option_type": option_type,
                "data": json.loads(data.to_json(orient="records", date_format="iso"))
            }
        except Exception as e:
            return {"error": str(e)}

    @staticmethod
    async def get_recommendations(
        ticker: str,
        recommendation_type: Literal["recommendations", "upgrades_downgrades"],
        months_back: int = 12
    ) -> dict:
        """
        Get analyst recommendations.

        Args:
            ticker: Stock ticker symbol
            recommendation_type: Type of recommendations
            months_back: Months of history for upgrades/downgrades

        Returns:
            dict with recommendation data
        """
        try:
            company = yf.Ticker(ticker)
            try:
                if company.isin is None:
                    return {"error": f"Ticker {ticker} not found"}
            except Exception as e:
                return {"error": f"Error getting recommendations for {ticker}: {e}"}

            if recommendation_type == "recommendations":
                data = company.recommendations.to_json(orient="records")
            else:
                upgrades_downgrades = company.upgrades_downgrades.reset_index()
                cutoff_date = pd.Timestamp.now() - pd.DateOffset(months=months_back)
                upgrades_downgrades = upgrades_downgrades[
                    upgrades_downgrades["GradeDate"] >= cutoff_date
                ]
                upgrades_downgrades = upgrades_downgrades.sort_values("GradeDate", ascending=False)
                latest_by_firm = upgrades_downgrades.drop_duplicates(subset=["Firm"])
                data = latest_by_firm.to_json(orient="records", date_format="iso")

            return {
                "ticker": ticker,
                "recommendation_type": recommendation_type,
                "data": json.loads(data)
            }
        except Exception as e:
            return {"error": str(e)}

    @staticmethod
    async def get_fx_rate(from_currency: str, to_currency: str) -> dict:
        """
        Get foreign exchange rate.

        Args:
            from_currency: Source currency code (e.g., "GBP")
            to_currency: Target currency code (e.g., "USD")

        Returns:
            dict with FX rate data
        """
        try:
            ticker_symbol = f"{from_currency.upper()}{to_currency.upper()}=X"
            ticker = yf.Ticker(ticker_symbol)
            info = ticker.info

            rate = info.get("regularMarketPrice")
            if rate is None:
                return {
                    "error": f"Could not get rate for {from_currency}/{to_currency}",
                    "message": "Check that both currency codes are valid"
                }

            return {
                "from": from_currency.upper(),
                "to": to_currency.upper(),
                "rate": rate,
                "bid": info.get("bid"),
                "ask": info.get("ask"),
                "day_high": info.get("dayHigh"),
                "day_low": info.get("dayLow"),
                "description": f"1 {from_currency.upper()} = {rate} {to_currency.upper()}"
            }
        except Exception as e:
            return {"error": str(e)}
