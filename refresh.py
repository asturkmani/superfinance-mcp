"""
Background refresh jobs for SuperFinance MCP cache.

This module handles scheduled refresh of cached data:
- Stock prices: Every 5 minutes (market hours) or configurable
- FX rates: Every 5 minutes
- Holdings: Every 12 hours

Uses APScheduler for in-process scheduling when running on Fly.io.
"""

import os
from datetime import datetime
from typing import Optional

import yfinance as yf
from dotenv import load_dotenv
from pathlib import Path

# Load environment variables
env_path = Path(__file__).parent / '.env'
if env_path.exists():
    load_dotenv(env_path)

from cache import (
    add_symbols,
    cache_accounts,
    cache_all_holdings,
    cache_fx_rate,
    cache_holdings,
    cache_price,
    get_all_symbols,
    is_cache_available,
    set_last_refresh,
)

# Refresh intervals (in seconds)
REFRESH_PRICES_INTERVAL = int(os.getenv("REFRESH_PRICES_INTERVAL", 300))  # 5 minutes
REFRESH_FX_INTERVAL = int(os.getenv("REFRESH_FX_INTERVAL", 300))  # 5 minutes
REFRESH_HOLDINGS_INTERVAL = int(os.getenv("REFRESH_HOLDINGS_INTERVAL", 43200))  # 12 hours

# Common FX pairs to always refresh
COMMON_FX_PAIRS = [
    ("USD", "GBP"),
    ("USD", "EUR"),
    ("GBP", "USD"),
    ("GBP", "EUR"),
    ("EUR", "USD"),
    ("EUR", "GBP"),
    ("USD", "CAD"),
    ("USD", "JPY"),
    ("USD", "CHF"),
]

# SnapTrade client (lazy initialization)
_snaptrade_client = None


def _get_snaptrade_client():
    """Get or create the SnapTrade client."""
    global _snaptrade_client

    if _snaptrade_client is not None:
        return _snaptrade_client

    consumer_key = os.getenv("SNAPTRADE_CONSUMER_KEY")
    client_id = os.getenv("SNAPTRADE_CLIENT_ID")

    if not consumer_key or not client_id:
        return None

    try:
        from snaptrade_client import SnapTrade
        _snaptrade_client = SnapTrade(
            consumer_key=consumer_key,
            client_id=client_id
        )
        return _snaptrade_client
    except Exception as e:
        print(f"Warning: Failed to initialize SnapTrade client: {e}")
        return None


def refresh_all_prices() -> dict:
    """
    Refresh prices for all tracked symbols.

    Fetches from Yahoo Finance using batch requests for efficiency.
    Updates the cache with new prices.

    Returns:
        Dict with refresh status and counts
    """
    if not is_cache_available():
        return {"success": False, "error": "Cache not available"}

    symbols = get_all_symbols()
    if not symbols:
        return {
            "success": True,
            "message": "No symbols to refresh",
            "refreshed": 0,
            "failed": 0
        }

    print(f"[{datetime.utcnow().isoformat()}] Refreshing prices for {len(symbols)} symbols...")

    refreshed = 0
    failed = 0
    errors = []

    # Process in batches to avoid rate limits
    batch_size = 50
    for i in range(0, len(symbols), batch_size):
        batch = symbols[i:i + batch_size]

        try:
            # yfinance supports batch downloads
            tickers = yf.Tickers(" ".join(batch))

            for symbol in batch:
                try:
                    ticker = tickers.tickers.get(symbol)
                    if ticker:
                        info = ticker.info
                        price = info.get("regularMarketPrice")

                        if price is not None:
                            price_data = {
                                "price": price,
                                "currency": info.get("currency"),
                                "name": info.get("shortName") or info.get("longName"),
                                "bid": info.get("bid"),
                                "ask": info.get("ask"),
                                "day_high": info.get("dayHigh"),
                                "day_low": info.get("dayLow"),
                                "volume": info.get("volume"),
                                "market_cap": info.get("marketCap"),
                                "source": "yahoo_finance"
                            }

                            if cache_price(symbol, price_data):
                                refreshed += 1
                            else:
                                failed += 1
                                errors.append(f"{symbol}: cache write failed")
                        else:
                            failed += 1
                            errors.append(f"{symbol}: no price available")
                    else:
                        failed += 1
                        errors.append(f"{symbol}: ticker not found")

                except Exception as e:
                    failed += 1
                    errors.append(f"{symbol}: {str(e)}")

        except Exception as e:
            # Batch failed, try individual fetches
            print(f"Batch fetch failed, trying individually: {e}")
            for symbol in batch:
                try:
                    ticker = yf.Ticker(symbol)
                    info = ticker.info
                    price = info.get("regularMarketPrice")

                    if price is not None:
                        price_data = {
                            "price": price,
                            "currency": info.get("currency"),
                            "name": info.get("shortName") or info.get("longName"),
                            "source": "yahoo_finance"
                        }

                        if cache_price(symbol, price_data):
                            refreshed += 1
                        else:
                            failed += 1
                except Exception as e2:
                    failed += 1
                    errors.append(f"{symbol}: {str(e2)}")

    # Update last refresh timestamp
    set_last_refresh("prices")

    result = {
        "success": True,
        "refreshed": refreshed,
        "failed": failed,
        "total": len(symbols),
        "timestamp": datetime.utcnow().isoformat() + "Z"
    }

    if errors:
        result["errors"] = errors[:10]  # First 10 errors only
        if len(errors) > 10:
            result["errors_truncated"] = True

    print(f"[{datetime.utcnow().isoformat()}] Price refresh complete: {refreshed} refreshed, {failed} failed")

    return result


def refresh_fx_rates() -> dict:
    """
    Refresh FX rates for common currency pairs.

    Returns:
        Dict with refresh status and counts
    """
    if not is_cache_available():
        return {"success": False, "error": "Cache not available"}

    print(f"[{datetime.utcnow().isoformat()}] Refreshing FX rates...")

    refreshed = 0
    failed = 0
    errors = []

    for from_curr, to_curr in COMMON_FX_PAIRS:
        try:
            ticker_symbol = f"{from_curr}{to_curr}=X"
            ticker = yf.Ticker(ticker_symbol)
            info = ticker.info

            rate = info.get("regularMarketPrice")
            if rate is not None:
                rate_data = {
                    "rate": rate,
                    "bid": info.get("bid"),
                    "ask": info.get("ask"),
                    "day_high": info.get("dayHigh"),
                    "day_low": info.get("dayLow"),
                    "source": "yahoo_finance"
                }

                if cache_fx_rate(from_curr, to_curr, rate_data):
                    refreshed += 1
                else:
                    failed += 1
                    errors.append(f"{from_curr}/{to_curr}: cache write failed")
            else:
                failed += 1
                errors.append(f"{from_curr}/{to_curr}: no rate available")

        except Exception as e:
            failed += 1
            errors.append(f"{from_curr}/{to_curr}: {str(e)}")

    # Update last refresh timestamp
    set_last_refresh("fx_rates")

    print(f"[{datetime.utcnow().isoformat()}] FX refresh complete: {refreshed} refreshed, {failed} failed")

    return {
        "success": True,
        "refreshed": refreshed,
        "failed": failed,
        "total": len(COMMON_FX_PAIRS),
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "errors": errors if errors else None
    }


def refresh_all_holdings(user_id: Optional[str] = None, user_secret: Optional[str] = None) -> dict:
    """
    Refresh holdings for all accounts from SnapTrade.

    Args:
        user_id: SnapTrade user ID (uses env var if not provided)
        user_secret: SnapTrade user secret (uses env var if not provided)

    Returns:
        Dict with refresh status
    """
    if not is_cache_available():
        return {"success": False, "error": "Cache not available"}

    snaptrade = _get_snaptrade_client()
    if not snaptrade:
        return {"success": False, "error": "SnapTrade not configured"}

    user_id = user_id or os.getenv("SNAPTRADE_USER_ID")
    user_secret = user_secret or os.getenv("SNAPTRADE_USER_SECRET")

    if not user_id or not user_secret:
        return {"success": False, "error": "SnapTrade credentials not provided"}

    print(f"[{datetime.utcnow().isoformat()}] Refreshing holdings for user {user_id}...")

    try:
        # Get all accounts
        accounts_response = snaptrade.account_information.list_user_accounts(
            user_id=user_id,
            user_secret=user_secret
        )
        accounts = accounts_response.body if hasattr(accounts_response, 'body') else accounts_response

        # Format and cache accounts
        formatted_accounts = []
        for account in accounts:
            if hasattr(account, 'to_dict'):
                account = account.to_dict()
            formatted_accounts.append({
                "account_id": account.get("id"),
                "brokerage_authorization": account.get("brokerage_authorization"),
                "name": account.get("name"),
                "number": account.get("number"),
                "institution": account.get("institution_name"),
                "balance": account.get("balance"),
                "meta": account.get("meta", {})
            })

        accounts_data = {
            "count": len(formatted_accounts),
            "accounts": formatted_accounts
        }
        cache_accounts(user_id, accounts_data)

        # Get and cache holdings for each account
        all_symbols = set()
        all_holdings = []
        accounts_refreshed = 0

        for account in accounts:
            if hasattr(account, 'to_dict'):
                account = account.to_dict()

            account_id = account.get("id")

            try:
                holdings_response = snaptrade.account_information.get_user_holdings(
                    account_id=account_id,
                    user_id=user_id,
                    user_secret=user_secret
                )
                holdings = holdings_response.body if hasattr(holdings_response, 'body') else holdings_response
                if hasattr(holdings, 'to_dict'):
                    holdings = holdings.to_dict()

                # Extract symbols from positions
                for position in holdings.get("positions", []):
                    if hasattr(position, 'to_dict'):
                        position = position.to_dict()
                    symbol_data = position.get("symbol", {})
                    if hasattr(symbol_data, 'to_dict'):
                        symbol_data = symbol_data.to_dict()

                    # Handle nested symbol structure
                    if "symbol" in symbol_data and isinstance(symbol_data["symbol"], dict):
                        symbol = symbol_data["symbol"].get("symbol")
                    else:
                        symbol = symbol_data.get("symbol")

                    if symbol:
                        all_symbols.add(symbol.upper())

                # Cache individual account holdings
                cache_holdings(user_id, account_id, holdings)
                all_holdings.append({
                    "account_id": account_id,
                    "name": account.get("name"),
                    "institution": account.get("institution_name"),
                    "holdings": holdings
                })
                accounts_refreshed += 1

            except Exception as e:
                print(f"Error fetching holdings for account {account_id}: {e}")
                all_holdings.append({
                    "account_id": account_id,
                    "name": account.get("name"),
                    "error": str(e)
                })

        # Cache combined holdings
        combined = {
            "accounts_count": len(all_holdings),
            "accounts": all_holdings
        }
        cache_all_holdings(user_id, combined)

        # Update tracked symbols
        if all_symbols:
            add_symbols(list(all_symbols))

        # Update last refresh timestamp
        set_last_refresh("holdings")

        print(f"[{datetime.utcnow().isoformat()}] Holdings refresh complete: {accounts_refreshed} accounts, {len(all_symbols)} symbols tracked")

        return {
            "success": True,
            "accounts_refreshed": accounts_refreshed,
            "symbols_tracked": len(all_symbols),
            "timestamp": datetime.utcnow().isoformat() + "Z"
        }

    except Exception as e:
        print(f"Error refreshing holdings: {e}")
        return {"success": False, "error": str(e)}


def refresh_all(user_id: Optional[str] = None, user_secret: Optional[str] = None) -> dict:
    """
    Refresh all cached data (prices, FX rates, and holdings).

    Args:
        user_id: SnapTrade user ID for holdings refresh
        user_secret: SnapTrade user secret for holdings refresh

    Returns:
        Dict with combined refresh status
    """
    results = {
        "timestamp": datetime.utcnow().isoformat() + "Z"
    }

    # Refresh holdings first (to get symbols)
    results["holdings"] = refresh_all_holdings(user_id, user_secret)

    # Then prices and FX rates
    results["prices"] = refresh_all_prices()
    results["fx_rates"] = refresh_fx_rates()

    return results


# ============================================================================
# APScheduler integration
# ============================================================================

_scheduler = None


def start_scheduler():
    """
    Start the background scheduler for automatic refresh.

    Uses APScheduler with a background thread scheduler.
    """
    global _scheduler

    if _scheduler is not None:
        print("Scheduler already running")
        return

    if not is_cache_available():
        print("Cache not available, scheduler not started")
        return

    try:
        from apscheduler.schedulers.background import BackgroundScheduler
        from apscheduler.triggers.interval import IntervalTrigger
        from apscheduler.triggers.cron import CronTrigger

        _scheduler = BackgroundScheduler()

        # Price refresh every 5 minutes
        _scheduler.add_job(
            refresh_all_prices,
            IntervalTrigger(seconds=REFRESH_PRICES_INTERVAL),
            id="refresh_prices",
            name="Refresh stock prices",
            replace_existing=True
        )

        # FX refresh every 5 minutes
        _scheduler.add_job(
            refresh_fx_rates,
            IntervalTrigger(seconds=REFRESH_FX_INTERVAL),
            id="refresh_fx_rates",
            name="Refresh FX rates",
            replace_existing=True
        )

        # Holdings refresh every 12 hours
        _scheduler.add_job(
            refresh_all_holdings,
            IntervalTrigger(seconds=REFRESH_HOLDINGS_INTERVAL),
            id="refresh_holdings",
            name="Refresh holdings",
            replace_existing=True
        )

        _scheduler.start()
        print(f"[{datetime.utcnow().isoformat()}] Background scheduler started")
        print(f"  - Prices: every {REFRESH_PRICES_INTERVAL}s")
        print(f"  - FX rates: every {REFRESH_FX_INTERVAL}s")
        print(f"  - Holdings: every {REFRESH_HOLDINGS_INTERVAL}s")

        # Do an initial refresh
        print("Running initial refresh...")
        refresh_all_prices()
        refresh_fx_rates()

    except Exception as e:
        print(f"Failed to start scheduler: {e}")
        _scheduler = None


def stop_scheduler():
    """Stop the background scheduler."""
    global _scheduler

    if _scheduler is not None:
        _scheduler.shutdown()
        _scheduler = None
        print("Background scheduler stopped")


def get_scheduler_status() -> dict:
    """Get the status of the background scheduler."""
    if _scheduler is None:
        return {"running": False}

    jobs = []
    for job in _scheduler.get_jobs():
        jobs.append({
            "id": job.id,
            "name": job.name,
            "next_run": job.next_run_time.isoformat() if job.next_run_time else None
        })

    return {
        "running": True,
        "jobs": jobs
    }


# Entry point for direct execution (e.g., from Fly.io machines schedule)
if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        command = sys.argv[1]

        if command == "prices":
            result = refresh_all_prices()
        elif command == "fx":
            result = refresh_fx_rates()
        elif command == "holdings":
            result = refresh_all_holdings()
        elif command == "all":
            result = refresh_all()
        else:
            print(f"Unknown command: {command}")
            print("Usage: python refresh.py [prices|fx|holdings|all]")
            sys.exit(1)

        import json
        print(json.dumps(result, indent=2))
    else:
        print("Usage: python refresh.py [prices|fx|holdings|all]")
        sys.exit(1)
