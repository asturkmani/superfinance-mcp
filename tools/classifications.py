"""Classification management tools."""

import json
from typing import Optional

from helpers.classification import (
    get_classification,
    get_known_categories,
    get_all_classifications,
    update_classification as _update_classification,
    add_category as _add_category,
)


def register_classification_tools(server):
    """Register classification tools with the server."""

    @server.tool()
    def list_categories() -> str:
        """
        List all available categories for classifying holdings.

        Categories are used to group holdings by investment theme/sector.
        Use update_classification() to change a holding's category.

        Returns:
            JSON with list of categories
        """
        categories = get_known_categories()
        return json.dumps({
            "success": True,
            "count": len(categories),
            "categories": categories
        }, indent=2)

    @server.tool()
    def list_classifications(
        category: Optional[str] = None
    ) -> str:
        """
        List all symbol classifications (name and category mappings).

        Shows how symbols are grouped and categorized. Use update_classification()
        to change any mapping.

        Args:
            category: Optional filter by category (e.g., "Technology", "Commodities")

        Returns:
            JSON with all classifications
        """
        data = get_all_classifications()
        tickers = data.get("tickers", {})

        # Filter by category if specified
        if category:
            tickers = {
                symbol: info
                for symbol, info in tickers.items()
                if info.get("category", "").lower() == category.lower()
            }

        # Sort by category then name
        sorted_tickers = dict(sorted(
            tickers.items(),
            key=lambda x: (x[1].get("category", ""), x[1].get("name", ""))
        ))

        return json.dumps({
            "success": True,
            "categories": data.get("categories", []),
            "count": len(sorted_tickers),
            "filter": category,
            "classifications": sorted_tickers
        }, indent=2)

    @server.tool()
    def update_classifications(
        updates: list[dict]
    ) -> str:
        """
        Update classifications (name and/or category) for one or more symbols.

        This overrides AI-generated classifications. Use this to:
        - Group related tickers under a common name (e.g., GOOG + GOOGL -> "Google")
        - Change a holding's category (e.g., IREN from "Crypto" to "AI Infrastructure")
        - Batch update multiple symbols at once

        Args:
            updates: List of updates, each with: symbol (required), name (optional), category (optional)

        Returns:
            JSON with results for each update

        Examples:
            update_classifications(updates=[{"symbol": "IREN", "category": "AI Infrastructure"}])
            update_classifications(updates=[
                {"symbol": "GOOG", "name": "Google", "category": "Technology"},
                {"symbol": "GOOGL", "name": "Google", "category": "Technology"}
            ])
        """
        if not updates:
            return json.dumps({"error": "No updates provided"}, indent=2)

        available_categories = get_known_categories()
        results = []
        new_categories = set()

        for update in updates:
            symbol = update.get("symbol")
            name = update.get("name")
            category = update.get("category")

            if not symbol:
                results.append({"error": "Missing symbol", "update": update})
                continue

            if not name and not category:
                results.append({
                    "error": "Must provide at least one of: name, category",
                    "symbol": symbol
                })
                continue

            result = _update_classification(symbol, name, category)

            if result.get("success"):
                entry = {
                    "success": True,
                    "symbol": result["symbol"],
                    "name": result["name"],
                    "category": result["category"]
                }
                if category and category not in available_categories:
                    new_categories.add(category)
                results.append(entry)
            else:
                results.append({"success": False, "symbol": symbol, "error": result.get("error")})

        response = {
            "updated": len([r for r in results if r.get("success")]),
            "failed": len([r for r in results if not r.get("success")]),
            "results": results
        }

        if new_categories:
            response["new_categories"] = list(new_categories)

        return json.dumps(response, indent=2)

    @server.tool()
    def add_categories(categories: list[str]) -> str:
        """
        Add one or more new categories to the available categories list.

        Categories are used to group holdings by investment theme/sector.
        New categories are also automatically created when using update_classifications().

        Args:
            categories: List of category names (e.g., ["AI Infrastructure", "Defense"])

        Returns:
            JSON confirming which categories were added

        Examples:
            add_categories(categories=["AI Infrastructure"])
            add_categories(categories=["Defense", "Space", "Biotech"])
        """
        if not categories:
            return json.dumps({"error": "No categories provided"}, indent=2)

        existing = get_known_categories()
        added = []
        already_existed = []
        failed = []

        for category in categories:
            if not category or not isinstance(category, str):
                failed.append({"category": category, "error": "Invalid category"})
                continue

            category = category.strip()
            if category in existing:
                already_existed.append(category)
            elif _add_category(category):
                added.append(category)
                existing.append(category)  # Update local list
            else:
                failed.append({"category": category, "error": "Failed to add"})

        return json.dumps({
            "added": added,
            "already_existed": already_existed,
            "failed": failed,
            "all_categories": get_known_categories()
        }, indent=2)
