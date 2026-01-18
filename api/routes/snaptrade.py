"""SnapTrade brokerage API routes."""

from typing import Optional

from fastapi import APIRouter, Query
from pydantic import BaseModel

from services.snaptrade_service import SnapTradeService


router = APIRouter()


class RegisterUserRequest(BaseModel):
    """Request body for user registration."""
    user_id: Optional[str] = None


@router.post("/users")
async def register_user(request: RegisterUserRequest):
    """
    Register a new SnapTrade user.

    Returns user_id and user_secret. **IMPORTANT**: Save the user_secret!
    """
    return await SnapTradeService.register_user(request.user_id)


@router.get("/connection-url")
async def get_connection_url(
    user_id: Optional[str] = Query(None, description="SnapTrade user ID"),
    user_secret: Optional[str] = Query(None, description="SnapTrade user secret")
):
    """
    Get URL for connecting a brokerage account.

    The user must visit this URL to authenticate with their brokerage.
    """
    return await SnapTradeService.get_connection_url(user_id, user_secret)


@router.get("/accounts")
async def list_accounts(
    user_id: Optional[str] = Query(None, description="SnapTrade user ID"),
    user_secret: Optional[str] = Query(None, description="SnapTrade user secret")
):
    """
    List all connected brokerage accounts.

    Returns account IDs, names, institutions, and balances.
    """
    return await SnapTradeService.list_accounts(user_id, user_secret)


@router.get("/accounts/{account_id}/holdings")
async def get_holdings(
    account_id: str,
    user_id: Optional[str] = Query(None, description="SnapTrade user ID"),
    user_secret: Optional[str] = Query(None, description="SnapTrade user secret")
):
    """
    Get holdings for a specific account.

    - **account_id**: The account UUID from /accounts endpoint
    """
    return await SnapTradeService.get_holdings(account_id, user_id, user_secret)


@router.get("/accounts/{account_id}/transactions")
async def get_transactions(
    account_id: str,
    start_date: str = Query(..., description="Start date (YYYY-MM-DD)"),
    end_date: str = Query(..., description="End date (YYYY-MM-DD)"),
    user_id: Optional[str] = Query(None, description="SnapTrade user ID"),
    user_secret: Optional[str] = Query(None, description="SnapTrade user secret"),
    transaction_type: Optional[str] = Query(None, description="Filter by type (e.g., BUY,SELL,DIVIDEND)")
):
    """
    Get transaction history for an account.

    - **account_id**: The account UUID
    - **start_date**: Start date (YYYY-MM-DD)
    - **end_date**: End date (YYYY-MM-DD)
    - **transaction_type**: Optional filter
    """
    return await SnapTradeService.get_transactions(
        account_id, start_date, end_date, user_id, user_secret, transaction_type
    )


@router.delete("/authorizations/{authorization_id}")
async def disconnect_account(
    authorization_id: str,
    user_id: Optional[str] = Query(None, description="SnapTrade user ID"),
    user_secret: Optional[str] = Query(None, description="SnapTrade user secret")
):
    """
    Disconnect a brokerage connection.

    **WARNING**: This is irreversible! All associated data will be removed.

    - **authorization_id**: The brokerage_authorization from /accounts
    """
    return await SnapTradeService.disconnect_account(authorization_id, user_id, user_secret)


@router.post("/authorizations/{authorization_id}/refresh")
async def refresh_account(
    authorization_id: str,
    user_id: Optional[str] = Query(None, description="SnapTrade user ID"),
    user_secret: Optional[str] = Query(None, description="SnapTrade user secret")
):
    """
    Trigger a manual refresh of holdings data.

    - **authorization_id**: The brokerage_authorization from /accounts

    Note: May incur additional charges depending on your SnapTrade plan.
    """
    return await SnapTradeService.refresh_account(authorization_id, user_id, user_secret)
