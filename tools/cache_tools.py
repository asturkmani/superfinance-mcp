"""Cache management tools."""

import json
from typing import Optional

import cache
import refresh


def register_cache_tools(server):
    """Register cache management tools with the server."""

    @server.tool()
    def refresh_cache(
        data_type: str = "all",
        user_id: Optional[str] = None,
        user_secret: Optional[str] = None
    ) -> str:
        """
        Force refresh cached data.

        Manually triggers a refresh of cached data. Useful when you need
        the latest data immediately rather than waiting for scheduled refresh.

        Args:
            data_type: Type of data to refresh. Options:
                       - "prices" - Refresh stock prices for all tracked symbols
                       - "fx" - Refresh FX rates for common currency pairs
                       - "holdings" - Refresh brokerage holdings from SnapTrade
                       - "all" - Refresh everything (default)
            user_id: SnapTrade user ID (required for 'holdings' or 'all', uses env var if not provided)
            user_secret: SnapTrade user secret (required for 'holdings' or 'all', uses env var if not provided)

        Returns:
            JSON string with refresh status and counts
        """
        try:
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

        except Exception as e:
            return json.dumps({
                "error": str(e)
            }, indent=2)

    @server.tool()
    def get_cache_status() -> str:
        """
        Get cache status and health information.

        Returns information about:
        - Whether cache is available
        - Last refresh times for each data type
        - Number of tracked symbols
        - Background scheduler status

        Use this to verify cache is working and data is fresh.

        Returns:
            JSON string with cache status information
        """
        try:
            status = cache.get_cache_status()
            status["scheduler"] = refresh.get_scheduler_status()

            return json.dumps(status, indent=2)

        except Exception as e:
            return json.dumps({
                "error": str(e)
            }, indent=2)
