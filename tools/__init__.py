"""Tool modules for SuperFinance MCP server."""

from tools.yahoo_finance import register_yahoo_finance_tools
from tools.portfolios import register_portfolio_tools
from tools.holdings import register_holdings_tools
from tools.visualization import register_visualization_tools
from tools.cache_tools import register_cache_tools


def register_all_tools(server):
    """Register all tools with the FastMCP server."""
    # Market data
    register_yahoo_finance_tools(server)

    # Unified portfolio management (manual + synced brokerages)
    register_portfolio_tools(server)

    # Aggregate holdings view
    register_holdings_tools(server)

    # Unified visualization (portfolio dashboard + price charts)
    register_visualization_tools(server)

    # Cache management
    register_cache_tools(server)


__all__ = ["register_all_tools"]
