"""Tool modules for SuperFinance MCP server."""

from tools.yahoo_finance import register_yahoo_finance_tools
from tools.portfolios import register_portfolio_tools
from tools.holdings import register_holdings_tools
from tools.visualization import register_visualization_tools
from tools.cache_tools import register_cache_tools
from tools.reconciliation import register_reconciliation_tools
from tools.accounts import register_account_tools
from tools.discovery import register_discovery_tools
from tools.analysis import register_analysis_tools
from tools.dashboards import register_dashboard_tools


def register_all_tools(server):
    """Register all tools with the FastMCP server."""
    # Market data
    register_yahoo_finance_tools(server)

    # Discovery and analytics (FinanceDatabase + FinanceToolkit)
    register_discovery_tools(server)
    register_analysis_tools(server)

    # Unified portfolio management (manual + synced brokerages)
    register_portfolio_tools(server)

    # Aggregate holdings view
    register_holdings_tools(server)

    # Unified visualization (portfolio dashboard + price charts)
    register_visualization_tools(server)

    # Dashboard management (saved views with widgets)
    register_dashboard_tools(server)

    # Cache management
    register_cache_tools(server)

    # Reconciliation
    register_reconciliation_tools(server)

    # Account/Holdings/Transaction CRUD
    register_account_tools(server)


__all__ = ["register_all_tools"]
