"""Unified holdings tool - reads from SQLite (populated by sync)."""

import json
from typing import Optional

from services.holdings_service import HoldingsService
from db import queries
from helpers.user_context import get_current_user_id


def register_holdings_tools(server):
    """Register holdings tools with the server."""

    @server.tool()
    async def list_all_holdings(
        user_id: Optional[str] = None,
        reporting_currency: Optional[str] = None
    ) -> str:
        """
        Get all holdings for a user from SQLite.

        This reads from the SQLite database, which is populated by:
        - Manual portfolio operations (via portfolio tools)
        - SnapTrade sync operations (via snaptrade_sync tool)

        Returns positions in their native instrument currency with totals summed per currency.
        If reporting_currency is specified, adds converted totals for unified view.

        Args:
            user_id: User ID (uses default user if not provided)
            reporting_currency: Optional currency code (e.g., "GBP") to convert all values

        Returns:
            JSON with:
            - totals: holdings, cash, value, cost_basis, unrealized_pnl (by currency)
            - accounts: list of accounts with their totals and positions
        """
        try:
            # Get or create default user if not provided
            if not user_id:
                user_id = get_current_user_id()
            
            # Call the service
            result = await HoldingsService.list_all_holdings(
                user_id=user_id,
                reporting_currency=reporting_currency
            )
            
            return json.dumps(result, indent=2)

        except Exception as e:
            return json.dumps({"error": str(e)}, indent=2)
