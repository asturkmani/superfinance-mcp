"""Tool modules for SuperFinance MCP server - Simplified."""

from db import init_db
from tools.v2_market import register_market_v2
from tools.v2_options import register_options_v2
from tools.v2_snaptrade import register_snaptrade_v2
from tools.v2_xsearch import register_xsearch_v2
from tools.v2_watchlist import register_watchlist_v2
from tools.v2_x_accounts import register_x_accounts_v2
from tools.v2_option_flow import register_option_flow_v2
from tools.v2_momentum import register_momentum_v2


def register_all_tools_v2(server):
    """Register all tools with the FastMCP server."""
    init_db()  # ensure SQLite schema exists before any tool runs
    register_market_v2(server)
    register_options_v2(server)
    register_snaptrade_v2(server)
    register_xsearch_v2(server)
    register_watchlist_v2(server)
    register_x_accounts_v2(server)
    register_option_flow_v2(server)
    register_momentum_v2(server)


__all__ = ["register_all_tools_v2"]
