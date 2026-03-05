"""Reconciliation MCP tool."""

import json
from typing import Optional

from db import queries
from services.reconciliation import reconcile_account, reconcile_user
from helpers.user_context import get_current_user_id


def register_reconciliation_tools(server):
    """Register reconciliation tools with the server."""

    @server.tool()
    def reconcile(
        user_id: Optional[str] = None,
        account_id: Optional[str] = None
    ) -> str:
        """
        Reconcile holdings against transaction history.

        Compares current holdings quantities with the implied quantities from
        summing all buy/sell transactions. Flags discrepancies where they don't match.

        Use this to check if transaction history is complete for an account.

        Args:
            user_id: User ID (uses default user if not provided)
            account_id: Optional specific account ID. If omitted, reconciles all accounts.

        Returns:
            JSON with matched count, discrepancies, and actionable details.

        Note: SnapTrade transactions may take 24-48 hours to appear after execution.
              Recent trades showing as discrepancies is expected — re-run after the sync delay.
        """
        if not user_id:
            user_id = get_current_user_id()

        if account_id:
            result = reconcile_account(account_id)
            result["note"] = (
                "SnapTrade transactions may take 24-48 hours to sync after execution. "
                "Recent discrepancies are expected and should resolve on the next sync."
            )
            return json.dumps(result, indent=2, default=str)
        else:
            result = reconcile_user(user_id)
            result["note"] = (
                "SnapTrade transactions may take 24-48 hours to sync after execution. "
                "Recent discrepancies are expected and should resolve on the next sync."
            )
            # Trim matched_details from per-account results to keep response concise
            for acc in result.get("results", []):
                acc.pop("matched_details", None)
            return json.dumps(result, indent=2, default=str)
