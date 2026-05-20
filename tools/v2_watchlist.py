"""Watchlist tool — track tickers with timestamped research notes."""

import json
import uuid
from datetime import datetime, timezone
from typing import Optional

from users import current_user_token, get_user, update_user


VALID_ACTIONS = [
    "list",
    "get",
    "add_ticker",
    "remove_ticker",
    "add_note",
    "set_themes",
    "update_note",
    "remove_note",
]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _today_date() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _get_watchlist(token: str) -> dict:
    user = get_user(token)
    return user.get("watchlist", {}) if user else {}


def _save_watchlist(token: str, watchlist: dict):
    update_user(token, {"watchlist": watchlist})


def _normalize_theme(name: str) -> str:
    return " ".join(str(name or "").strip().split())


def _parse_themes(theme: Optional[str], themes: Optional[str]) -> list[str]:
    raw = []
    if theme:
        raw.append(theme)
    if themes:
        raw.extend(themes.replace("\n", ",").split(","))
    parsed = []
    for item in raw:
        normalized = _normalize_theme(item)
        if normalized and normalized not in parsed:
            parsed.append(normalized)
    return parsed


def _sync_theme_membership(token: str, ticker: str, theme_names: list[str]):
    if not ticker or not theme_names:
        return
    user = get_user(token) or {}
    registry = user.get("themes", {})
    for theme_name in theme_names:
        entry = registry.setdefault(
            theme_name,
            {
                "created_at": _now_iso(),
                "updated_at": _now_iso(),
                "description": "",
                "status": "active",
                "tickers": {},
            },
        )
        entry.setdefault("tickers", {})
        entry.setdefault("description", "")
        entry.setdefault("status", "active")
        entry["tickers"].setdefault(ticker, {"note": "watchlist-linked", "added_at": _now_iso()})
        entry["updated_at"] = _now_iso()
    update_user(token, {"themes": registry})


def _watchlist_item(ticker: str, entry: dict) -> dict:
    notes = entry.get("notes", [])
    last_note = notes[-1] if notes else None
    return {
        "ticker": ticker,
        "themes": entry.get("themes", []),
        "added_at": entry.get("added_at"),
        "note_count": len(notes),
        "last_note": {
            "date": last_note["date"],
            "text": last_note["text"],
        } if last_note else None,
    }


def _group_by_theme(items: list[dict]) -> dict:
    grouped: dict[str, list[dict]] = {}
    ungrouped = []
    for item in items:
        item_themes = item.get("themes") or []
        if not item_themes:
            ungrouped.append(item)
            continue
        for theme_name in item_themes:
            grouped.setdefault(theme_name, []).append(item)
    if ungrouped:
        grouped["Ungrouped"] = ungrouped
    return grouped


def register_watchlist_v2(server):

    @server.tool()
    def watchlist(
        action: str,
        ticker: Optional[str] = None,
        text: Optional[str] = None,
        note_id: Optional[str] = None,
        theme: Optional[str] = None,
        themes: Optional[str] = None,
        group_by_theme: bool = False,
    ) -> str:
        """
        Manage a personal watchlist of tickers with research notes.

        Each ticker in the watchlist can have multiple timestamped notes — great for
        tracking sentiment signals, options flow mentions, tweets you saw, analyst views,
        etc. Notes accumulate over time so you can look back at what you noticed.

        Actions:
        - list: Show all watchlist tickers with their themes, note counts, and most recent note.
        - get: Get all notes for a specific ticker. Requires `ticker`.
        - add_ticker: Add a new ticker to the watchlist (optionally with a first note and theme). Requires `ticker`, optional `text`, `theme`/`themes`.
        - remove_ticker: Remove a ticker and all its notes. Requires `ticker`.
        - add_note: Append a new note to an existing ticker. Requires `ticker` and `text`; optional `theme`/`themes` also groups it.
        - set_themes: Replace a ticker's theme groups. Requires `ticker`, `theme` or comma-separated `themes`.
        - update_note: Edit a note's text. Requires `ticker`, `note_id`, `text`.
        - remove_note: Delete a single note. Requires `ticker`, `note_id`.

        Notes are automatically dated when added/updated.
        When themes are provided, watchlist auto-syncs ticker membership into the `themes` registry.

        Examples:
            watchlist(action="add_ticker", ticker="NVDA", theme="Semiconductors", text="unusual_whales flagged bullish options flow")
            watchlist(action="set_themes", ticker="AMKR", themes="Packaging & Test, Semiconductors")
            watchlist(action="list", group_by_theme=True)
            watchlist(action="add_note", ticker="NVDA", text="Saw Jim Cramer bearish comments")
            watchlist(action="list")
            watchlist(action="get", ticker="NVDA")
            watchlist(action="remove_note", ticker="NVDA", note_id="ab12cd34")
            watchlist(action="remove_ticker", ticker="NVDA")
        """
        if action not in VALID_ACTIONS:
            return json.dumps({
                "error": f"Unknown action '{action}'",
                "valid_actions": VALID_ACTIONS,
            }, indent=2)

        token = current_user_token.get()
        if not token:
            return json.dumps({"error": "User context required"}, indent=2)

        wl = _get_watchlist(token)

        # Normalize ticker to uppercase for consistency
        tkr = ticker.strip().upper() if ticker else None
        theme_names = _parse_themes(theme, themes)

        if action == "list":
            items = []
            for t, entry in sorted(wl.items()):
                items.append(_watchlist_item(t, entry))
            return json.dumps({
                "success": True,
                "count": len(items),
                "tickers": items,
                "grouped_by_theme": _group_by_theme(items) if group_by_theme else None,
            }, indent=2)

        if action == "get":
            if not tkr:
                return json.dumps({"error": "ticker is required"}, indent=2)
            entry = wl.get(tkr)
            if not entry:
                return json.dumps({"error": f"{tkr} not in watchlist"}, indent=2)
            return json.dumps({
                "success": True,
                "ticker": tkr,
                "themes": entry.get("themes", []),
                "added_at": entry.get("added_at"),
                "notes": entry.get("notes", []),
            }, indent=2)

        if action == "add_ticker":
            if not tkr:
                return json.dumps({"error": "ticker is required"}, indent=2)
            if tkr in wl:
                return json.dumps({
                    "error": f"{tkr} already in watchlist",
                    "hint": "Use add_note to append a note instead",
                }, indent=2)

            entry = {"added_at": _now_iso(), "themes": theme_names, "notes": []}
            if text:
                entry["notes"].append({
                    "id": uuid.uuid4().hex[:8],
                    "date": _today_date(),
                    "text": text,
                })
            wl[tkr] = entry
            _save_watchlist(token, wl)
            _sync_theme_membership(token, tkr, theme_names)
            return json.dumps({
                "success": True,
                "ticker": tkr,
                "entry": entry,
            }, indent=2)

        if action == "remove_ticker":
            if not tkr:
                return json.dumps({"error": "ticker is required"}, indent=2)
            if tkr not in wl:
                return json.dumps({"error": f"{tkr} not in watchlist"}, indent=2)
            removed = wl.pop(tkr)
            _save_watchlist(token, wl)
            return json.dumps({
                "success": True,
                "removed": tkr,
                "note_count": len(removed.get("notes", [])),
            }, indent=2)

        if action == "add_note":
            if not tkr:
                return json.dumps({"error": "ticker is required"}, indent=2)
            if not text:
                return json.dumps({"error": "text is required"}, indent=2)
            # Auto-create ticker if missing
            if tkr not in wl:
                wl[tkr] = {"added_at": _now_iso(), "themes": [], "notes": []}
            if theme_names:
                current = wl[tkr].setdefault("themes", [])
                for theme_name in theme_names:
                    if theme_name not in current:
                        current.append(theme_name)

            note = {
                "id": uuid.uuid4().hex[:8],
                "date": _today_date(),
                "text": text,
            }
            wl[tkr]["notes"].append(note)
            _save_watchlist(token, wl)
            _sync_theme_membership(token, tkr, theme_names)
            return json.dumps({
                "success": True,
                "ticker": tkr,
                "themes": wl[tkr].get("themes", []),
                "note": note,
                "total_notes": len(wl[tkr]["notes"]),
            }, indent=2)

        if action == "set_themes":
            if not tkr:
                return json.dumps({"error": "ticker is required"}, indent=2)
            if not theme_names:
                return json.dumps({"error": "theme or themes is required"}, indent=2)
            if tkr not in wl:
                wl[tkr] = {"added_at": _now_iso(), "notes": []}
            wl[tkr]["themes"] = theme_names
            _save_watchlist(token, wl)
            _sync_theme_membership(token, tkr, theme_names)
            return json.dumps({
                "success": True,
                "ticker": tkr,
                "themes": theme_names,
            }, indent=2)

        if action == "update_note":
            if not tkr or not note_id or not text:
                return json.dumps({"error": "ticker, note_id, and text are all required"}, indent=2)
            entry = wl.get(tkr)
            if not entry:
                return json.dumps({"error": f"{tkr} not in watchlist"}, indent=2)
            target = next((n for n in entry["notes"] if n["id"] == note_id), None)
            if not target:
                return json.dumps({"error": f"No note with id '{note_id}' on {tkr}"}, indent=2)
            target["text"] = text
            target["date"] = _today_date()
            _save_watchlist(token, wl)
            return json.dumps({
                "success": True,
                "ticker": tkr,
                "note": target,
            }, indent=2)

        if action == "remove_note":
            if not tkr or not note_id:
                return json.dumps({"error": "ticker and note_id are required"}, indent=2)
            entry = wl.get(tkr)
            if not entry:
                return json.dumps({"error": f"{tkr} not in watchlist"}, indent=2)
            before = len(entry["notes"])
            entry["notes"] = [n for n in entry["notes"] if n["id"] != note_id]
            if len(entry["notes"]) == before:
                return json.dumps({"error": f"No note with id '{note_id}' on {tkr}"}, indent=2)
            _save_watchlist(token, wl)
            return json.dumps({
                "success": True,
                "removed_note": note_id,
                "ticker": tkr,
                "remaining_notes": len(entry["notes"]),
            }, indent=2)
