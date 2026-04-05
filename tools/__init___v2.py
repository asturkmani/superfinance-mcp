"""Tool modules for SuperFinance MCP server - Simplified."""

from tools.v2_market import register_market_v2
from tools.v2_options import register_options_v2
from tools.v2_snaptrade import register_snaptrade_v2


def register_all_tools_v2(server):
    """Register all tools with the FastMCP server."""
    register_market_v2(server)
    register_options_v2(server)
    register_snaptrade_v2(server)


__all__ = ["register_all_tools_v2"]
