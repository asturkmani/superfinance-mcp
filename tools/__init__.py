"""Tool modules for SuperFinance MCP server."""

from tools.yahoo_finance import register_yahoo_finance_tools
from tools.snaptrade import register_snaptrade_tools
from tools.holdings import register_holdings_tools
from tools.manual_portfolio import register_manual_portfolio_tools
from tools.cache_tools import register_cache_tools
from tools.charts import register_chart_tools


def register_all_tools(server):
    """Register all tools with the FastMCP server."""
    register_yahoo_finance_tools(server)
    register_snaptrade_tools(server)
    register_holdings_tools(server)
    register_manual_portfolio_tools(server)
    register_cache_tools(server)
    register_chart_tools(server)


__all__ = ["register_all_tools"]
