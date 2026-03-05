"""FinanceDatabase service - search and lookup securities."""

import financedatabase as fd
import pandas as pd
from typing import Optional


class UniverseService:
    """Search and lookup securities from FinanceDatabase."""
    
    _equities = None
    _etfs = None
    
    @classmethod
    def _get_equities(cls):
        """Lazy-load equities database."""
        if cls._equities is None:
            cls._equities = fd.Equities()
        return cls._equities
    
    @classmethod
    def _get_etfs(cls):
        """Lazy-load ETFs database."""
        if cls._etfs is None:
            cls._etfs = fd.ETFs()
        return cls._etfs
    
    @staticmethod
    def search_equities(
        sector: Optional[str] = None,
        industry: Optional[str] = None,
        country: Optional[str] = None,
        market_cap: Optional[str] = None,
        limit: int = 100
    ) -> list:
        """
        Search equities by sector, industry, country, market cap.
        
        Args:
            sector: Sector name (e.g., "Technology")
            industry: Industry name (e.g., "Semiconductors")
            country: Country code (e.g., "United States")
            market_cap: Market cap category (e.g., "Large Cap", "Mid Cap", "Small Cap")
            limit: Maximum number of results (default 100)
            
        Returns:
            list of dicts with equity data
        """
        try:
            equities = UniverseService._get_equities()
            
            # Build search criteria
            kwargs = {}
            if sector:
                kwargs['sector'] = sector
            if industry:
                kwargs['industry'] = industry
            if country:
                kwargs['country'] = country
            if market_cap:
                kwargs['market_cap'] = market_cap
            
            # Search returns a DataFrame
            result_df = equities.search(**kwargs) if kwargs else equities.select()
            
            if result_df is None or result_df.empty:
                return []
            
            # Convert to list of dicts, limit results
            result_df = result_df.head(limit)
            
            # Reset index to get ticker as a column
            result_df = result_df.reset_index()
            
            # Convert to dict, handling NaN values
            result = result_df.to_dict(orient='records')
            
            # Replace NaN with None for JSON serialization
            for record in result:
                for key, value in record.items():
                    if pd.isna(value):
                        record[key] = None
            
            return result
            
        except Exception as e:
            return [{"error": f"Search failed: {str(e)}"}]
    
    @staticmethod
    def search_etfs(
        category: Optional[str] = None,
        family: Optional[str] = None,
        name_search: Optional[str] = None,
        limit: int = 100
    ) -> list:
        """
        Search ETFs by category, family, or name.
        
        Args:
            category: ETF category (e.g., "Equity", "Bond", "Commodity")
            family: ETF family/provider (e.g., "iShares", "Vanguard")
            name_search: Search in ETF name
            limit: Maximum number of results (default 100)
            
        Returns:
            list of dicts with ETF data
        """
        try:
            etfs = UniverseService._get_etfs()
            
            # Build search criteria
            kwargs = {}
            if category:
                kwargs['category'] = category
            if family:
                kwargs['family'] = family
            
            # Search returns a DataFrame
            result_df = etfs.search(**kwargs) if kwargs else etfs.select()
            
            if result_df is None or result_df.empty:
                return []
            
            # Filter by name if provided
            if name_search and not result_df.empty:
                # Search in the 'name' column if it exists
                if 'name' in result_df.columns:
                    mask = result_df['name'].str.contains(name_search, case=False, na=False)
                    result_df = result_df[mask]
            
            # Limit results
            result_df = result_df.head(limit)
            
            # Reset index to get ticker as a column
            result_df = result_df.reset_index()
            
            # Convert to dict, handling NaN values
            result = result_df.to_dict(orient='records')
            
            # Replace NaN with None for JSON serialization
            for record in result:
                for key, value in record.items():
                    if pd.isna(value):
                        record[key] = None
            
            return result
            
        except Exception as e:
            return [{"error": f"ETF search failed: {str(e)}"}]
    
    @staticmethod
    def lookup(ticker: str) -> dict:
        """
        Get full details for a ticker (name, sector, industry, country, etc.).
        
        Args:
            ticker: Ticker symbol (e.g., "AAPL")
            
        Returns:
            dict with ticker details
        """
        try:
            ticker = ticker.upper().strip()
            
            # Try equities first
            equities = UniverseService._get_equities()
            equity_data = equities.select()  # Get all equities
            
            if ticker in equity_data.index:
                result = equity_data.loc[ticker].to_dict()
                result['symbol'] = ticker
                result['asset_class'] = 'equity'
                
                # Replace NaN with None
                for key, value in result.items():
                    if pd.isna(value):
                        result[key] = None
                
                return result
            
            # Try ETFs
            etfs = UniverseService._get_etfs()
            etf_data = etfs.select()  # Get all ETFs
            
            if ticker in etf_data.index:
                result = etf_data.loc[ticker].to_dict()
                result['symbol'] = ticker
                result['asset_class'] = 'etf'
                
                # Replace NaN with None
                for key, value in result.items():
                    if pd.isna(value):
                        result[key] = None
                
                return result
            
            return {"error": f"Ticker {ticker} not found in FinanceDatabase"}
            
        except Exception as e:
            return {"error": f"Lookup failed: {str(e)}"}
