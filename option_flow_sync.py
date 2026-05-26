"""Admin ingestion for syncing local option-flow rows into Fly SQLite."""

from __future__ import annotations

import hashlib
import json
import os
import re
from typing import Any

from starlette.requests import Request
from starlette.responses import JSONResponse

from db import connect

VALID_ORDER_TYPES = {"Calls Bought", "Puts Bought", "Calls Sold", "Puts Sold"}
GLOBAL_OPTION_FLOW_TOKEN = "__global__"


SYNC_COLUMNS = [
    "trade_datetime",
    "trade_date",
    "order_type",
    "action",
    "symbol",
    "strike",
    "option_type",
    "strike_label",
    "expiry",
    "contracts",
    "premium",
    "premium_usd",
    "notes",
    "source",
    "source_page",
    "raw_json",
    "imported_at",
    "sync_key",
]


def _json_or_none(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        # Keep strings as-is; local exporter sends compact JSON strings for raw_json.
        return value
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _numeric_value(value: Any) -> float | None:
    if value in (None, ""):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if not isinstance(value, str):
        return None
    cleaned = value.strip().replace("$", "").replace(",", "")
    match = re.fullmatch(r"([+-]?\d+(?:\.\d+)?)([kKmMbB]?)", cleaned)
    if not match:
        return None
    multiplier = {"": 1.0, "K": 1_000.0, "M": 1_000_000.0, "B": 1_000_000_000.0}
    return float(match.group(1)) * multiplier[match.group(2).upper()]


def _premium_usd(row: dict[str, Any]) -> float | None:
    direct = _numeric_value(row.get("premium_usd"))
    if direct is not None:
        return direct
    direct = _numeric_value(row.get("premium"))
    if direct is not None:
        return direct
    raw_json = row.get("raw_json")
    if isinstance(raw_json, str):
        try:
            raw_json = json.loads(raw_json)
        except Exception:
            raw_json = None
    if isinstance(raw_json, dict):
        for key in (
            "premium_usd",
            "total_premium_usd",
            "premium",
            "total_premium",
            "cost",
            "amount",
            "value",
            "notional",
        ):
            parsed = _numeric_value(raw_json.get(key))
            if parsed is not None:
                return parsed
    return None


def _make_sync_key(row: dict[str, Any]) -> str:
    if row.get("sync_key"):
        return str(row["sync_key"])
    if row.get("local_id") is not None:
        raw = f"{row.get('source') or 'manual'}\x1flocal_id\x1f{row['local_id']}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    # Stable natural key. Includes source so different feeds don't collide.
    # Deliberately excludes mutable annotations/size fields so corrected rows
    # update instead of duplicating.
    parts = [
        row.get("source") or "manual",
        row.get("trade_datetime") or row.get("trade_date") or "",
        row.get("trade_date") or "",
        row.get("order_type") or "",
        str(row.get("symbol") or "").upper(),
        str(row.get("strike") or ""),
        row.get("option_type") or "",
        row.get("strike_label") or "",
        row.get("expiry") or "",
    ]
    raw = "\x1f".join(parts)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _normalize_row(row: dict[str, Any]) -> dict[str, Any]:
    required = ["trade_date", "order_type", "symbol", "strike", "expiry", "contracts"]
    missing = [k for k in required if row.get(k) in (None, "")]
    if missing:
        raise ValueError(f"missing required fields: {', '.join(missing)}")

    order_type = str(row["order_type"])
    if order_type not in VALID_ORDER_TYPES:
        raise ValueError(f"invalid order_type: {order_type}")

    normalized = {
        "trade_datetime": row.get("trade_datetime") or row.get("trade_date"),
        "trade_date": str(row["trade_date"]),
        "order_type": order_type,
        "action": row.get("action"),
        "symbol": str(row["symbol"]).upper(),
        "strike": str(row["strike"]),
        "option_type": row.get("option_type"),
        "strike_label": row.get("strike_label"),
        "expiry": str(row["expiry"]),
        "contracts": int(row["contracts"]),
        "premium": row.get("premium"),
        "premium_usd": _premium_usd(row),
        "notes": row.get("notes"),
        "source": row.get("source") or "sync",
        "source_page": row.get("source_page"),
        "raw_json": _json_or_none(row.get("raw_json")),
        "imported_at": row.get("imported_at"),
    }
    normalized["sync_key"] = _make_sync_key({**row, **normalized})
    return normalized


def upsert_option_flow_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Insert/update shared option-flow rows visible to every MCP user.

    Synced market data lives under a reserved global namespace. Personal/manual
    rows remain user-scoped in the MCP tool.
    """
    user_token = GLOBAL_OPTION_FLOW_TOKEN
    if not isinstance(rows, list):
        raise ValueError("rows must be a list")

    inserted = 0
    updated = 0
    errors: list[dict[str, Any]] = []

    assignments = ", ".join(f"{col}=excluded.{col}" for col in SYNC_COLUMNS if col != "sync_key")
    placeholders = ", ".join(["?"] * (1 + len(SYNC_COLUMNS)))
    columns = ", ".join(["user_token", *SYNC_COLUMNS])

    with connect() as c:
        for idx, row in enumerate(rows):
            if not isinstance(row, dict):
                errors.append({"index": idx, "error": "row must be an object"})
                continue
            try:
                normalized = _normalize_row(row)
                existed = (
                    c.execute(
                        "SELECT 1 FROM option_flow WHERE user_token = ? AND sync_key = ?",
                        (user_token, normalized["sync_key"]),
                    ).fetchone()
                    is not None
                )
                values = [user_token] + [normalized.get(col) for col in SYNC_COLUMNS]
                c.execute(
                    f"""
                    INSERT INTO option_flow ({columns})
                    VALUES ({placeholders})
                    ON CONFLICT(user_token, sync_key) DO UPDATE SET
                        {assignments}
                    """,
                    values,
                )
                if existed:
                    updated += 1
                else:
                    inserted += 1
            except Exception as e:  # keep bulk sync resilient
                errors.append({"index": idx, "error": str(e)})

    return {"received": len(rows), "inserted": inserted, "updated": updated, "errors": errors}


async def option_flow_sync_handler(request: Request):
    """POST /admin/option-flow/sync protected by OPTION_FLOW_SYNC_TOKEN."""
    expected = os.getenv("OPTION_FLOW_SYNC_TOKEN")
    auth = request.headers.get("authorization", "")
    if not expected or auth != f"Bearer {expected}":
        return JSONResponse({"error": "unauthorized"}, status_code=401)

    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON body"}, status_code=400)

    rows = body.get("rows")
    if not isinstance(rows, list):
        return JSONResponse({"error": "rows must be an array"}, status_code=400)

    try:
        result = upsert_option_flow_rows(rows)
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    return JSONResponse(result)
