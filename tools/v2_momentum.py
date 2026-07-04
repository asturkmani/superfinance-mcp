"""Finviz-backed momentum scans for groups, stocks, and themes."""

import json
from typing import Optional
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from finvizfinance.group.performance import Performance as GroupPerf
from finvizfinance.screener.performance import Performance as StockPerf


GROUP_OPTIONS = {"Industry", "Sector"}
MARKET_CAP_OPTIONS = {"all", "large", "mid", "small", "micro", "nano"}
SORT_BY_OPTIONS = {"score", "perf_week", "perf_month", "perf_quarter", "perf_half", "perf_year"}
THEME_LEVEL_OPTIONS = {"top", "subtheme", "all"}
THEME_SORT_BY_OPTIONS = {"score", "perf_week", "perf_month", "perf_quarter", "acceleration"}

MARKET_CAP_FILTERS = {
    "all": None,
    "large": "+Large (over $10bln)",
    "mid": "Mid ($2bln to $10bln)",
    "small": "Small ($300mln to $2bln)",
    "micro": "Micro ($50mln to $300mln)",
    "nano": "Nano (under $50mln)",
}

THEME_INTERVALS = {
    "perf_week": "w1",
    "perf_month": "w4",
    "perf_quarter": "w13",
}

THEME_GROUP_PREFIXES = [
    ("cybersecurity", "Cybersecurity"),
    ("transportation", "Transportation & Logistics"),
    ("environmental", "Environmental Sustainability"),
    ("energyclean", "Energy Renewable"),
    ("energybase", "Energy Traditional"),
    ("commenergy", "Commodities Energy"),
    ("commmetals", "Commodities Metals"),
    ("commagri", "Commodities Agriculture"),
    ("agriculture", "Agriculture & FoodTech"),
    ("healthcare", "Healthcare & Biotech"),
    ("longevity", "Aging Population & Longevity"),
    ("nutrition", "Healthy Food & Nutrition"),
    ("blockchain", "Crypto & Blockchain"),
    ("automation", "Industrial Automation"),
    ("autonomous", "Autonomous Systems"),
    ("entertainment", "Digital Entertainment"),
    ("realestate", "Real Estate & REITs"),
    ("smarthome", "Smart Home"),
    ("wearables", "Wearables"),
    ("education", "Education Technology"),
    ("biometrics", "Biometrics"),
    ("nanotech", "Nanotechnology"),
    ("ecommerce", "E-commerce"),
    ("software", "Software"),
    ("hardware", "Hardware"),
    ("quantum", "Quantum Computing"),
    ("vareality", "Virtual & Augmented Reality"),
    ("bigdata", "Big Data"),
    ("defense", "Defense & Aerospace"),
    ("telecom", "Telecommunications"),
    ("fintech", "FinTech"),
    ("robotics", "Robotics"),
    ("space", "Space Tech"),
    ("cloud", "Cloud Computing"),
    ("semis", "Semiconductors"),
    ("evs", "Electric Vehicles"),
    ("social", "Social Media"),
    ("iot", "Internet of Things"),
    ("ai", "Artificial Intelligence"),
    ("consumer", "Consumer Goods"),
]

THEME_LABEL_OVERRIDES = {
    "aicompute": "AI Compute",
    "aicloud": "AI Cloud",
    "aimodels": "AI Models",
    "aidata": "AI Data",
    "aienterprise": "AI Enterprise",
    "ainetworking": "AI Networking",
    "aisecurity": "AI Security",
    "aiedge": "AI Edge",
    "airobotics": "AI Robotics",
    "aiapplications": "AI Applications",
    "aiadssearch": "AI Ads/Search",
    "aienergy": "AI Energy",
    "aiagi": "AI AGI",
    "semiscompute": "Semis Compute",
    "semismemory": "Semis Memory",
    "semisanalog": "Semis Analog",
    "semiswireless": "Semis Wireless",
    "semisfoundries": "Semis Foundries",
    "semisdesigntools": "Semis Design Tools",
    "semislithography": "Semis Lithography",
    "semispackaging": "Semis Packaging",
    "semisnextgen": "Semis Next Gen",
    "commmetalsgold": "Gold",
    "commmetalssilver": "Silver",
    "commmetalsprecious": "Precious Metals",
    "commmetalsindustrial": "Industrial Metals",
    "commmetalsbattery": "Battery Metals",
    "commmetalsrareearth": "Rare Earths",
    "commmetalsrecycling": "Metals Recycling",
    "commenergyoil": "Oil",
    "commenergygaslng": "Gas/LNG",
    "commenergyuranium": "Uranium",
    "commenergybiofuels": "Biofuels",
    "spacelaunch": "Space Launch",
    "spacesatellites": "Space Satellites",
    "spacedataanalytics": "Space Data Analytics",
    "spacedefense": "Space Defense",
    "spaceinfrastructure": "Space Infrastructure",
    "defensedrones": "Defense Drones",
    "defensemissiles": "Defense Missiles",
    "defensespacetech": "Defense Space Tech",
    "defensecyberdefense": "Defense Cyberdefense",
    "defenseweapons": "Defense Weapons",
    "defenseaviation": "Defense Aviation",
    "defensemanufacturing": "Defense Manufacturing",
    "healthcareoncology": "Healthcare Oncology",
    "healthcaremetabolic": "Healthcare Metabolic",
    "healthcarediagnostics": "Healthcare Diagnostics",
    "healthcaregenomics": "Healthcare Genomics",
    "healthcaredevices": "Healthcare Devices",
    "healthcaretelemedicine": "Healthcare Telemedicine",
    "healthcareitdata": "Healthcare IT/Data",
    "healthcaretherapeutics": "Healthcare Therapeutics",
    "fintechpayments": "FinTech Payments",
    "fintechtrading": "FinTech Trading",
    "fintechexchanges": "FinTech Exchanges",
    "blockchaininfrastructure": "Blockchain Infrastructure",
    "blockchainmining": "Blockchain Mining",
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


def _group_score(
    perf_month: float, perf_quarter: float, perf_half: float, perf_year: float
) -> float:
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


def _theme_group_for_node(node: str) -> tuple[str, str, str]:
    for prefix, label in THEME_GROUP_PREFIXES:
        if node.startswith(prefix):
            return prefix, label, node[len(prefix) :]
    return "other", "Other", node


def _theme_label(node: str) -> str:
    if node in THEME_LABEL_OVERRIDES:
        return THEME_LABEL_OVERRIDES[node]
    _, group_label, suffix = _theme_group_for_node(node)
    suffix = suffix.replace("hsaas", "horizontal SaaS").replace("vsaas", "vertical SaaS")
    suffix = suffix.replace("paas", "PaaS").replace("iam", "IAM").replace("siem", "SIEM")
    suffix = suffix.replace("iot", "IoT").replace("av", "AV")
    words = []
    current = ""
    for char in suffix:
        if char.isupper() and current:
            words.append(current)
            current = char
        else:
            current += char
    if current:
        words.append(current)
    suffix_label = " ".join(words).strip().title()
    return f"{group_label} {suffix_label}".strip()


def _fetch_theme_perf(st: str) -> dict:
    query = urlencode({"t": "themes", "st": st})
    req = Request(
        f"https://finviz.com/api/map_perf?{query}",
        headers={
            "User-Agent": "Mozilla/5.0",
            "Referer": "https://finviz.com/map?t=themes",
        },
    )
    with urlopen(req, timeout=20) as response:
        return json.loads(response.read().decode("utf-8"))


def _theme_score(perf_week: float, perf_month: float, perf_quarter: float) -> float:
    acceleration = perf_week - (perf_month / 4)
    return perf_week * 0.35 + perf_month * 0.30 + perf_quarter * 0.25 + acceleration * 0.10


def _build_theme_item(
    *,
    key: str,
    name: str,
    level: str,
    nodes: list[str],
    perf_data: dict[str, dict],
) -> dict:
    def avg(field: str) -> float:
        vals = [float(perf_data[field]["nodes"].get(node, 0) or 0) for node in nodes]
        return sum(vals) / len(vals) if vals else 0.0

    perf_week = avg("perf_week")
    perf_month = avg("perf_month")
    perf_quarter = avg("perf_quarter")
    acceleration = perf_week - (perf_month / 4)
    score = _theme_score(perf_week, perf_month, perf_quarter)
    item = {
        "key": key,
        "name": name,
        "level": level,
        "perf_week": round(perf_week, 2),
        "perf_month": round(perf_month, 2),
        "perf_quarter": round(perf_quarter, 2),
        "acceleration": round(acceleration, 2),
        "score": round(score, 2),
    }
    if level == "top":
        item["subtheme_count"] = len(nodes)
    else:
        _, group_label, _ = _theme_group_for_node(key)
        item["top_theme"] = group_label
    return item


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
    def momentum_theme_scan(
        level: str = "all",
        limit: int = 30,
        sort_by: str = "score",
        descending: bool = True,
    ) -> str:
        """
        Rank Finviz theme-map momentum across top-level themes and subthemes.

        Finviz exposes this data as current/live map performance only. The tool pulls
        1-week, 1-month, and 3-month theme performance and derives top-level theme
        rollups by averaging their child subthemes.

        Recommended baseline settings:
        - level="all" for Rolling Bubble Radar.
        - sort_by="score" for blended momentum + acceleration.
        - limit=20 to 50.

        Args:
            level: Select one of "top", "subtheme", or "all".
            limit: Number of rows to return (1-300).
            sort_by: One of "score", "perf_week", "perf_month", "perf_quarter", "acceleration".
            descending: Sort order.
        """
        if level not in THEME_LEVEL_OPTIONS:
            return json.dumps(
                {
                    "error": f"Invalid level: {level}",
                    "valid_level_options": sorted(THEME_LEVEL_OPTIONS),
                },
                indent=2,
            )
        if sort_by not in THEME_SORT_BY_OPTIONS:
            return json.dumps(
                {
                    "error": f"Invalid sort_by: {sort_by}",
                    "valid_sort_options": sorted(THEME_SORT_BY_OPTIONS),
                },
                indent=2,
            )

        lim = max(1, min(int(limit), 300))
        try:
            perf_data = {field: _fetch_theme_perf(st) for field, st in THEME_INTERVALS.items()}
            node_names = sorted(perf_data["perf_week"].get("nodes", {}).keys())
            top_nodes: dict[str, dict] = {}
            for node in node_names:
                prefix, group_label, _ = _theme_group_for_node(node)
                top_nodes.setdefault(prefix, {"name": group_label, "nodes": []})["nodes"].append(
                    node
                )

            items = []
            if level in {"top", "all"}:
                for prefix, group in top_nodes.items():
                    if prefix == "other":
                        continue
                    items.append(
                        _build_theme_item(
                            key=prefix,
                            name=group["name"],
                            level="top",
                            nodes=group["nodes"],
                            perf_data=perf_data,
                        )
                    )
            if level in {"subtheme", "all"}:
                for node in node_names:
                    items.append(
                        _build_theme_item(
                            key=node,
                            name=_theme_label(node),
                            level="subtheme",
                            nodes=[node],
                            perf_data=perf_data,
                        )
                    )

            ranked = sorted(items, key=lambda x: x.get(sort_by, 0), reverse=descending)[:lim]
            return json.dumps(
                {
                    "success": True,
                    "source": "Finviz themes map /api/map_perf?t=themes",
                    "historical_support": False,
                    "note": "Finviz appears to return current/live theme momentum only; store daily snapshots for backtesting.",
                    "level": level,
                    "sort_by": sort_by,
                    "descending": descending,
                    "count": len(ranked),
                    "items": ranked,
                    "recommended_defaults": {
                        "level": "all",
                        "limit": 30,
                        "sort_by": "score",
                        "descending": True,
                    },
                    "valid_level_options": sorted(THEME_LEVEL_OPTIONS),
                    "valid_sort_options": sorted(THEME_SORT_BY_OPTIONS),
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
            filters["Price"] = (
                f"Over ${int(min_price) if float(min_price).is_integer() else min_price}"
            )
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
