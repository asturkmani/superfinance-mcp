"""Option flow CRUD tool backed by SQLite."""

import json
from typing import Optional

from db import connect, row_to_dict
from users import current_user_token

VALID_ORDER_TYPES = {"Calls Bought", "Puts Bought", "Calls Sold", "Puts Sold"}
GLOBAL_OPTION_FLOW_TOKEN = "__global__"


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
                        "valid": ["add", "add_bulk", "update", "remove", "get", "list", "clear"],
                    },
                    indent=2,
                )

        except Exception as e:
            return json.dumps({"error": str(e)}, indent=2)
