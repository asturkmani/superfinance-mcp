#!/usr/bin/env python3
"""Sync local JBT option-flow SQLite rows into deployed SuperFinance MCP.

Environment:
  LOCAL_OPTIONS_DB              default: /root/clawd/research/optionslib/options.db
  SUPERFINANCE_SYNC_URL         e.g. https://superfinance-mcp.fly.dev/admin/option-flow/sync
  SUPERFINANCE_SYNC_TOKEN       admin bearer token matching OPTION_FLOW_SYNC_TOKEN on Fly

Examples:
  SUPERFINANCE_SYNC_URL=https://superfinance-mcp.fly.dev/admin/option-flow/sync \
  SUPERFINANCE_SYNC_TOKEN=... \
    uv run python scripts/sync_option_flow_to_fly.py --from-date 2026-05-01
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Iterable

DEFAULT_LOCAL_DB = "/root/clawd/research/optionslib/options.db"
DEFAULT_SYNC_URL = "https://superfinance-mcp.fly.dev/admin/option-flow/sync"


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--db", default=os.getenv("LOCAL_OPTIONS_DB", DEFAULT_LOCAL_DB))
    p.add_argument("--url", default=os.getenv("SUPERFINANCE_SYNC_URL", DEFAULT_SYNC_URL))
    p.add_argument("--token", default=os.getenv("SUPERFINANCE_SYNC_TOKEN"))
    p.add_argument("--from-date", help="Only sync trade_date >= YYYY-MM-DD")
    p.add_argument("--to-date", help="Only sync trade_date <= YYYY-MM-DD")
    p.add_argument("--symbol", action="append", help="Symbol filter; repeatable")
    p.add_argument("--batch-size", type=int, default=500)
    p.add_argument("--dry-run", action="store_true")
    return p.parse_args()


def _row_to_payload(row: sqlite3.Row) -> dict[str, Any]:
    strike_label = row["strike_label"]
    if not strike_label and row["strike"] is not None and row["option_type"]:
        strike_label = f"{row['strike']:g}{row['option_type']}"

    raw_json = row["raw_json"]
    # Keep valid JSON compact if present; otherwise pass through as a string.
    if raw_json:
        try:
            raw_json = json.dumps(json.loads(raw_json), separators=(",", ":"), sort_keys=True)
        except Exception:
            pass

    return {
        "local_id": row["id"],
        "trade_datetime": row["trade_datetime"],
        "trade_date": row["trade_date"],
        "order_type": row["order_type"],
        "action": row["action"],
        "symbol": row["symbol"],
        "strike": row["strike"],
        "option_type": row["option_type"],
        "strike_label": strike_label,
        "expiry": row["expiry"],
        "contracts": row["contracts"],
        "source": row["source"] or "jamesbulltard",
        "source_page": row["source_page"],
        "raw_json": raw_json,
        "imported_at": row["imported_at"],
    }


def iter_rows(
    db_path: str, from_date: str | None, to_date: str | None, symbols: list[str] | None
) -> Iterable[dict[str, Any]]:
    if not Path(db_path).exists():
        raise SystemExit(f"Local DB not found: {db_path}")

    where = []
    params: list[Any] = []
    if from_date:
        where.append("trade_date >= ?")
        params.append(from_date)
    if to_date:
        where.append("trade_date <= ?")
        params.append(to_date)
    if symbols:
        placeholders = ",".join("?" for _ in symbols)
        where.append(f"upper(symbol) IN ({placeholders})")
        params.extend(s.upper() for s in symbols)

    sql = """
        SELECT id, trade_datetime, trade_date, order_type, action, symbol, strike,
               option_type, strike_label, expiry, contracts, source, source_page,
               raw_json, imported_at
        FROM option_flow_trades
    """
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY trade_date, id"

    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    try:
        for row in con.execute(sql, params):
            yield _row_to_payload(row)
    finally:
        con.close()


def post_batch(url: str, token: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
    body: dict[str, Any] = {"rows": rows}
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {e.code}: {detail}") from e


def main() -> int:
    args = parse_args()
    if not args.token and not args.dry_run:
        print("SUPERFINANCE_SYNC_TOKEN/--token is required", file=sys.stderr)
        return 2
    if args.batch_size < 1 or args.batch_size > 5000:
        print("--batch-size must be 1..5000", file=sys.stderr)
        return 2

    total = inserted = updated = errors = 0
    batch: list[dict[str, Any]] = []

    def flush() -> None:
        nonlocal batch, inserted, updated, errors
        if not batch:
            return
        if args.dry_run:
            print(f"DRY RUN: would post {len(batch)} rows to {args.url}")
        else:
            result = post_batch(args.url, args.token, batch)
            inserted += int(result.get("inserted", 0))
            updated += int(result.get("updated", 0))
            errors += len(result.get("errors", []))
            if result.get("errors"):
                print(
                    json.dumps({"batch_errors": result["errors"][:10]}, indent=2), file=sys.stderr
                )
            print(json.dumps(result, sort_keys=True))
        batch = []

    for row in iter_rows(args.db, args.from_date, args.to_date, args.symbol):
        total += 1
        batch.append(row)
        if len(batch) >= args.batch_size:
            flush()
    flush()

    print(
        json.dumps(
            {
                "selected": total,
                "inserted": inserted,
                "updated": updated,
                "errors": errors,
                "dry_run": args.dry_run,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
