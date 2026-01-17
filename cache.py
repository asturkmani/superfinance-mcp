"""
Redis caching layer for SuperFinance MCP using Upstash Redis.

Cache key structure:
- superfinance:accounts:{user_id}                    - List of accounts
- superfinance:holdings:{user_id}:{account_id}       - Holdings for account
- superfinance:holdings_all:{user_id}                - All holdings combined
- superfinance:price:{symbol}                        - Stock price
- superfinance:fx:{from}_{to}                        - FX rate
- superfinance:portfolio:{portfolio_id}              - Manual portfolio
- superfinance:meta:last_refresh:{type}              - Refresh timestamps
- superfinance:meta:symbols                          - Set of all tracked symbols
"""

import json
import os
from datetime import datetime
from typing import Any, Optional

from dotenv import load_dotenv
from pathlib import Path

# Load environment variables
env_path = Path(__file__).parent / '.env'
if env_path.exists():
    load_dotenv(env_path)


# Cache TTL configuration (in seconds)
CACHE_HOLDINGS_TTL = int(os.getenv("CACHE_HOLDINGS_TTL", 90000))  # 25 hours
CACHE_PRICES_TTL = int(os.getenv("CACHE_PRICES_TTL", 600))  # 10 minutes
CACHE_FX_TTL = int(os.getenv("CACHE_FX_TTL", 600))  # 10 minutes
CACHE_ACCOUNTS_TTL = int(os.getenv("CACHE_ACCOUNTS_TTL", 90000))  # 25 hours

# Cache key prefix
KEY_PREFIX = "superfinance"

# Redis client (lazy initialization)
_redis_client = None


def _get_redis_client():
    """Get or create the Redis client (lazy initialization)."""
    global _redis_client

    if _redis_client is not None:
        return _redis_client

    # Support both naming conventions (Upstash default uses REST suffix)
    url = os.getenv("UPSTASH_REDIS_REST_URL") or os.getenv("UPSTASH_REDIS_URL")
    token = os.getenv("UPSTASH_REDIS_REST_TOKEN") or os.getenv("UPSTASH_REDIS_TOKEN")

    if not url or not token:
        return None

    try:
        from upstash_redis import Redis
        _redis_client = Redis(url=url, token=token)
        return _redis_client
    except Exception as e:
        print(f"Warning: Failed to initialize Redis client: {e}")
        return None


def is_cache_available() -> bool:
    """Check if Redis cache is available."""
    return _get_redis_client() is not None


def _make_key(*parts: str) -> str:
    """Create a cache key with the standard prefix."""
    return ":".join([KEY_PREFIX] + list(parts))


def get_cached(key: str) -> Optional[dict]:
    """
    Get a cached value by key.

    Args:
        key: The cache key (without prefix)

    Returns:
        The cached value as a dict, or None if not found/error
    """
    redis = _get_redis_client()
    if not redis:
        return None

    try:
        full_key = _make_key(key)
        value = redis.get(full_key)

        if value is None:
            return None

        # Handle both string and dict responses
        if isinstance(value, str):
            return json.loads(value)
        return value

    except Exception as e:
        print(f"Cache get error for {key}: {e}")
        return None


def set_cached(key: str, data: Any, ttl_seconds: Optional[int] = None) -> bool:
    """
    Set a cached value with optional TTL.

    Args:
        key: The cache key (without prefix)
        data: The data to cache (will be JSON serialized)
        ttl_seconds: TTL in seconds (None = no expiry)

    Returns:
        True if successful, False otherwise
    """
    redis = _get_redis_client()
    if not redis:
        return False

    try:
        full_key = _make_key(key)
        value = json.dumps(data)

        if ttl_seconds:
            redis.setex(full_key, ttl_seconds, value)
        else:
            redis.set(full_key, value)

        return True

    except Exception as e:
        print(f"Cache set error for {key}: {e}")
        return False


def delete_cached(key: str) -> bool:
    """
    Delete a cached value.

    Args:
        key: The cache key (without prefix)

    Returns:
        True if successful, False otherwise
    """
    redis = _get_redis_client()
    if not redis:
        return False

    try:
        full_key = _make_key(key)
        redis.delete(full_key)
        return True

    except Exception as e:
        print(f"Cache delete error for {key}: {e}")
        return False


def invalidate_pattern(pattern: str) -> int:
    """
    Invalidate all keys matching a pattern.

    Note: Upstash doesn't support SCAN, so we track keys manually.
    This function is best-effort for known key patterns.

    Args:
        pattern: The pattern to match (e.g., "holdings:*")

    Returns:
        Number of keys deleted (or 0 if not supported)
    """
    redis = _get_redis_client()
    if not redis:
        return 0

    # For Upstash, we'll need to track keys explicitly
    # This is a limitation - we'll handle specific patterns
    print(f"Warning: Pattern-based invalidation not fully supported for: {pattern}")
    return 0


# ============================================================================
# Symbol tracking for batch price refresh
# ============================================================================

def add_symbol(symbol: str) -> bool:
    """Add a symbol to the tracked symbols set."""
    redis = _get_redis_client()
    if not redis:
        return False

    try:
        key = _make_key("meta", "symbols")
        redis.sadd(key, symbol.upper())
        return True
    except Exception as e:
        print(f"Error adding symbol {symbol}: {e}")
        return False


def add_symbols(symbols: list[str]) -> bool:
    """Add multiple symbols to the tracked symbols set."""
    redis = _get_redis_client()
    if not redis:
        return False

    try:
        key = _make_key("meta", "symbols")
        for symbol in symbols:
            redis.sadd(key, symbol.upper())
        return True
    except Exception as e:
        print(f"Error adding symbols: {e}")
        return False


def get_all_symbols() -> list[str]:
    """Get all tracked symbols for batch price refresh."""
    redis = _get_redis_client()
    if not redis:
        return []

    try:
        key = _make_key("meta", "symbols")
        symbols = redis.smembers(key)
        return list(symbols) if symbols else []
    except Exception as e:
        print(f"Error getting symbols: {e}")
        return []


def remove_symbol(symbol: str) -> bool:
    """Remove a symbol from the tracked symbols set."""
    redis = _get_redis_client()
    if not redis:
        return False

    try:
        key = _make_key("meta", "symbols")
        redis.srem(key, symbol.upper())
        return True
    except Exception as e:
        print(f"Error removing symbol {symbol}: {e}")
        return False


# ============================================================================
# Specialized cache functions for different data types
# ============================================================================

def cache_price(symbol: str, price_data: dict) -> bool:
    """Cache a stock price with standard TTL."""
    key = f"price:{symbol.upper()}"
    price_data["cached_at"] = datetime.utcnow().isoformat() + "Z"
    return set_cached(key, price_data, CACHE_PRICES_TTL)


def get_cached_price(symbol: str) -> Optional[dict]:
    """Get a cached stock price."""
    key = f"price:{symbol.upper()}"
    return get_cached(key)


def cache_fx_rate(from_currency: str, to_currency: str, rate_data: dict) -> bool:
    """Cache an FX rate with standard TTL."""
    key = f"fx:{from_currency.upper()}_{to_currency.upper()}"
    rate_data["cached_at"] = datetime.utcnow().isoformat() + "Z"
    return set_cached(key, rate_data, CACHE_FX_TTL)


def get_cached_fx_rate(from_currency: str, to_currency: str) -> Optional[dict]:
    """Get a cached FX rate."""
    key = f"fx:{from_currency.upper()}_{to_currency.upper()}"
    return get_cached(key)


def cache_holdings(user_id: str, account_id: str, holdings_data: dict) -> bool:
    """Cache holdings for a specific account."""
    key = f"holdings:{user_id}:{account_id}"
    holdings_data["cached_at"] = datetime.utcnow().isoformat() + "Z"
    return set_cached(key, holdings_data, CACHE_HOLDINGS_TTL)


def get_cached_holdings(user_id: str, account_id: str) -> Optional[dict]:
    """Get cached holdings for a specific account."""
    key = f"holdings:{user_id}:{account_id}"
    return get_cached(key)


def cache_all_holdings(user_id: str, holdings_data: dict) -> bool:
    """Cache all holdings combined for a user."""
    key = f"holdings_all:{user_id}"
    holdings_data["cached_at"] = datetime.utcnow().isoformat() + "Z"
    return set_cached(key, holdings_data, CACHE_HOLDINGS_TTL)


def get_cached_all_holdings(user_id: str) -> Optional[dict]:
    """Get all cached holdings for a user."""
    key = f"holdings_all:{user_id}"
    return get_cached(key)


def cache_accounts(user_id: str, accounts_data: dict) -> bool:
    """Cache accounts list for a user."""
    key = f"accounts:{user_id}"
    accounts_data["cached_at"] = datetime.utcnow().isoformat() + "Z"
    return set_cached(key, accounts_data, CACHE_ACCOUNTS_TTL)


def get_cached_accounts(user_id: str) -> Optional[dict]:
    """Get cached accounts for a user."""
    key = f"accounts:{user_id}"
    return get_cached(key)


# ============================================================================
# Refresh metadata tracking
# ============================================================================

def set_last_refresh(refresh_type: str) -> bool:
    """Record the last refresh time for a type."""
    key = f"meta:last_refresh:{refresh_type}"
    data = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "type": refresh_type
    }
    return set_cached(key, data, None)  # No expiry for metadata


def get_last_refresh(refresh_type: str) -> Optional[dict]:
    """Get the last refresh time for a type."""
    key = f"meta:last_refresh:{refresh_type}"
    return get_cached(key)


def get_cache_status() -> dict:
    """
    Get overall cache status including last refresh times.

    Returns:
        Dict with cache status information
    """
    status = {
        "available": is_cache_available(),
        "last_refresh": {}
    }

    if not status["available"]:
        return status

    # Check last refresh times for each type
    for refresh_type in ["prices", "fx_rates", "holdings"]:
        last = get_last_refresh(refresh_type)
        if last:
            status["last_refresh"][refresh_type] = last.get("timestamp")
        else:
            status["last_refresh"][refresh_type] = None

    # Get symbol count
    symbols = get_all_symbols()
    status["tracked_symbols_count"] = len(symbols)
    status["tracked_symbols"] = symbols[:20]  # First 20 only
    if len(symbols) > 20:
        status["tracked_symbols_truncated"] = True

    return status
