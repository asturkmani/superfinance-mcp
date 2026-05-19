"""Finviz-backed momentum scans for groups and stocks."""

import json
from typing import Optional

from finvizfinance.group.performance import Performance as GroupPerf
from finvizfinance.screener.performance import Performance as StockPerf


GROUP_OPTIONS = {"Industry", "Sector"}
MARKET_CAP_OPTIONS = {"all", "large", "mid", "small", "micro", "nano"}
SORT_BY_OPTIONS = {"score", "perf_week", "perf_month", "perf_quarter", "perf_half", "perf_year"}

MARKET_CAP_FILTERS = {
    "all": None,
    "large": "+Large (over $10bln)",
    "mid": "Mid ($2bln to $10bln)",
    "small": "Small ($300mln to $2bln)",
    "micro": "Micro ($50mln to $300mln)",
    "nano": "Nano (under $50mln)",
}


def _to_pct(value) -> float:
    if value is None:
        return 0.0
    if isinstance(value, str):
        v = value.strip().replace("%", "")
        if not v or v == "-":
            return 0.0
        try:
            return float(v)
        except ValueError:
            return 0.0
    try:
        return float(value) * 100
    except Exception:
        return 0.0


def _group_score(perf_month: float, perf_quarter: float, perf_half: float, perf_year: float) -> float:
    # Leadership-weighted score with quarter and half-year carrying most weight.
    return perf_month * 0.20 + perf_quarter * 0.40 + perf_half * 0.25 + perf_year * 0.15


def _acceleration_flag(perf_month: float, perf_quarter: float) -> str:
    month_ann = perf_month * 12
    quarter_ann = perf_quarter * 4
    if perf_quarter > 0 and month_ann > quarter_ann:
        return "accelerating"
    if perf_quarter > 5 and month_ann < quarter_ann * 0.5:
        return "decelerating"
    return "stable"


def _sort_items(items: list[dict], sort_by: str, descending: bool) -> list[dict]:
    key_map = {
        "score": "score",
        "perf_week": "perf_week",
        "perf_month": "perf_month",
        "perf_quarter": "perf_quarter",
        "perf_half": "perf_half",
        "perf_year": "perf_year",
    }
    key = key_map[sort_by]
    return sorted(items, key=lambda x: x.get(key, 0), reverse=descending)


def register_momentum_v2(server):

    @server.tool()
    def momentum_group_scan(
        group: str = "Industry",
        limit: int = 20,
        sort_by: str = "score",
        descending: bool = True,
    ) -> str:
        """
        Rank Finviz groups (industry/sector) by momentum.

        Recommended baseline settings:
        - group="Industry" for idea generation; use group="Sector" for macro context.
        - sort_by="score" and descending=True.
        - limit=10 to 20.

        Args:
            group: Select one of "Industry" or "Sector".
            limit: Number of rows to return (1-100).
            sort_by: One of "score", "perf_week", "perf_month", "perf_quarter", "perf_half", "perf_year".
            descending: Sort order.
        """
        if group not in GROUP_OPTIONS:
            return json.dumps(
                {
                    "error": f"Invalid group: {group}",
                    "valid_group_options": sorted(GROUP_OPTIONS),
                },
                indent=2,
            )
        if sort_by not in SORT_BY_OPTIONS:
            return json.dumps(
                {
                    "error": f"Invalid sort_by: {sort_by}",
                    "valid_sort_options": sorted(SORT_BY_OPTIONS),
                },
                indent=2,
            )

        lim = max(1, min(int(limit), 100))
        try:
            df = GroupPerf().screener_view(group=group, order="Performance (Quarter)")
            items = []
            for _, row in df.iterrows():
                perf_week = _to_pct(row.get("Perf Week"))
                perf_month = _to_pct(row.get("Perf Month"))
                perf_quarter = _to_pct(row.get("Perf Quart"))
                perf_half = _to_pct(row.get("Perf Half"))
                perf_year = _to_pct(row.get("Perf Year"))
                perf_ytd = _to_pct(row.get("Perf YTD"))
                score = _group_score(perf_month, perf_quarter, perf_half, perf_year)
                items.append(
                    {
                        "name": row.get("Name"),
                        "perf_week": round(perf_week, 2),
                        "perf_month": round(perf_month, 2),
                        "perf_quarter": round(perf_quarter, 2),
                        "perf_half": round(perf_half, 2),
                        "perf_year": round(perf_year, 2),
                        "perf_ytd": round(perf_ytd, 2),
                        "score": round(score, 2),
                        "acceleration_flag": _acceleration_flag(perf_month, perf_quarter),
                    }
                )
            ranked = _sort_items(items, sort_by=sort_by, descending=descending)[:lim]
            return json.dumps(
                {
                    "success": True,
                    "group": group,
                    "sort_by": sort_by,
                    "descending": descending,
                    "count": len(ranked),
                    "items": ranked,
                    "recommended_defaults": {
                        "group": "Industry",
                        "limit": 15,
                        "sort_by": "score",
                        "descending": True,
                    },
                    "valid_group_options": sorted(GROUP_OPTIONS),
                    "valid_sort_options": sorted(SORT_BY_OPTIONS),
                },
                indent=2,
            )
        except Exception as e:
            return json.dumps({"error": str(e)}, indent=2)

    @server.tool()
    def momentum_stock_scan(
        industry: Optional[str] = None,
        sector: Optional[str] = None,
        market_cap: str = "large",
        min_price: float = 5.0,
        min_avg_volume: int = 500_000,
        limit: int = 20,
        sort_by: str = "score",
        descending: bool = True,
    ) -> str:
        """
        Scan stock leaders within a Finviz industry/sector.

        Recommended baseline settings:
        - market_cap="large" (or "mid") for liquidity and execution quality.
        - min_price=5, min_avg_volume=500000.
        - pass exactly one of industry or sector.

        Args:
            industry: Finviz industry label (e.g. "Oil & Gas Drilling").
            sector: Finviz sector label (e.g. "Energy").
            market_cap: Select one of "all", "large", "mid", "small", "micro", "nano".
            min_price: Minimum stock price.
            min_avg_volume: Minimum average daily volume.
            limit: Number of rows to return (1-100).
            sort_by: One of "score", "perf_week", "perf_month", "perf_quarter", "perf_half", "perf_year".
            descending: Sort order.
        """
        if (industry and sector) or (not industry and not sector):
            return json.dumps(
                {"error": "Provide exactly one filter: industry or sector"},
                indent=2,
            )
        if market_cap not in MARKET_CAP_OPTIONS:
            return json.dumps(
                {
                    "error": f"Invalid market_cap: {market_cap}",
                    "valid_market_cap_options": sorted(MARKET_CAP_OPTIONS),
                },
                indent=2,
            )
        if sort_by not in SORT_BY_OPTIONS:
            return json.dumps(
                {
                    "error": f"Invalid sort_by: {sort_by}",
                    "valid_sort_options": sorted(SORT_BY_OPTIONS),
                },
                indent=2,
            )

        lim = max(1, min(int(limit), 100))
        filters = {}
        if industry:
            filters["Industry"] = industry
        if sector:
            filters["Sector"] = sector

        cap_filter = MARKET_CAP_FILTERS[market_cap]
        if cap_filter:
            filters["Market Cap."] = cap_filter
        if min_price > 0:
            filters["Price"] = f"Over ${int(min_price) if float(min_price).is_integer() else min_price}"
        if min_avg_volume > 0:
            if min_avg_volume >= 1_000_000:
                filters["Average Volume"] = f"Over {int(min_avg_volume / 1_000_000)}M"
            else:
                filters["Average Volume"] = f"Over {int(min_avg_volume / 1_000)}K"

        try:
            perf = StockPerf()
            perf.set_filter(filters_dict=filters)
            df = perf.screener_view()
            items = []
            for _, row in df.iterrows():
                perf_week = _to_pct(row.get("Perf Week"))
                perf_month = _to_pct(row.get("Perf Month"))
                perf_quarter = _to_pct(row.get("Perf Quart"))
                perf_half = _to_pct(row.get("Perf Half"))
                perf_year = _to_pct(row.get("Perf Year"))
                score = _group_score(perf_month, perf_quarter, perf_half, perf_year)
                items.append(
                    {
                        "ticker": row.get("Ticker"),
                        "price": float(row.get("Price") or 0),
                        "avg_volume": float(row.get("Avg Volume") or 0),
                        "perf_week": round(perf_week, 2),
                        "perf_month": round(perf_month, 2),
                        "perf_quarter": round(perf_quarter, 2),
                        "perf_half": round(perf_half, 2),
                        "perf_year": round(perf_year, 2),
                        "score": round(score, 2),
                    }
                )

            ranked = _sort_items(items, sort_by=sort_by, descending=descending)[:lim]
            return json.dumps(
                {
                    "success": True,
                    "filters_applied": filters,
                    "sort_by": sort_by,
                    "descending": descending,
                    "count": len(ranked),
                    "items": ranked,
                    "recommended_defaults": {
                        "market_cap": "large",
                        "min_price": 5.0,
                        "min_avg_volume": 500000,
                        "limit": 15,
                        "sort_by": "score",
                        "descending": True,
                    },
                    "valid_market_cap_options": sorted(MARKET_CAP_OPTIONS),
                    "valid_sort_options": sorted(SORT_BY_OPTIONS),
                },
                indent=2,
            )
        except Exception as e:
            return json.dumps({"error": str(e)}, indent=2)
