"""Option flow CRUD tool backed by SQLite."""

import json
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Optional

from db import connect, row_to_dict
from users import current_user_token

VALID_ORDER_TYPES = {"Calls Bought", "Puts Bought", "Calls Sold", "Puts Sold"}
GLOBAL_OPTION_FLOW_TOKEN = "__global__"


def _date_minus(date_str: str, days: int) -> str:
    return (datetime.fromisoformat(str(date_str)[:10]) - timedelta(days=days)).date().isoformat()


def _month_start(date_str: str) -> str:
    return datetime.fromisoformat(str(date_str)[:10]).replace(day=1).date().isoformat()


def _leader_signal(symbol: str, side: str, snapshots: dict[str, dict[str, dict]]) -> dict[str, str | None]:
    metric = "bullish_score" if side == "bullish" else "bearish_score"
    days_metric = "bullish_days" if side == "bullish" else "bearish_days"
    day = float(snapshots.get("day", {}).get(symbol, {}).get(metric) or 0)
    week = float(snapshots.get("week", {}).get(symbol, {}).get(metric) or 0)
    month = float(snapshots.get("month", {}).get(symbol, {}).get(metric) or 0)
    quarter = float(snapshots.get("quarter", {}).get(symbol, {}).get(metric) or 0)
    week_days = int(snapshots.get("week", {}).get(symbol, {}).get(days_metric) or 0)
    month_days = int(snapshots.get("month", {}).get(symbol, {}).get(days_metric) or 0)
    quarter_days = int(snapshots.get("quarter", {}).get(symbol, {}).get(days_metric) or 0)

    signal: dict[str, str | None] = {
        "trendIcon": None,
        "trendLabel": None,
        "durationIcon": None,
        "durationLabel": None,
    }
    if day and week >= 2 and week_days >= 2:
        signal["durationIcon"] = "⚡"
        signal["durationLabel"] = "recent flow"
    elif quarter >= 8 and quarter_days >= 4 and month:
        signal["durationIcon"] = "⏳"
        signal["durationLabel"] = "long-term flow"

    day_avg = day
    week_avg = week / 7 if week else 0
    month_avg = month / 30 if month else 0
    has_consistency = week_days >= 2 or month_days >= 3 or quarter_days >= 4
    if has_consistency and day_avg >= week_avg * 1.25 and week_avg >= month_avg * 1.1 and day:
        signal["trendIcon"] = "↑"
        signal["trendLabel"] = "increasing"
    elif has_consistency and week_avg and day_avg <= week_avg * 0.5 and (not month_avg or week_avg <= month_avg * 0.9):
        signal["trendIcon"] = "↓"
        signal["trendLabel"] = "decreasing"
    elif month_days >= 3 and month_avg:
        rates = [rate for rate in (day_avg, week_avg, month_avg) if rate > 0]
        if rates and max(rates) / min(rates) <= 1.8:
            signal["trendIcon"] = "→"
            signal["trendLabel"] = "steady"
    return signal


def _week_starts_ending(latest_date: str, weeks: int = 8) -> list[datetime]:
    latest = datetime.fromisoformat(str(latest_date)[:10])
    current_week = latest - timedelta(days=latest.weekday())
    return [current_week - timedelta(days=7 * offset) for offset in range(weeks - 1, -1, -1)]


def _add_weekly_bars(c, leaders: list[dict], side: str, latest_date: str, where_base: str, base_params: list, weeks: int = 8) -> None:
    symbols = sorted({str(item.get("symbol") or "").upper() for item in leaders if item.get("symbol")})
    if not symbols:
        return
    starts = _week_starts_ending(latest_date, weeks)
    week_keys = [start.date().isoformat() for start in starts]
    placeholders = ",".join("?" for _ in symbols)
    side_sql = "order_type IN ('Calls Bought', 'Puts Sold')" if side == "bullish" else "order_type = 'Puts Bought'"
    params = [*base_params, *symbols, starts[0].date().isoformat(), str(latest_date)[:10]]
    rows = c.execute(
        f"""
        SELECT symbol, substr(trade_date, 1, 10) AS trade_day, count(*) AS rows
        FROM option_flow
        WHERE {where_base}
          AND upper(symbol) IN ({placeholders})
          AND date(trade_date) >= date(?)
          AND date(trade_date) <= date(?)
          AND {side_sql}
        GROUP BY symbol, trade_day
        """,
        params,
    ).fetchall()
    counts: dict[str, dict[str, int]] = {symbol: {} for symbol in symbols}
    for row in rows:
        traded = datetime.fromisoformat(row["trade_day"])
        week = traded - timedelta(days=traded.weekday())
        key = week.date().isoformat()
        if key in week_keys:
            symbol_key = str(row["symbol"]).upper()
            counts.setdefault(symbol_key, {})[key] = counts.setdefault(symbol_key, {}).get(key, 0) + int(row["rows"] or 0)
    for item in leaders:
        symbol_key = str(item.get("symbol") or "").upper()
        item["weeklyBars"] = [
            {
                "weekStart": key,
                "label": datetime.fromisoformat(key).strftime("%-m/%-d"),
                "trades": counts.get(symbol_key, {}).get(key, 0),
            }
            for key in week_keys
        ]


def _aggregate_period(c, key: str, label: str, start: str, end: str, latest_date: str, where_base: str, base_params: list) -> dict:
    params = [*base_params, start, end]
    where = f"{where_base} AND date(trade_date) >= date(?) AND date(trade_date) <= date(?)"
    row = c.execute(
        f"""
        SELECT count(*) AS rows, coalesce(sum(contracts), 0) AS contracts,
               min(substr(trade_date, 1, 10)) AS start_date,
               max(substr(trade_date, 1, 10)) AS end_date,
               count(DISTINCT substr(trade_date, 1, 10)) AS trading_days
        FROM option_flow
        WHERE {where}
        """,
        params,
    ).fetchone()
    by_type = [
        row_to_dict(r)
        for r in c.execute(
            f"""
            SELECT order_type, count(*) AS rows, coalesce(sum(contracts), 0) AS contracts
            FROM option_flow
            WHERE {where}
            GROUP BY order_type
            ORDER BY rows DESC
            """,
            params,
        ).fetchall()
    ]
    leaders = [
        row_to_dict(r)
        for r in c.execute(
            f"""
            SELECT upper(symbol) AS symbol,
                   coalesce(sum(CASE WHEN order_type IN ('Calls Bought', 'Puts Sold') THEN 1 ELSE 0 END), 0) AS bullish_score,
                   coalesce(sum(CASE WHEN order_type = 'Puts Bought' THEN 1 ELSE 0 END), 0) AS bearish_score,
                   coalesce(sum(CASE WHEN order_type = 'Calls Bought' THEN 1 ELSE 0 END), 0) AS calls_bought,
                   coalesce(sum(CASE WHEN order_type = 'Puts Bought' THEN 1 ELSE 0 END), 0) AS puts_bought,
                   coalesce(sum(CASE WHEN order_type = 'Puts Sold' THEN 1 ELSE 0 END), 0) AS puts_sold,
                   coalesce(sum(CASE WHEN order_type = 'Calls Sold' THEN 1 ELSE 0 END), 0) AS calls_sold,
                   count(DISTINCT CASE WHEN order_type IN ('Calls Bought', 'Puts Sold') THEN substr(trade_date, 1, 10) END) AS bullish_days,
                   count(DISTINCT CASE WHEN order_type = 'Puts Bought' THEN substr(trade_date, 1, 10) END) AS bearish_days,
                   coalesce(sum(contracts), 0) AS contracts,
                   count(*) AS rows,
                   max(substr(trade_date, 1, 10)) AS last_seen
            FROM option_flow
            WHERE {where}
            GROUP BY upper(symbol)
            HAVING bullish_score > 0 OR bearish_score > 0
            ORDER BY rows DESC
            LIMIT 200
            """,
            params,
        ).fetchall()
    ]
    top_trades = [
        row_to_dict(r)
        for r in c.execute(
            f"""
            SELECT upper(symbol) AS symbol, order_type,
                   coalesce(strike_label, strike) AS strike_label,
                   expiry, contracts, substr(trade_date, 1, 10) AS trade_date
            FROM option_flow
            WHERE {where}
            ORDER BY contracts DESC
            LIMIT 12
            """,
            params,
        ).fetchall()
    ]
    bullish = sorted((dict(x) for x in leaders), key=lambda x: (x["bullish_score"], x["rows"], x["contracts"]), reverse=True)[:20]
    bearish = sorted((dict(x) for x in leaders), key=lambda x: (x["bearish_score"], x["rows"], x["contracts"]), reverse=True)[:20]
    _add_weekly_bars(c, bullish, "bullish", latest_date, where_base, base_params)
    _add_weekly_bars(c, bearish, "bearish", latest_date, where_base, base_params)
    return {
        "key": key,
        "label": label,
        "summary": {
            "rows": row["rows"] or 0,
            "rowsLabel": f"{int(row['rows'] or 0):,}",
            "contracts": row["contracts"] or 0,
            "contractsLabel": f"{int(row['contracts'] or 0):,}",
            "startDate": row["start_date"],
            "endDate": row["end_date"],
            "tradingDays": row["trading_days"] or 0,
        },
        "byType": by_type,
        "leaders": leaders[:20],
        "bullishLeaders": bullish,
        "bearishLeaders": bearish,
        "topTrades": top_trades,
    }


def _build_aggregate(c, token: str, from_date: Optional[str], to_date: Optional[str], symbol: Optional[str]) -> dict:
    where_base = "user_token IN (?, ?)"
    base_params: list = [token, GLOBAL_OPTION_FLOW_TOKEN]
    if symbol:
        where_base += " AND upper(symbol) = ?"
        base_params.append(symbol.upper())
    latest_row = c.execute(
        f"SELECT max(substr(trade_date, 1, 10)) AS latest_date FROM option_flow WHERE {where_base}",
        base_params,
    ).fetchone()
    latest_date = latest_row["latest_date"] if latest_row else None
    if not latest_date:
        return {"success": True, "latestDate": None, "summary": {"rows": 0, "contracts": 0}, "periods": {}}

    end = (to_date or latest_date)[:10]
    day = (from_date or end)[:10] if from_date and to_date and from_date[:10] == to_date[:10] else end
    specs = [
        ("day", "Day", day, day),
        ("week", "Week", _date_minus(end, 6), end),
        ("month", "Month", _month_start(end), end),
        ("past_30_days", "Past 30 Days", _date_minus(end, 29), end),
        ("quarter", "Past Quarter", _date_minus(end, 89), end),
    ]
    periods = {
        key: _aggregate_period(c, key, label, start, stop, end, where_base, base_params)
        for key, label, start, stop in specs
    }
    snapshots = {key: {str(x.get("symbol")): x for x in period.get("leaders", [])} for key, period in periods.items()}
    for period in periods.values():
        for side, collection in (("bullish", period["bullishLeaders"]), ("bearish", period["bearishLeaders"])):
            for item in collection:
                item["signal"] = _leader_signal(item["symbol"], side, snapshots)

    day_period = periods["day"]
    week_period = periods["week"]
    month_period = periods["month"]
    quarter_period = periods["quarter"]
    week_by_symbol = {x["symbol"]: x for x in week_period.get("leaders", [])}
    month_by_symbol = {x["symbol"]: x for x in month_period.get("leaders", [])}
    quarter_by_symbol = {x["symbol"]: x for x in quarter_period.get("leaders", [])}
    momentum_ramp = []
    for symbol_key, w in list(week_by_symbol.items())[:20]:
        q = quarter_by_symbol.get(symbol_key, {})
        m = month_by_symbol.get(symbol_key, {})
        momentum_ramp.append(
            {
                "symbol": symbol_key,
                "net_per_day_7d": round((w.get("bullish_score", 0) - w.get("bearish_score", 0)) / 7, 2),
                "net_per_day_28d": round((m.get("bullish_score", 0) - m.get("bearish_score", 0)) / 30, 2),
                "net_per_day_84d": round((q.get("bullish_score", 0) - q.get("bearish_score", 0)) / 90, 2),
                "bull_ratio_7d": round(w.get("bullish_score", 0) / max(1, w.get("rows", 0)), 2),
                "gross_7d": w.get("contracts", 0),
            }
        )
    momentum_ramp.sort(key=lambda x: x["net_per_day_7d"], reverse=True)

    flow_fading = []
    for symbol_key, m in list(month_by_symbol.items())[:20]:
        w = week_by_symbol.get(symbol_key, {})
        q = quarter_by_symbol.get(symbol_key, {})
        net_7d = round((w.get("bullish_score", 0) - w.get("bearish_score", 0)) / 7, 2)
        net_30d = round((m.get("bullish_score", 0) - m.get("bearish_score", 0)) / 30, 2)
        if net_30d <= 0 or net_7d >= net_30d * 0.5:
            continue
        flow_fading.append(
            {
                "symbol": symbol_key,
                "net_per_day_7d": net_7d,
                "net_per_day_28d": net_30d,
                "net_per_day_84d": round((q.get("bullish_score", 0) - q.get("bearish_score", 0)) / 90, 2),
                "gross_30d": m.get("contracts", 0),
            }
        )
    flow_fading.sort(key=lambda x: x["net_per_day_28d"] - x["net_per_day_7d"], reverse=True)

    return {
        "success": True,
        "source": "Superfinance option_flow aggregate",
        "latestDate": end,
        "summary": day_period.get("summary", {}),
        "byType": day_period.get("byType", []),
        "topTrades": day_period.get("topTrades", []),
        "symbolTotals": day_period.get("leaders", [])[:12],
        "periods": periods,
        "defaultPeriod": "day",
        "momentumRamp": momentum_ramp[:8],
        "flowFading": flow_fading[:8],
        "longAccumulation": [
            {
                "symbol": x["symbol"],
                "score": x.get("bullish_score", 0),
                "net_contracts": x.get("contracts", 0),
                "active_days": x.get("bullish_days", 0),
                "active_weeks": sum(1 for b in x.get("weeklyBars", []) if b.get("trades")),
                "bull_week_rate": None,
                "net_gross_ratio": None,
            }
            for x in quarter_period.get("bullishLeaders", [])[:8]
        ],
        "shortBullishSlams": [
            {
                "symbol": x["symbol"],
                "short_gross": x.get("contracts", 0),
                "bull_ratio": round(x.get("bullish_score", 0) / max(1, x.get("rows", 0)), 2),
                "net": x.get("bullish_score", 0) - x.get("bearish_score", 0),
            }
            for x in day_period.get("bullishLeaders", [])
            if x.get("bullish_score", 0) >= 2 and x.get("bullish_score", 0) > x.get("bearish_score", 0)
        ][:8],
    }


def _build_signals(c, token: str, from_date: Optional[str], to_date: Optional[str], symbol: Optional[str]) -> dict:
    where_base = "user_token IN (?, ?)"
    base_params: list = [token, GLOBAL_OPTION_FLOW_TOKEN]
    if symbol:
        where_base += " AND upper(symbol) = ?"
        base_params.append(symbol.upper())
    latest_row = c.execute(
        f"SELECT max(substr(trade_date, 1, 10)) AS latest_date FROM option_flow WHERE {where_base}",
        base_params,
    ).fetchone()
    latest_date = latest_row["latest_date"] if latest_row else None
    if not latest_date:
        return {"success": True, "latestDate": None, "daily": [], "symbols": []}

    end = (to_date or latest_date)[:10]
    start = (from_date or _date_minus(end, 29))[:10]
    rows = [
        row_to_dict(r)
        for r in c.execute(
            f"""
            SELECT upper(symbol) AS symbol,
                   substr(trade_date, 1, 10) AS trade_date,
                   coalesce(sum(CASE WHEN order_type IN ('Calls Bought', 'Puts Sold') THEN 1 ELSE 0 END), 0) AS bullish_points,
                   coalesce(sum(CASE WHEN order_type = 'Puts Bought' THEN 1 ELSE 0 END), 0) AS bearish_points,
                   coalesce(sum(CASE
                       WHEN order_type IN ('Calls Bought', 'Puts Sold') THEN 1
                       WHEN order_type = 'Puts Bought' THEN -1
                       ELSE 0
                   END), 0) AS net_score,
                   coalesce(sum(CASE WHEN order_type = 'Calls Bought' THEN 1 ELSE 0 END), 0) AS calls_bought,
                   coalesce(sum(CASE WHEN order_type = 'Puts Sold' THEN 1 ELSE 0 END), 0) AS puts_sold,
                   coalesce(sum(CASE WHEN order_type = 'Puts Bought' THEN 1 ELSE 0 END), 0) AS puts_bought,
                   coalesce(sum(contracts), 0) AS contracts,
                   count(*) AS rows,
                   max(contracts) AS largest_contracts,
                   max(expiry) AS longest_expiry
            FROM option_flow
            WHERE {where_base}
              AND date(trade_date) <= date(?)
            GROUP BY upper(symbol), substr(trade_date, 1, 10)
            ORDER BY upper(symbol), substr(trade_date, 1, 10)
            """,
            [*base_params, end],
        ).fetchall()
    ]

    by_symbol: dict[str, list[dict]] = defaultdict(list)
    cumulative: dict[str, int] = defaultdict(int)
    daily: list[dict] = []
    for row in rows:
        symbol_key = row["symbol"]
        cumulative[symbol_key] += int(row["net_score"] or 0)
        item = {
            **row,
            "bullish_points": int(row["bullish_points"] or 0),
            "bearish_points": int(row["bearish_points"] or 0),
            "net_score": int(row["net_score"] or 0),
            "cumulative_net": cumulative[symbol_key],
        }
        by_symbol[symbol_key].append(item)
        if start <= item["trade_date"] <= end:
            daily.append(item)

    def window_stats(items: list[dict], days: int) -> dict:
        window_start = _date_minus(end, days - 1)
        window = [x for x in items if window_start <= x["trade_date"] <= end]
        return {
            "net": sum(int(x["net_score"] or 0) for x in window),
            "bullish_points": sum(int(x["bullish_points"] or 0) for x in window),
            "bearish_points": sum(int(x["bearish_points"] or 0) for x in window),
            "contracts": sum(int(x["contracts"] or 0) for x in window),
            "active_days": len(window),
        }

    symbols = []
    for symbol_key, items in by_symbol.items():
        latest = items[-1]
        w7 = window_stats(items, 7)
        w30 = window_stats(items, 30)
        w90 = window_stats(items, 90)
        rate_7d = w7["net"] / 7
        rate_30d = w30["net"] / 30
        state = "Noise"
        if latest["trade_date"] == end and latest["net_score"] > 0 and w30["active_days"] <= 1:
            state = "Fresh Slam"
        elif w90["net"] > 0 and w90["active_days"] >= 4 and w30["net"] > 0:
            state = "Persistent Accumulation"
        if w30["net"] > 0 and rate_7d > max(1, rate_30d * 1.5):
            state = "Acceleration"
        elif w30["net"] > 0 and rate_7d < rate_30d * 0.5:
            state = "Fading"
        elif latest["net_score"] < 0 and w30["net"] <= 0:
            state = "Bearish Reversal"

        symbols.append(
            {
                "symbol": symbol_key,
                "state": state,
                "latest_date": latest["trade_date"],
                "latest_net": latest["net_score"],
                "cumulative_net": latest["cumulative_net"],
                "day": {
                    "bullish_points": latest["bullish_points"] if latest["trade_date"] == end else 0,
                    "bearish_points": latest["bearish_points"] if latest["trade_date"] == end else 0,
                    "net": latest["net_score"] if latest["trade_date"] == end else 0,
                },
                "seven_day": w7,
                "thirty_day": w30,
                "ninety_day": w90,
            }
        )
    symbols.sort(key=lambda x: (x["cumulative_net"], x["seven_day"]["net"], x["thirty_day"]["contracts"]), reverse=True)

    return {
        "success": True,
        "source": "Superfinance option_flow signals",
        "latestDate": end,
        "fromDate": start,
        "scoring": {
            "bullish_points": "Calls Bought + Puts Sold, 1 point each",
            "bearish_points": "Puts Bought, 1 point each",
            "net_score": "bullish_points - bearish_points",
            "cumulative_net": "sum of daily net_score over time",
        },
        "daily": daily,
        "symbols": symbols[:200],
        "topBullish": symbols[:20],
        "topBearish": sorted(symbols, key=lambda x: (x["cumulative_net"], x["seven_day"]["net"]))[:20],
    }


def register_option_flow_v2(server):

    @server.tool()
    def option_flow(
        action: str,
        id: Optional[int] = None,
        symbol: Optional[str] = None,
        order_type: Optional[str] = None,
        strike: Optional[str] = None,
        expiry: Optional[str] = None,
        contracts: Optional[int] = None,
        trade_date: Optional[str] = None,
        notes: Optional[str] = None,
        source: Optional[str] = None,
        # Filters for list
        from_date: Optional[str] = None,
        to_date: Optional[str] = None,
        limit: Optional[int] = 100,
        # Bulk
        rows: Optional[str] = None,
    ) -> str:
        """
        Track and query option flow data (manual entries from sources like jamesbulltard).

        Schema mirrors the typical option flow report:
        - trade_date  (YYYY-MM-DD HH:MM, e.g. "2026-05-04 10:53")
        - order_type  ("Calls Bought" | "Puts Bought" | "Calls Sold" | "Puts Sold")
        - symbol      (e.g. "AMZN")
        - strike      (e.g. "270C", "250P", "320/370C" for spreads — kept as string)
        - expiry      (YYYY-MM-DD)
        - contracts   (int)
        - notes, source (optional)

        Actions:
        - add: Insert a single trade
        - add_bulk: Insert many trades. `rows` = JSON array of trade dicts
        - update: Update a trade by id (pass any fields to change)
        - remove: Delete a trade by id
        - get: Get a single trade by id
        - list: List trades. Filter by symbol/order_type/from_date/to_date.
        - aggregate: Full leader/period summary for canvas/digest. Optional symbol/from_date/to_date.
        - signals: Daily/cumulative directional score. Calls bought/puts sold = bullish, puts bought = bearish.
        - clear: Delete all your trades (with confirm via source="CONFIRM_DELETE_ALL")

        Examples:
            option_flow(action="add", symbol="AMZN", order_type="Calls Bought",
                        strike="270C", expiry="2026-06-05", contracts=5000,
                        trade_date="2026-05-04 10:37")
            option_flow(action="list", symbol="AMZN", limit=20)
            option_flow(action="list", from_date="2026-05-01", to_date="2026-05-04")
            option_flow(action="remove", id=42)
            option_flow(action="add_bulk", rows='[{"symbol":"AMZN","order_type":"Calls Bought","strike":"270C","expiry":"2026-06-05","contracts":5000,"trade_date":"2026-05-04 10:37"}]')
        """
        token = current_user_token.get()
        if not token:
            return json.dumps({"error": "User context required"}, indent=2)

        try:
            if action == "add":
                if (
                    not symbol
                    or not order_type
                    or not strike
                    or not expiry
                    or contracts is None
                    or not trade_date
                ):
                    return json.dumps(
                        {
                            "error": "Required: symbol, order_type, strike, expiry, contracts, trade_date",
                        },
                        indent=2,
                    )
                if order_type not in VALID_ORDER_TYPES:
                    return json.dumps(
                        {
                            "error": f"order_type must be one of: {sorted(VALID_ORDER_TYPES)}",
                        },
                        indent=2,
                    )

                with connect() as c:
                    cur = c.execute(
                        """INSERT INTO option_flow
                           (user_token, trade_date, order_type, symbol, strike, expiry, contracts, notes, source)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        (
                            token,
                            trade_date,
                            order_type,
                            symbol.upper(),
                            strike,
                            expiry,
                            int(contracts),
                            notes,
                            source or "manual",
                        ),
                    )
                    new_id = cur.lastrowid
                    row = c.execute("SELECT * FROM option_flow WHERE id = ?", (new_id,)).fetchone()
                return json.dumps({"success": True, "trade": row_to_dict(row)}, indent=2)

            elif action == "add_bulk":
                if not rows:
                    return json.dumps({"error": "rows (JSON array string) is required"}, indent=2)
                try:
                    items = json.loads(rows)
                except Exception as e:
                    return json.dumps({"error": f"rows must be valid JSON array: {e}"}, indent=2)
                if not isinstance(items, list):
                    return json.dumps({"error": "rows must be a JSON array"}, indent=2)

                inserted, errors = 0, []
                with connect() as c:
                    for i, item in enumerate(items):
                        if not isinstance(item, dict):
                            errors.append({"index": i, "error": "not an object"})
                            continue
                        ot = item.get("order_type")
                        if ot not in VALID_ORDER_TYPES:
                            errors.append({"index": i, "error": f"invalid order_type: {ot}"})
                            continue
                        try:
                            c.execute(
                                """INSERT INTO option_flow
                                   (user_token, trade_date, order_type, symbol, strike, expiry, contracts, notes, source)
                                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                                (
                                    token,
                                    item["trade_date"],
                                    ot,
                                    item["symbol"].upper(),
                                    item["strike"],
                                    item["expiry"],
                                    int(item["contracts"]),
                                    item.get("notes"),
                                    item.get("source", "manual"),
                                ),
                            )
                            inserted += 1
                        except Exception as e:
                            errors.append({"index": i, "error": str(e)})

                result = {"success": True, "inserted": inserted, "total": len(items)}
                if errors:
                    result["errors"] = errors
                return json.dumps(result, indent=2)

            elif action == "update":
                if id is None:
                    return json.dumps({"error": "id is required"}, indent=2)
                fields, params = [], []
                for col, val in [
                    ("trade_date", trade_date),
                    ("order_type", order_type),
                    ("symbol", symbol.upper() if symbol else None),
                    ("strike", strike),
                    ("expiry", expiry),
                    ("contracts", contracts),
                    ("notes", notes),
                    ("source", source),
                ]:
                    if val is not None:
                        if col == "order_type" and val not in VALID_ORDER_TYPES:
                            return json.dumps({"error": f"invalid order_type: {val}"}, indent=2)
                        fields.append(f"{col} = ?")
                        params.append(val if col != "contracts" else int(val))
                if not fields:
                    return json.dumps({"error": "no fields to update"}, indent=2)
                params.extend([id, token])

                with connect() as c:
                    cur = c.execute(
                        f"UPDATE option_flow SET {', '.join(fields)} WHERE id = ? AND user_token = ?",
                        params,
                    )
                    if cur.rowcount == 0:
                        return json.dumps({"error": f"no trade with id={id}"}, indent=2)
                    row = c.execute("SELECT * FROM option_flow WHERE id = ?", (id,)).fetchone()
                return json.dumps({"success": True, "trade": row_to_dict(row)}, indent=2)

            elif action == "remove":
                if id is None:
                    return json.dumps({"error": "id is required"}, indent=2)
                with connect() as c:
                    cur = c.execute(
                        "DELETE FROM option_flow WHERE id = ? AND user_token = ?",
                        (id, token),
                    )
                    if cur.rowcount == 0:
                        return json.dumps({"error": f"no trade with id={id}"}, indent=2)
                return json.dumps({"success": True, "removed": id}, indent=2)

            elif action == "get":
                if id is None:
                    return json.dumps({"error": "id is required"}, indent=2)
                with connect() as c:
                    row = c.execute(
                        """SELECT * FROM option_flow
                           WHERE id = ? AND user_token IN (?, ?)""",
                        (id, token, GLOBAL_OPTION_FLOW_TOKEN),
                    ).fetchone()
                if not row:
                    return json.dumps({"error": f"no trade with id={id}"}, indent=2)
                return json.dumps({"success": True, "trade": row_to_dict(row)}, indent=2)

            elif action == "list":
                where = ["user_token IN (?, ?)"]
                params = [token, GLOBAL_OPTION_FLOW_TOKEN]
                if symbol:
                    where.append("symbol = ?")
                    params.append(symbol.upper())
                if order_type:
                    if order_type not in VALID_ORDER_TYPES:
                        return json.dumps({"error": f"invalid order_type: {order_type}"}, indent=2)
                    where.append("order_type = ?")
                    params.append(order_type)
                if from_date:
                    where.append("trade_date >= ?")
                    params.append(from_date)
                if to_date:
                    where.append("trade_date <= ?")
                    params.append(to_date)

                lim = max(1, min(int(limit or 100), 1000))
                params.append(lim)
                with connect() as c:
                    rows_ = c.execute(
                        f"SELECT * FROM option_flow WHERE {' AND '.join(where)} "
                        f"ORDER BY trade_date DESC LIMIT ?",
                        params,
                    ).fetchall()
                    total = c.execute(
                        f"SELECT COUNT(*) AS n FROM option_flow WHERE {' AND '.join(where)}",
                        params[:-1],  # exclude the LIMIT param
                    ).fetchone()["n"]
                return json.dumps(
                    {
                        "success": True,
                        "count": len(rows_),
                        "total_matching": total,
                        "trades": [row_to_dict(r) for r in rows_],
                    },
                    indent=2,
                )

            elif action == "aggregate":
                with connect() as c:
                    result = _build_aggregate(c, token, from_date, to_date, symbol)
                return json.dumps(result, indent=2)

            elif action == "signals":
                with connect() as c:
                    result = _build_signals(c, token, from_date, to_date, symbol)
                return json.dumps(result, indent=2)

            elif action == "clear":
                if source != "CONFIRM_DELETE_ALL":
                    return json.dumps(
                        {
                            "error": "destructive — pass source='CONFIRM_DELETE_ALL' to confirm",
                        },
                        indent=2,
                    )
                with connect() as c:
                    cur = c.execute(
                        "DELETE FROM option_flow WHERE user_token = ?",
                        (token,),
                    )
                return json.dumps({"success": True, "deleted": cur.rowcount}, indent=2)

            else:
                return json.dumps(
                    {
                        "error": f"unknown action: {action}",
                        "valid": ["add", "add_bulk", "update", "remove", "get", "list", "aggregate", "signals", "clear"],
                    },
                    indent=2,
                )

        except Exception as e:
            return json.dumps({"error": str(e)}, indent=2)
