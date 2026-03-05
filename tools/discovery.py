"""Discovery tools - search and lookup securities via FinanceDatabase."""

import json
from services.universe import UniverseService


def register_discovery_tools(server):
    """Register FinanceDatabase discovery tools."""
    
    @server.tool()
    def search_securities(
        sector: str = None,
        industry: str = None,
        country: str = None,
        market_cap: str = None,
        asset_class: str = "equities",
        limit: int = 100
    ) -> str:
        """
        Search equities or ETFs by sector, industry, country.
        
        Args:
            sector: Sector name (e.g., "Technology", "Healthcare")
            industry: Industry name (e.g., "Semiconductors", "Biotechnology")
            country: Country name (e.g., "United States", "Japan")
            market_cap: Market cap category (e.g., "Large Cap", "Mid Cap", "Small Cap")
            asset_class: "equities" or "etfs" (default: "equities")
            limit: Maximum number of results (default: 100)
            
        Returns:
            JSON string with search results
            
        Examples:
            - Search for semiconductor companies: sector="Technology", industry="Semiconductors"
            - Search for large cap US tech: sector="Technology", country="United States", market_cap="Large Cap"
            - Search for healthcare ETFs: asset_class="etfs", sector="Healthcare"
        """
        try:
            if asset_class.lower() == "etfs":
                # For ETFs, category is like sector
                result = UniverseService.search_etfs(
                    category=sector,
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
            
        except Exception as e:
            return json.dumps({"error": str(e)})
    
    @server.tool()
    def lookup_security(ticker: str) -> str:
        """
        Get full details for a ticker symbol.
        
        Args:
            ticker: Stock or ETF ticker symbol (e.g., "AAPL", "SPY")
            
        Returns:
            JSON string with ticker details including:
            - name: Company/fund name
            - sector: Business sector
            - industry: Specific industry
            - country: Country of domicile
            - market_cap: Market capitalization category
            - asset_class: "equity" or "etf"
            
        Examples:
            - Get Apple info: ticker="AAPL"
            - Get S&P 500 ETF info: ticker="SPY"
        """
        try:
            result = UniverseService.lookup(ticker)
            return json.dumps(result, indent=2)
            
        except Exception as e:
            return json.dumps({"error": str(e)})
    
    @server.tool()
    def search_etfs(
        category: str = None,
        family: str = None,
        name_search: str = None,
        limit: int = 100
    ) -> str:
        """
        Search ETFs by category, family, or name.
        
        Args:
            category: ETF category (e.g., "Equity", "Bond", "Commodity", "Currency")
            family: ETF family/provider (e.g., "iShares", "Vanguard", "SPDR")
            name_search: Search term to find in ETF name
            limit: Maximum number of results (default: 100)
            
        Returns:
            JSON string with ETF search results
            
        Examples:
            - Find Vanguard ETFs: family="Vanguard"
            - Find bond ETFs: category="Bond"
            - Find S&P 500 ETFs: name_search="S&P 500"
            - Find iShares equity ETFs: family="iShares", category="Equity"
        """
        try:
            result = UniverseService.search_etfs(
                category=category,
                family=family,
                name_search=name_search,
                limit=limit
            )
            
            return json.dumps(result, indent=2)
            
        except Exception as e:
            return json.dumps({"error": str(e)})
