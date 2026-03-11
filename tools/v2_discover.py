"""Consolidated discovery tool."""

import json

from services.universe import UniverseService


def register_discover_v2(server):
    """Register consolidated discovery tool."""

    @server.tool()
    def discover(
        action: str,
        ticker: str = None,
        type: str = "equity",
        sector: str = None,
        industry: str = None,
        country: str = None,
        market_cap: str = None,
        category: str = None,
        family: str = None,
        name_search: str = None,
        limit: int = 100
    ) -> str:
        """
        Search and discover securities (stocks and ETFs).

        Actions:
        - search: Search by criteria (sector, industry, country, etc.)
        - lookup: Get full details for a specific ticker

        Args:
            action: Action to perform (search|lookup)
            ticker: Ticker symbol for lookup action (e.g., "AAPL", "SPY")
            type: Asset type for search (equity|etf|all) — default: equity
            sector: Sector name (e.g., "Technology", "Healthcare")
            industry: Industry name (e.g., "Semiconductors", "Biotechnology")
            country: Country name (e.g., "United States", "Japan")
            market_cap: Market cap category (e.g., "Large Cap", "Mid Cap")
            category: ETF category (e.g., "Equity", "Bond", "Commodity")
            family: ETF family/provider (e.g., "iShares", "Vanguard", "SPDR")
            name_search: Search term to find in name
            limit: Maximum results (default: 100)

        Returns:
            JSON with search results or ticker details

        Examples:
            discover(action="lookup", ticker="AAPL")
            discover(action="search", type="equity", sector="Technology", industry="Semiconductors")
            discover(action="search", type="etf", category="Bond")
            discover(action="search", type="etf", family="Vanguard", limit=50)
        """
        try:
            if action == "lookup":
                if not ticker:
                    return json.dumps({
                        "error": "ticker required for lookup action"
                    }, indent=2)
                result = UniverseService.lookup(ticker)
                return json.dumps(result, indent=2)

            elif action == "search":
                if type.lower() == "etf":
                    result = UniverseService.search_etfs(
                        category=category or sector,
                        family=family,
                        name_search=name_search,
                        limit=limit
                    )
                else:
                    result = UniverseService.search_equities(
                        sector=sector,
                        industry=industry,
                        country=country,
                        market_cap=market_cap,
                        limit=limit
                    )
                return json.dumps(result, indent=2)

            else:
                return json.dumps({
                    "error": f"Invalid action: {action}",
                    "valid_actions": ["search", "lookup"]
                }, indent=2)

        except Exception as e:
            return json.dumps({"error": str(e)}, indent=2)
