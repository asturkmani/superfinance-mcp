"""Consolidated classification management tool."""

import json
from typing import Optional

from helpers.classification import (
    get_known_categories,
    get_all_classifications,
    update_classification as _update_classification,
    add_category as _add_category,
)


def register_classify_v2(server):
    """Register consolidated classification tool."""

    @server.tool()
    def classify(
        action: str,
        category: Optional[str] = None,
        categories: list = None,
        updates: list = None
    ) -> str:
        """
        Manage holding classifications (categories and name mappings).

        Actions:
        - list_categories: List all available categories
        - list: List all symbol classifications (optionally filtered by category)
        - add_categories: Add new categories
        - update: Update symbol classifications (name and/or category)

        Args:
            action: Action to perform (list_categories|list|add_categories|update)
            category: Filter by category for list action
            categories: List of category names for add_categories action
            updates: List of updates for update action. Each update: {symbol, name?, category?}

        Returns:
            JSON with classification data or update results

        Examples:
            classify(action="list_categories")
            classify(action="list", category="Technology")
            classify(action="add_categories", categories=["AI Infrastructure", "Defense"])
            classify(action="update", updates=[{"symbol": "IREN", "category": "AI Infrastructure"}])
            classify(action="update", updates=[
                {"symbol": "GOOG", "name": "Google"},
                {"symbol": "GOOGL", "name": "Google"}
            ])
        """
        try:
            if action == "list_categories":
                categories_list = get_known_categories()
                return json.dumps({
                    "success": True,
                    "count": len(categories_list),
                    "categories": categories_list
                }, indent=2)

            elif action == "list":
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

            elif action == "add_categories":
                if not categories:
                    return json.dumps({"error": "categories required for add_categories action"}, indent=2)

                existing = get_known_categories()
                added = []
                already_existed = []
                failed = []

                for cat in categories:
                    if not cat or not isinstance(cat, str):
                        failed.append({"category": cat, "error": "Invalid category"})
                        continue

                    cat = cat.strip()
                    if cat in existing:
                        already_existed.append(cat)
                    elif _add_category(cat):
                        added.append(cat)
                        existing.append(cat)
                    else:
                        failed.append({"category": cat, "error": "Failed to add"})

                return json.dumps({
                    "added": added,
                    "already_existed": already_existed,
                    "failed": failed,
                    "all_categories": get_known_categories()
                }, indent=2)

            elif action == "update":
                if not updates:
                    return json.dumps({"error": "updates required for update action"}, indent=2)

                available_categories = get_known_categories()
                results = []
                new_categories = set()

                for update in updates:
                    symbol = update.get("symbol")
                    name = update.get("name")
                    cat = update.get("category")

                    if not symbol:
                        results.append({"error": "Missing symbol", "update": update})
                        continue

                    if not name and not cat:
                        results.append({
                            "error": "Must provide at least one of: name, category",
                            "symbol": symbol
                        })
                        continue

                    result = _update_classification(symbol, name, cat)

                    if result.get("success"):
                        entry = {
                            "success": True,
                            "symbol": result["symbol"],
                            "name": result["name"],
                            "category": result["category"]
                        }
                        if cat and cat not in available_categories:
                            new_categories.add(cat)
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

            else:
                return json.dumps({
                    "error": f"Invalid action: {action}",
                    "valid_actions": ["list_categories", "list", "add_categories", "update"]
                }, indent=2)

        except Exception as e:
            return json.dumps({"error": str(e)}, indent=2)
