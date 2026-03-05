"""Manual portfolio tools - SQLite-backed portfolio management."""

import json
from typing import Optional

from services.portfolio_service import PortfolioService
from db import queries
from helpers.user_context import get_current_user_id


def register_manual_portfolio_tools(server):
    """Register all manual portfolio tools with the server."""

    @server.tool()
    async def manual_create_portfolio(
        portfolio_id: str,
        name: str,
        description: Optional[str] = None,
        user_id: Optional[str] = None
    ) -> str:
        """
        Create a new manual portfolio for tracking private investments.

        Use this for investments not connected through SnapTrade, such as:
        - Private equity (SpaceX, Stripe, etc.)
        - Real estate investments
        - Angel investments
        - Other alternative assets

        Args:
            portfolio_id: Unique identifier for the portfolio (e.g., "private-equity", "real-estate")
            name: Display name for the portfolio (e.g., "Private Equity Holdings")
            description: Optional description of the portfolio
            user_id: Optional user ID (uses default user if not provided)

        Returns:
            JSON string confirming portfolio creation
        """
        if not user_id:
            user_id = get_current_user_id()
        
        result = await PortfolioService.create_portfolio(
            user_id=user_id,
            portfolio_id=portfolio_id,
            name=name,
            description=description
        )
        
        return json.dumps(result, indent=2)

    @server.tool()
    async def manual_add_position(
        portfolio_id: str,
        name: str,
        units: float,
        average_cost: float,
        currency: str = "USD",
        symbol: Optional[str] = None,
        manual_price: Optional[float] = None,
        asset_type: Optional[str] = None,
        notes: Optional[str] = None,
        user_id: Optional[str] = None
    ) -> str:
        """
        Add a position to a manual portfolio.

        For pricing, you can specify:
        - A Yahoo Finance symbol (e.g., "STRB" for SpaceX exposure) for live prices
        - A manual_price if there's no ticker available

        Args:
            portfolio_id: The portfolio to add the position to
            name: Display name for the position (e.g., "SpaceX Series J")
            units: Number of shares/units held
            average_cost: Average cost per unit in the specified currency
            currency: Currency code (e.g., "USD", "GBP", "EUR"). Default: "USD"
            symbol: Optional Yahoo Finance ticker symbol for live pricing
            manual_price: Optional manual price if no ticker is available
            asset_type: Optional category (e.g., "private_equity", "real_estate", "crypto")
            notes: Optional notes about the position
            user_id: Optional user ID (uses default user if not provided)

        Returns:
            JSON string confirming position was added
        """
        if not user_id:
            user_id = get_current_user_id()
        
        result = await PortfolioService.add_position(
            user_id=user_id,
            portfolio_id=portfolio_id,
            name=name,
            units=units,
            average_cost=average_cost,
            currency=currency,
            symbol=symbol,
            manual_price=manual_price,
            asset_type=asset_type,
            notes=notes
        )
        
        return json.dumps(result, indent=2)

    @server.tool()
    async def manual_update_position(
        portfolio_id: str,
        position_id: str,
        units: Optional[float] = None,
        average_cost: Optional[float] = None,
        manual_price: Optional[float] = None,
        symbol: Optional[str] = None,
        name: Optional[str] = None,
        notes: Optional[str] = None,
        user_id: Optional[str] = None
    ) -> str:
        """
        Update an existing position in a manual portfolio.

        Only the fields you provide will be updated; others remain unchanged.

        Args:
            portfolio_id: The portfolio containing the position
            position_id: The ID of the position to update (from manual_add_position)
            units: New number of units (optional)
            average_cost: New average cost per unit (optional)
            manual_price: New manual price override (optional, set to 0 to clear)
            symbol: New Yahoo Finance symbol (optional, set to empty string to clear)
            name: New display name (optional)
            notes: New notes (optional)
            user_id: Optional user ID (uses default user if not provided)

        Returns:
            JSON string confirming the update
        """
        if not user_id:
            user_id = get_current_user_id()
        
        result = await PortfolioService.update_position(
            user_id=user_id,
            portfolio_id=portfolio_id,
            position_id=position_id,
            units=units,
            average_cost=average_cost,
            manual_price=manual_price,
            symbol=symbol,
            name=name,
            notes=notes
        )
        
        return json.dumps(result, indent=2)

    @server.tool()
    async def manual_remove_position(
        portfolio_id: str,
        position_id: str,
        user_id: Optional[str] = None
    ) -> str:
        """
        Remove a position from a manual portfolio.

        Args:
            portfolio_id: The portfolio containing the position
            position_id: The ID of the position to remove
            user_id: Optional user ID (uses default user if not provided)

        Returns:
            JSON string confirming removal
        """
        if not user_id:
            user_id = get_current_user_id()
        
        result = await PortfolioService.remove_position(
            user_id=user_id,
            portfolio_id=portfolio_id,
            position_id=position_id
        )
        
        return json.dumps(result, indent=2)

    @server.tool()
    async def manual_delete_portfolio(
        portfolio_id: str,
        user_id: Optional[str] = None
    ) -> str:
        """
        Delete an entire manual portfolio and all its positions.

        WARNING: This is irreversible! All positions in the portfolio will be deleted.

        Args:
            portfolio_id: The portfolio to delete
            user_id: Optional user ID (uses default user if not provided)

        Returns:
            JSON string confirming deletion
        """
        if not user_id:
            user_id = get_current_user_id()
        
        result = await PortfolioService.delete_portfolio(
            user_id=user_id,
            portfolio_id=portfolio_id
        )
        
        return json.dumps(result, indent=2)

    @server.tool()
    async def manual_list_portfolios(
        user_id: Optional[str] = None
    ) -> str:
        """
        List all manual portfolios with summaries.

        Args:
            user_id: Optional user ID (uses default user if not provided)

        Returns:
            JSON string with list of portfolios and their summaries
        """
        if not user_id:
            user_id = get_current_user_id()
        
        result = await PortfolioService.list_portfolios(user_id=user_id)
        
        return json.dumps(result, indent=2)

    @server.tool()
    async def manual_get_portfolio(
        portfolio_id: str,
        target_currency: Optional[str] = None,
        user_id: Optional[str] = None
    ) -> str:
        """
        Get detailed view of a manual portfolio with live prices.

        Args:
            portfolio_id: The portfolio to retrieve
            target_currency: Optional currency for conversion (e.g., "GBP")
            user_id: Optional user ID (uses default user if not provided)

        Returns:
            JSON string with portfolio details and current valuations
        """
        if not user_id:
            user_id = get_current_user_id()
        
        result = await PortfolioService.get_portfolio(
            user_id=user_id,
            portfolio_id=portfolio_id,
            target_currency=target_currency
        )
        
        return json.dumps(result, indent=2)
