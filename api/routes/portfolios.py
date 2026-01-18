"""Manual portfolio API routes."""

from typing import Optional

from fastapi import APIRouter, Query
from pydantic import BaseModel

from services.portfolio_service import PortfolioService


router = APIRouter()


class CreatePortfolioRequest(BaseModel):
    """Request body for creating a portfolio."""
    portfolio_id: str
    name: str
    description: Optional[str] = None


class AddPositionRequest(BaseModel):
    """Request body for adding a position."""
    name: str
    units: float
    average_cost: float
    currency: str = "USD"
    symbol: Optional[str] = None
    manual_price: Optional[float] = None
    asset_type: Optional[str] = None
    notes: Optional[str] = None


class UpdatePositionRequest(BaseModel):
    """Request body for updating a position."""
    units: Optional[float] = None
    average_cost: Optional[float] = None
    manual_price: Optional[float] = None
    symbol: Optional[str] = None
    name: Optional[str] = None
    notes: Optional[str] = None


@router.get("")
async def list_portfolios():
    """
    List all manual portfolios with summaries.

    Returns portfolio IDs, names, position counts, and total cost basis.
    """
    return await PortfolioService.list_portfolios()


@router.post("")
async def create_portfolio(request: CreatePortfolioRequest):
    """
    Create a new manual portfolio.

    Use for tracking investments not in connected brokerages:
    - Private equity (SpaceX, Stripe, etc.)
    - Real estate investments
    - Angel investments
    - Other alternative assets
    """
    return await PortfolioService.create_portfolio(
        request.portfolio_id,
        request.name,
        request.description
    )


@router.get("/{portfolio_id}")
async def get_portfolio(
    portfolio_id: str,
    target_currency: Optional[str] = Query(None, description="Convert all values to this currency")
):
    """
    Get a portfolio with live prices.

    Fetches current prices from Yahoo Finance for positions with symbols,
    uses manual_price for positions without symbols.

    - **portfolio_id**: The portfolio identifier
    - **target_currency**: Optional currency for conversion
    """
    return await PortfolioService.get_portfolio(portfolio_id, target_currency)


@router.delete("/{portfolio_id}")
async def delete_portfolio(portfolio_id: str):
    """
    Delete a portfolio and all its positions.

    **WARNING**: This is irreversible!

    - **portfolio_id**: The portfolio to delete
    """
    return await PortfolioService.delete_portfolio(portfolio_id)


@router.post("/{portfolio_id}/positions")
async def add_position(portfolio_id: str, request: AddPositionRequest):
    """
    Add a position to a portfolio.

    For pricing, you can specify:
    - A Yahoo Finance symbol for live prices
    - A manual_price if no ticker is available

    - **portfolio_id**: Target portfolio
    """
    return await PortfolioService.add_position(
        portfolio_id,
        request.name,
        request.units,
        request.average_cost,
        request.currency,
        request.symbol,
        request.manual_price,
        request.asset_type,
        request.notes
    )


@router.put("/{portfolio_id}/positions/{position_id}")
async def update_position(
    portfolio_id: str,
    position_id: str,
    request: UpdatePositionRequest
):
    """
    Update a position in a portfolio.

    Only provided fields will be updated.

    - **portfolio_id**: Target portfolio
    - **position_id**: Position to update
    """
    return await PortfolioService.update_position(
        portfolio_id,
        position_id,
        request.units,
        request.average_cost,
        request.manual_price,
        request.symbol,
        request.name,
        request.notes
    )


@router.delete("/{portfolio_id}/positions/{position_id}")
async def remove_position(portfolio_id: str, position_id: str):
    """
    Remove a position from a portfolio.

    - **portfolio_id**: Target portfolio
    - **position_id**: Position to remove
    """
    return await PortfolioService.remove_position(portfolio_id, position_id)
