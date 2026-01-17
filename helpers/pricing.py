"""Pricing helpers for fetching live prices and FX rates."""

from typing import Optional

import yfinance as yf

import cache


def get_live_price(symbol: str, use_cache: bool = True) -> dict:
    """
    Fetch live price for a symbol.
    Checks cache first, then falls back to Yahoo Finance API.

    Args:
        symbol: The ticker symbol to fetch price for
        use_cache: Whether to check cache first (default True)

    Returns:
        dict with price info or error
    """
    # Try cache first
    if use_cache:
        cached = cache.get_cached_price(symbol)
        if cached and cached.get("price") is not None:
            return {
                "price": cached["price"],
                "source": "cache",
                "currency": cached.get("currency"),
                "name": cached.get("name"),
                "cached_at": cached.get("cached_at")
            }

    # Fallback to API
    try:
        ticker = yf.Ticker(symbol)
        info = ticker.info
        price = info.get("regularMarketPrice")
        if price is not None:
            result = {
                "price": price,
                "source": "yahoo_finance",
                "currency": info.get("currency"),
                "name": info.get("shortName") or info.get("longName")
            }

            # Cache the price and track the symbol
            price_data = {
                "price": price,
                "currency": info.get("currency"),
                "name": info.get("shortName") or info.get("longName"),
                "bid": info.get("bid"),
                "ask": info.get("ask"),
                "day_high": info.get("dayHigh"),
                "day_low": info.get("dayLow"),
                "source": "yahoo_finance"
            }
            cache.cache_price(symbol, price_data)
            cache.add_symbol(symbol)

            return result
        return {"price": None, "source": "unavailable", "error": f"No price for {symbol}"}
    except Exception as e:
        return {"price": None, "source": "error", "error": str(e)}


def get_fx_rate_cached(from_currency: str, to_currency: str, local_cache: dict) -> Optional[float]:
    """
    Get FX rate with caching to avoid repeated API calls.
    Uses Redis cache first, then local in-memory cache, then API.

    Args:
        from_currency: Source currency code (e.g., "USD")
        to_currency: Target currency code (e.g., "GBP")
        local_cache: In-memory dict for within-request caching

    Returns:
        Exchange rate as float, or None if unavailable
    """
    if from_currency == to_currency:
        return 1.0

    cache_key = f"{from_currency}_{to_currency}"

    # Check local in-memory cache (for within-request caching)
    if cache_key in local_cache:
        return local_cache[cache_key]

    # Check Redis cache
    cached = cache.get_cached_fx_rate(from_currency, to_currency)
    if cached and cached.get("rate") is not None:
        rate = cached["rate"]
        local_cache[cache_key] = rate
        return rate

    # Fallback to API
    try:
        ticker_symbol = f"{from_currency.upper()}{to_currency.upper()}=X"
        ticker = yf.Ticker(ticker_symbol)
        info = ticker.info
        rate = info.get("regularMarketPrice")
        if rate:
            local_cache[cache_key] = rate

            # Cache in Redis
            rate_data = {
                "rate": rate,
                "bid": info.get("bid"),
                "ask": info.get("ask"),
                "day_high": info.get("dayHigh"),
                "day_low": info.get("dayLow"),
                "source": "yahoo_finance"
            }
            cache.cache_fx_rate(from_currency, to_currency, rate_data)

            return rate
    except:
        pass

    return None
