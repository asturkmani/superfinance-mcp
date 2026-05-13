"""X accounts tool — store handles and why to follow them."""

import json
import re
from datetime import datetime, timezone
from typing import Optional

from users import current_user_token, get_user, update_user


VALID_ACTIONS = ["list", "get", "add", "upsert", "update", "remove", "search"]
_HANDLE_RE = re.compile(r"^[A-Za-z0-9_]{1,15}$")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _normalize_handle(handle: Optional[str]) -> Optional[str]:
    if not handle:
        return None
    h = handle.strip()
    if h.startswith("@"):
        h = h[1:]
    h = h.strip()
    return h or None


def _validate_handle(handle: str) -> Optional[str]:
    if not _HANDLE_RE.match(handle):
        return (
            "handle must be a valid X handle: 1-15 letters/numbers/underscores, optional leading @"
        )
    return None


def _get_accounts(token: str) -> dict:
    user = get_user(token)
    return user.get("x_accounts", {}) if user else {}


def _save_accounts(token: str, accounts: dict):
    update_user(token, {"x_accounts": accounts})


def _as_sorted_list(accounts: dict) -> list[dict]:
    return [accounts[h] for h in sorted(accounts, key=lambda x: x.lower())]


def _response(accounts: list[dict], **extra) -> str:
    handles_csv = ",".join(a["handle"] for a in accounts)
    payload = {
        "success": True,
        "count": len(accounts),
        "accounts": accounts,
        "handles_csv": handles_csv,
        "handles_for_x_search": handles_csv,
        **extra,
    }
    return json.dumps(payload, indent=2)


def register_x_accounts_v2(server):

    @server.tool()
    def x_accounts(
        action: str,
        handle: Optional[str] = None,
        note: Optional[str] = None,
        query: Optional[str] = None,
    ) -> str:
        """
        Store X/Twitter accounts to follow, plus why to check each one.

        Use this as a personal account directory for targeted x_search calls.
        The returned `handles_csv` can be passed directly to x_search handles.

        Actions:
        - list: List saved accounts with notes and handles_csv.
        - get: Get one account. Requires `handle`.
        - add: Add a new account. Requires `handle` and `note`.
        - upsert: Add or update an account. Requires `handle` and `note`.
        - update: Update an account note. Requires `handle` and `note`.
        - remove: Remove an account. Requires `handle`.
        - search: Search handles/notes. Requires `query`.

        Examples:
            x_accounts(action="add", handle="unusual_whales", note="options flow and large sweeps")
            x_accounts(action="add", handle="DeItaone", note="breaking macro/market news")
            x_accounts(action="search", query="options")
            x_accounts(action="list")
        """
        if action not in VALID_ACTIONS:
            return json.dumps(
                {"error": f"Unknown action '{action}'", "valid_actions": VALID_ACTIONS},
                indent=2,
            )

        token = current_user_token.get()
        if not token:
            return json.dumps({"error": "User context required"}, indent=2)

        accounts = _get_accounts(token)
        normalized = _normalize_handle(handle)

        if normalized:
            err = _validate_handle(normalized)
            if err:
                return json.dumps({"error": err}, indent=2)

        if action == "list":
            return _response(_as_sorted_list(accounts))

        if action == "search":
            if not query:
                return json.dumps({"error": "query is required"}, indent=2)
            q = query.lower()
            matches = [
                acct
                for acct in _as_sorted_list(accounts)
                if q in acct["handle"].lower() or q in acct.get("note", "").lower()
            ]
            return _response(matches, query=query)

        if not normalized:
            return json.dumps({"error": "handle is required"}, indent=2)

        if action == "get":
            account = accounts.get(normalized)
            if not account:
                return json.dumps({"error": f"@{normalized} not found"}, indent=2)
            return json.dumps({"success": True, "account": account}, indent=2)

        if action == "remove":
            account = accounts.pop(normalized, None)
            if not account:
                return json.dumps({"error": f"@{normalized} not found"}, indent=2)
            _save_accounts(token, accounts)
            return json.dumps({"success": True, "removed": account}, indent=2)

        if action in ("add", "upsert", "update"):
            if not note:
                return json.dumps({"error": "note is required"}, indent=2)
            now = _now_iso()
            existing = accounts.get(normalized)

            if action == "add" and existing:
                return json.dumps(
                    {
                        "error": f"@{normalized} already exists",
                        "hint": "Use update or upsert to change the note",
                    },
                    indent=2,
                )
            if action == "update" and not existing:
                return json.dumps({"error": f"@{normalized} not found"}, indent=2)

            created = existing is None
            account = existing or {"handle": normalized, "added_at": now}
            account["note"] = note
            account["updated_at"] = now
            accounts[normalized] = account
            _save_accounts(token, accounts)

            return json.dumps(
                {
                    "success": True,
                    "created": created,
                    "account": account,
                },
                indent=2,
            )

        return json.dumps({"error": f"Unhandled action '{action}'"}, indent=2)
