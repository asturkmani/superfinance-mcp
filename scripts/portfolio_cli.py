#!/usr/bin/env python3
"""Portfolio CLI backed by the Superfinance portfolio tool.

This keeps the old local holdings.py json/summary/accounts/themes/all
interface available while making Superfinance the portfolio source of truth.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from fastmcp import FastMCP

ROOT = Path(__file__).resolve().parents[1]
LEGACY_MANUAL_FILE = Path(
    os.getenv(
        "LEGACY_PORTFOLIO_MANUAL_FILE",
        "/root/clawd/skills/portfolio/data/manual_portfolios.json",
    )
)
LEGACY_THEMES_FILE = Path(
    os.getenv(
        "LEGACY_PORTFOLIO_THEMES_FILE",
        "/root/clawd/skills/portfolio/data/themes.json",
    )
)

os.environ.setdefault("DATA_DIR", str(ROOT / ".data"))
load_dotenv(ROOT / ".env")

sys.path.insert(0, str(ROOT))

from tools.v2_snaptrade import register_snaptrade_v2  # noqa: E402
from users import current_user_token, load_users, save_users  # noqa: E402


def _tool_fn():
    server = FastMCP("portfolio-cli")
    register_snaptrade_v2(server)
    for tool in server._tool_manager._tools.values():
        if tool.name == "portfolio":
            return tool.fn
    raise RuntimeError("Superfinance portfolio tool not found")


def _load_legacy_manual() -> list[dict[str, Any]]:
    if not LEGACY_MANUAL_FILE.exists():
        return []
    data = json.loads(LEGACY_MANUAL_FILE.read_text())
    holdings = []
    for portfolio in data.get("portfolios", []):
        account_name = portfolio.get("name") or "Manual"
        for idx, pos in enumerate(portfolio.get("positions", []), start=1):
            name = pos.get("name") or pos.get("symbol") or f"Manual holding {idx}"
            notes = pos.get("notes")
            asset_type = pos.get("asset_type")
            if asset_type:
                notes = f"{asset_type}: {notes}" if notes else asset_type
            holdings.append(
                {
                    "id": f"legacy{len(holdings) + 1:02d}",
                    "symbol": pos.get("symbol"),
                    "description": name,
                    "units": float(pos.get("units") or 1),
                    "currency": (pos.get("currency") or "USD").upper(),
                    "cost_price": float(pos.get("cost_basis") or 0) or None,
                    "additional_cost": float(pos.get("additional_cost") or 0) or None,
                    "manual_price": (
                        float(pos["price"])
                        if pos.get("price") is not None
                        else None
                    ),
                    "account_name": account_name,
                    "notes": notes,
                }
            )
    return holdings


def _ensure_local_user() -> str:
    """Ensure local Superfinance storage has Abudi's env creds and legacy manual assets."""
    token = os.getenv("SUPERFINANCE_USER_TOKEN", "local-abudi")
    users = load_users()
    user = users.get(token, {})

    user.update(
        {
            "email": user.get("email") or "abudi.local",
            "snaptrade_user_id": os.getenv("SNAPTRADE_USER_ID"),
            "snaptrade_user_secret": os.getenv("SNAPTRADE_USER_SECRET"),
            "base_currency": user.get("base_currency") or os.getenv("BASE_CURRENCY", "USD"),
        }
    )

    if not user.get("manual_holdings"):
        legacy_manual = _load_legacy_manual()
        if legacy_manual:
            user["manual_holdings"] = legacy_manual

    users[token] = user
    save_users(users)
    return token


def _load_theme_map() -> tuple[dict[str, dict], dict[str, str]]:
    if not LEGACY_THEMES_FILE.exists():
        return {}, {}
    try:
        data = json.loads(LEGACY_THEMES_FILE.read_text())
    except Exception:
        return {}, {}
    themes = data.get("themes", {})
    ticker_to_theme: dict[str, str] = {}
    for name, meta in themes.items():
        for ticker in meta.get("holdings", []):
            ticker_to_theme[ticker] = name
    ticker_to_theme.update(data.get("options_mapping", {}))
    return themes, ticker_to_theme


def _base_pnl(item: dict[str, Any]) -> float | None:
    if item.get("cost_basis") is None:
        return None
    fx = item.get("fx_rate") or 1.0
    cost_base = float(item.get("cost_basis") or 0) * fx
    value_base = float(item.get("market_value_base") or 0)
    if not cost_base:
        return None
    return round(value_base - cost_base, 2)


def _position(
    *,
    symbol: str | None,
    name: str | None,
    qty: float,
    price: float,
    currency: str,
    value: float,
    cost_basis: float,
    pnl: float | None,
    theme: str,
    account: str,
    kind: str,
    source: str,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    pnl_pct = round((pnl / cost_basis) * 100, 2) if pnl is not None and cost_basis else None
    data = {
        "symbol": symbol,
        "name": name or symbol,
        "qty": qty,
        "price_local": round(price or 0, 4),
        "currency_local": currency,
        "cost_basis": round(cost_basis or 0, 2),
        "market_value": round(value or 0, 2),
        "pnl": pnl,
        "pnl_pct": pnl_pct,
        "theme": theme,
        "account": account,
        "type": kind,
        "source": source,
        "price_source": "superfinance",
    }
    if extra:
        data.update(extra)
    return data


def legacy_json() -> dict[str, Any]:
    token = _ensure_local_user()
    tok = current_user_token.set(token)
    try:
        raw = json.loads(_tool_fn()(action="overview"))
    finally:
        current_user_token.reset(tok)

    if raw.get("error"):
        raise RuntimeError(raw["error"])

    themes, ticker_to_theme = _load_theme_map()
    positions: list[dict[str, Any]] = []

    for account in raw.get("accounts", []):
        account_name = (
            (account.get("account") or {}).get("name")
            or (account.get("account") or {}).get("institution")
            or "Brokerage"
        )

        for p in account.get("positions", []):
            symbol = p.get("symbol")
            fx = p.get("fx_rate") or 1.0
            cost_base = float(p.get("cost_basis") or 0) * fx
            positions.append(
                _position(
                    symbol=symbol,
                    name=p.get("description"),
                    qty=float(p.get("units") or 0),
                    price=float(p.get("current_price") or 0),
                    currency=p.get("currency") or raw.get("base_currency", "USD"),
                    value=float(p.get("market_value_base") or 0),
                    cost_basis=cost_base,
                    pnl=_base_pnl(p),
                    theme=ticker_to_theme.get(symbol, "Other"),
                    account=account_name,
                    kind="stock",
                    source="superfinance",
                )
            )

        for op in account.get("option_positions", []):
            underlying = op.get("underlying")
            opt_type = "C" if str(op.get("type")).upper().startswith("CALL") else "P"
            strike = op.get("strike") or 0
            expiry = op.get("expiration") or ""
            label = f"{underlying} {expiry} " + "$" + f"{float(strike):.0f}{opt_type}"
            fx = op.get("fx_rate") or 1.0
            cost_base = float(op.get("cost_basis") or 0) * fx
            pnl = round(float(op.get("market_value_base") or 0) - cost_base, 2) if cost_base else None
            positions.append(
                _position(
                    symbol=f"{underlying} (opt)",
                    name=label,
                    qty=float(op.get("units") or 0),
                    price=float(op.get("current_price") or 0),
                    currency=op.get("currency") or raw.get("base_currency", "USD"),
                    value=float(op.get("market_value_base") or 0),
                    cost_basis=cost_base,
                    pnl=pnl,
                    theme=ticker_to_theme.get(underlying, "Other"),
                    account=account_name,
                    kind="option",
                    source="superfinance",
                    extra={
                        "underlying": underlying,
                        "strike": strike,
                        "expiry": expiry,
                        "option_type": op.get("type"),
                    },
                )
            )

        for cash in account.get("cash_balances", []):
            ccy = cash.get("currency") or raw.get("base_currency", "USD")
            value = float(cash.get("cash_base") or 0)
            amount = float(cash.get("cash") or 0)
            positions.append(
                _position(
                    symbol=f"Cash ({ccy})",
                    name=f"Cash ({ccy})",
                    qty=amount,
                    price=1.0,
                    currency=ccy,
                    value=value,
                    cost_basis=value,
                    pnl=0,
                    theme="Cash",
                    account=account_name,
                    kind="cash",
                    source="superfinance",
                )
            )

    manual = raw.get("manual_holdings", {}).get("holdings", [])
    for p in manual:
        symbol = p.get("symbol")
        fx = p.get("fx_rate") or 1.0
        cost_base = float(p.get("cost_basis") or 0) * fx
        positions.append(
            _position(
                symbol=symbol,
                name=p.get("description"),
                qty=float(p.get("units") or 0),
                price=float(p.get("current_price") or 0),
                currency=p.get("currency") or raw.get("base_currency", "USD"),
                value=float(p.get("market_value_base") or 0),
                cost_basis=cost_base,
                pnl=_base_pnl(p),
                theme=ticker_to_theme.get(symbol, "Other") if symbol else "Other",
                account=p.get("account_name") or "Manual",
                kind="manual",
                source="superfinance",
                extra={"notes": p.get("notes")} if p.get("notes") else None,
            )
        )

    by_account: dict[str, float] = {}
    by_theme: dict[str, dict[str, Any]] = {}
    for p in positions:
        by_account[p["account"]] = by_account.get(p["account"], 0) + p["market_value"]
        theme = p.get("theme") or "Other"
        if theme not in by_theme:
            meta = themes.get(theme, {})
            by_theme[theme] = {
                "value": 0.0,
                "pnl": 0.0,
                "color": meta.get("color", ""),
                "description": meta.get("description", ""),
                "positions": [],
            }
        by_theme[theme]["value"] += p["market_value"]
        by_theme[theme]["pnl"] += p.get("pnl") or 0
        by_theme[theme]["positions"].append(
            {
                "symbol": p["symbol"],
                "name": p["name"],
                "value": p["market_value"],
                "pnl": p.get("pnl"),
                "pnl_pct": p.get("pnl_pct"),
            }
        )

    by_account = dict(sorted(by_account.items(), key=lambda x: x[1], reverse=True))
    for info in by_theme.values():
        info["value"] = round(info["value"], 2)
        info["pnl"] = round(info["pnl"], 2)
    by_theme = dict(sorted(by_theme.items(), key=lambda x: x[1]["value"], reverse=True))

    cash_total = round(sum(p["market_value"] for p in positions if p["type"] == "cash"), 2)
    invested_total = round(sum(p["market_value"] for p in positions if p["type"] != "cash"), 2)
    total_pnl = round(sum(p.get("pnl") or 0 for p in positions if p["type"] != "cash"), 2)

    return {
        "positions": positions,
        "by_account": by_account,
        "by_theme": by_theme,
        "cash_total": cash_total,
        "invested_total": invested_total,
        "grand_total": round(invested_total + cash_total, 2),
        "unrealized_pnl": total_pnl,
        "currency": raw.get("base_currency", "USD"),
        "timestamp": raw.get("timestamp"),
        "source": "superfinance",
        "superfinance_totals": raw.get("totals", {}),
    }


def _fmt_money(v: float) -> str:
    sign = "-" if v < 0 else ""
    return sign + "$" + f"{abs(v):,.2f}"


def print_summary(data: dict[str, Any]) -> None:
    print(f"PORTFOLIO - Superfinance ({data['currency']})")
    print()
    print("BY ACCOUNT")
    print("-" * 50)
    total = data["grand_total"] or 1
    for account, value in data["by_account"].items():
        print(f"  {account:<45} {_fmt_money(value):>12}  ({value / total * 100:.0f}%)")
    print()
    print("BY THEME")
    print("-" * 50)
    for name, info in data["by_theme"].items():
        value = info["value"]
        pnl = info["pnl"]
        pnl_str = f"  P&L: {'+' if pnl >= 0 else ''}{_fmt_money(pnl)}" if pnl else ""
        print(f"  {name:<32} {_fmt_money(value):>12}  ({value / total * 100:.0f}%){pnl_str}")
        for p in info["positions"]:
            pct = p.get("pnl_pct")
            pct_str = f" ({'+' if pct >= 0 else ''}{pct:.0f}%)" if pct else ""
            print(f"      {(p.get('symbol') or p.get('name') or ''):<26} {_fmt_money(p['value']):>12}{pct_str}")
    print()
    print("=" * 50)
    print(f"  Invested:           {_fmt_money(data['invested_total']):>12}")
    print(f"  Cash:               {_fmt_money(data['cash_total']):>12}")
    print(f"  Unrealized P&L:     {'+' if data['unrealized_pnl'] >= 0 else ''}{_fmt_money(data['unrealized_pnl']):>11}")
    print("  =======================================")
    print(f"  TOTAL NET WORTH:    {_fmt_money(data['grand_total']):>12}")


def main() -> None:
    cmd = sys.argv[1] if len(sys.argv) > 1 else "summary"
    data = legacy_json()

    if cmd in {"json", "all"}:
        print(json.dumps(data, indent=2))
    elif cmd == "summary":
        print_summary(data)
    elif cmd == "accounts":
        print(json.dumps(data["by_account"], indent=2))
    elif cmd == "themes":
        print(json.dumps(data["by_theme"], indent=2))
    else:
        raise SystemExit("Usage: portfolio_cli.py <json|summary|accounts|themes|all>")


if __name__ == "__main__":
    main()
