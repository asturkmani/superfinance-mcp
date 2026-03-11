"""Consolidated cache management tool."""

import json
from typing import Optional

import cache
import refresh


def register_cache_v2(server):
    """Register consolidated cache tool."""

    @server.tool()
    def cache(
        action: str,
        data_type: str = "all",
        user_id: Optional[str] = None,
        user_secret: Optional[str] = None
    ) -> str:
        """
        Manage data cache.

        Actions:
        - status: Get cache health and refresh times
        - refresh: Force refresh cached data

        Args:
            action: Action to perform (status|refresh)
            data_type: For refresh action - what to refresh (prices|fx|holdings|all)
            user_id: SnapTrade user ID (for holdings/all refresh, uses env var if not provided)
            user_secret: SnapTrade user secret (for holdings/all refresh, uses env var if not provided)

        Returns:
            JSON with cache status or refresh results

        Examples:
            cache(action="status")
            cache(action="refresh", data_type="prices")
            cache(action="refresh", data_type="all")
        """
        try:
            if action == "status":
                status = cache.get_cache_status()
                status["scheduler"] = refresh.get_scheduler_status()
                return json.dumps(status, indent=2)

            elif action == "refresh":
                if data_type == "prices":
                    result = refresh.refresh_all_prices()
                elif data_type == "fx":
                    result = refresh.refresh_fx_rates()
                elif data_type == "holdings":
                    result = refresh.refresh_all_holdings(user_id, user_secret)
                elif data_type == "all":
                    result = refresh.refresh_all(user_id, user_secret)
                else:
                    return json.dumps({
                        "error": f"Invalid data_type: {data_type}",
                        "valid_options": ["prices", "fx", "holdings", "all"]
                    }, indent=2)
                return json.dumps(result, indent=2)

            else:
                return json.dumps({
                    "error": f"Invalid action: {action}",
                    "valid_actions": ["status", "refresh"]
                }, indent=2)

        except Exception as e:
            return json.dumps({"error": str(e)}, indent=2)
