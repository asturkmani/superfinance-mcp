"""Unified holdings API routes."""

from typing import Optional

from fastapi import APIRouter, Query

from services.holdings_service import HoldingsService


router = APIRouter()


@router.get("")
async def list_all_holdings(
    user_id: Optional[str] = Query(None, description="SnapTrade user ID"),
    user_secret: Optional[str] = Query(None, description="SnapTrade user secret"),
    reporting_currency: Optional[str] = Query(None, description="Convert all values to this currency (e.g., GBP)")
):
    """
    Get unified holdings from all sources.

    Combines:
    - SnapTrade brokerage accounts
    - Manual portfolios

    Returns positions with live prices from Yahoo Finance, totals by currency,
    and optional conversion to a reporting currency.

    - **reporting_currency**: Optional currency code for unified view
    """
    return await HoldingsService.list_all_holdings(user_id, user_secret, reporting_currency)
