"""Cache management API routes."""

from typing import Literal, Optional

from fastapi import APIRouter, Query

import cache
import refresh


router = APIRouter()


@router.get("/status")
async def get_cache_status_endpoint():
    """
    Get cache health and status information.

    Returns:
    - Cache availability
    - Last refresh times
    - Tracked symbols
    - Scheduler status
    """
    if not cache.is_cache_available():
        return {
            "cache_available": False,
            "message": "Redis cache not configured"
        }

    # Use the cache module's get_cache_status which includes last refresh times
    status = cache.get_cache_status()
    status["scheduler"] = refresh.get_scheduler_status()

    return status


@router.post("/refresh")
async def refresh_cache(
    refresh_type: Literal["prices", "fx", "holdings", "all"] = Query(
        "all",
        description="Type of data to refresh"
    ),
    user_id: Optional[str] = Query(None, description="SnapTrade user ID (for holdings refresh)"),
    user_secret: Optional[str] = Query(None, description="SnapTrade user secret (for holdings refresh)")
):
    """
    Force refresh cached data.

    - **refresh_type**: What to refresh
      - `prices`: Stock prices for tracked symbols
      - `fx`: Foreign exchange rates
      - `holdings`: SnapTrade holdings (requires credentials)
      - `all`: Everything

    Note: Holdings refresh requires SnapTrade credentials.
    """
    if not cache.is_cache_available():
        return {
            "success": False,
            "error": "Redis cache not configured"
        }

    results = {}

    if refresh_type in ["prices", "all"]:
        try:
            result = refresh.refresh_all_prices()
            results["prices"] = result
        except Exception as e:
            results["prices"] = {"error": str(e)}

    if refresh_type in ["fx", "all"]:
        try:
            result = refresh.refresh_fx_rates()
            results["fx"] = result
        except Exception as e:
            results["fx"] = {"error": str(e)}

    if refresh_type in ["holdings", "all"]:
        if user_id and user_secret:
            try:
                result = refresh.refresh_all_holdings(user_id, user_secret)
                results["holdings"] = result
            except Exception as e:
                results["holdings"] = {"error": str(e)}
        else:
            results["holdings"] = {"skipped": "credentials required"}

    return {
        "success": True,
        "refreshed": results
    }
