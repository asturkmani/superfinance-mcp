"""Theme registry tool — manage investable themes and mapped tickers."""

import json
from datetime import datetime, timezone
from typing import Optional

from users import current_user_token, get_user, update_user


VALID_ACTIONS = [
    "list",
    "get",
    "upsert_theme",
    "remove_theme",
    "add_ticker",
    "remove_ticker",
    "set_tickers",
]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _normalize_theme(name: Optional[str]) -> Optional[str]:
    if not name:
        return None
    return " ".join(name.strip().split())


def _normalize_ticker(ticker: Optional[str]) -> Optional[str]:
    if not ticker:
        return None
    return ticker.strip().upper()


def _get_themes(token: str) -> dict:
    user = get_user(token)
    return user.get("themes", {}) if user else {}


def _save_themes(token: str, themes: dict):
    update_user(token, {"themes": themes})


def _theme_payload(name: str, entry: dict) -> dict:
    tickers = entry.get("tickers", {})
    return {
        "name": name,
        "description": entry.get("description", ""),
        "status": entry.get("status", "active"),
        "tickers": [
            {
                "ticker": ticker,
                "note": meta.get("note", "") if isinstance(meta, dict) else "",
                "added_at": meta.get("added_at") if isinstance(meta, dict) else None,
            }
            for ticker, meta in sorted(tickers.items())
        ],
        "ticker_count": len(tickers),
        "created_at": entry.get("created_at"),
        "updated_at": entry.get("updated_at"),
    }


def register_themes_v2(server):

    @server.tool()
    def themes(
        action: str,
        name: Optional[str] = None,
        description: Optional[str] = None,
        status: Optional[str] = None,
        ticker: Optional[str] = None,
        tickers: Optional[str] = None,
        note: Optional[str] = None,
    ) -> str:
        """
        Manage the user's investable themes and mapped tickers.

        This is the source of truth for X Signal, watchlist grouping, and daily canvas themes.

        Actions:
        - list: List all themes and ticker counts.
        - get: Get one theme with mapped tickers. Requires `name`.
        - upsert_theme: Create or update a theme. Requires `name`.
        - remove_theme: Remove a theme. Requires `name`.
        - add_ticker: Add one ticker to a theme. Requires `name` and `ticker`.
        - remove_ticker: Remove one ticker from a theme. Requires `name` and `ticker`.
        - set_tickers: Replace a theme's tickers. Requires `name` and comma-separated `tickers`.

        Examples:
            themes(action="upsert_theme", name="Packaging & Test", description="AI advanced packaging bottleneck")
            themes(action="add_ticker", name="Packaging & Test", ticker="AMKR", note="OSAT exposure")
            themes(action="list")
            themes(action="get", name="Packaging & Test")
        """
        if action not in VALID_ACTIONS:
            return json.dumps({"error": f"Unknown action '{action}'", "valid_actions": VALID_ACTIONS}, indent=2)

        token = current_user_token.get()
        if not token:
            return json.dumps({"error": "User context required"}, indent=2)

        registry = _get_themes(token)
        theme_name = _normalize_theme(name)
        tkr = _normalize_ticker(ticker)

        if action == "list":
            items = [_theme_payload(n, e) for n, e in sorted(registry.items())]
            return json.dumps(
                {
                    "success": True,
                    "count": len(items),
                    "themes": items,
                    "tickers": sorted({t for entry in registry.values() for t in entry.get("tickers", {}).keys()}),
                },
                indent=2,
            )

        if not theme_name:
            return json.dumps({"error": "name is required"}, indent=2)

        if action == "get":
            entry = registry.get(theme_name)
            if not entry:
                return json.dumps({"error": f"{theme_name} not found"}, indent=2)
            return json.dumps({"success": True, "theme": _theme_payload(theme_name, entry)}, indent=2)

        if action == "upsert_theme":
            created = theme_name not in registry
            entry = registry.setdefault(theme_name, {"created_at": _now_iso(), "tickers": {}})
            if description is not None:
                entry["description"] = description
            if status is not None:
                entry["status"] = status
            entry.setdefault("status", "active")
            entry.setdefault("description", "")
            entry["updated_at"] = _now_iso()
            _save_themes(token, registry)
            return json.dumps(
                {"success": True, "created": created, "theme": _theme_payload(theme_name, entry)},
                indent=2,
            )

        if action == "remove_theme":
            if theme_name not in registry:
                return json.dumps({"error": f"{theme_name} not found"}, indent=2)
            removed = registry.pop(theme_name)
            _save_themes(token, registry)
            return json.dumps(
                {"success": True, "removed": _theme_payload(theme_name, removed)},
                indent=2,
            )

        entry = registry.setdefault(theme_name, {"created_at": _now_iso(), "updated_at": _now_iso(), "description": "", "status": "active", "tickers": {}})
        entry.setdefault("tickers", {})

        if action == "add_ticker":
            if not tkr:
                return json.dumps({"error": "ticker is required"}, indent=2)
            entry["tickers"][tkr] = {"note": note or "", "added_at": _now_iso()}
            entry["updated_at"] = _now_iso()
            _save_themes(token, registry)
            return json.dumps({"success": True, "theme": _theme_payload(theme_name, entry)}, indent=2)

        if action == "remove_ticker":
            if not tkr:
                return json.dumps({"error": "ticker is required"}, indent=2)
            if tkr not in entry["tickers"]:
                return json.dumps({"error": f"{tkr} not found in {theme_name}"}, indent=2)
            entry["tickers"].pop(tkr)
            entry["updated_at"] = _now_iso()
            _save_themes(token, registry)
            return json.dumps({"success": True, "theme": _theme_payload(theme_name, entry)}, indent=2)

        if action == "set_tickers":
            if tickers is None:
                return json.dumps({"error": "tickers is required"}, indent=2)
            parsed = [_normalize_ticker(x) for x in tickers.replace("\n", ",").split(",")]
            entry["tickers"] = {x: {"note": "", "added_at": _now_iso()} for x in parsed if x}
            entry["updated_at"] = _now_iso()
            _save_themes(token, registry)
            return json.dumps({"success": True, "theme": _theme_payload(theme_name, entry)}, indent=2)

        return json.dumps({"error": f"Unhandled action {action}"}, indent=2)
