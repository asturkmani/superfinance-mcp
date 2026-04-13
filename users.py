"""Per-user credential storage backed by a JSON file on disk."""

import json
import os
import uuid
from contextvars import ContextVar
from pathlib import Path
from typing import Optional

# Context variable set by middleware so tools know which user is calling.
current_user_token: ContextVar[Optional[str]] = ContextVar("current_user_token", default=None)

# Where the JSON file lives. On Fly.io this should be on a persistent volume.
_DATA_DIR = Path(os.getenv("DATA_DIR", "/data"))
_USERS_FILE = _DATA_DIR / "users.json"


def _ensure_dir():
    _DATA_DIR.mkdir(parents=True, exist_ok=True)


def load_users() -> dict:
    """Load the users dict from disk. Returns {} if file doesn't exist."""
    if _USERS_FILE.exists():
        return json.loads(_USERS_FILE.read_text())
    return {}


def save_users(users: dict):
    """Persist the users dict to disk."""
    _ensure_dir()
    _USERS_FILE.write_text(json.dumps(users, indent=2))


def create_user(email: str, snaptrade_user_id: str, snaptrade_user_secret: str) -> str:
    """Store a new user and return their unique token."""
    token = uuid.uuid4().hex
    users = load_users()
    users[token] = {
        "email": email,
        "snaptrade_user_id": snaptrade_user_id,
        "snaptrade_user_secret": snaptrade_user_secret,
        "base_currency": "USD",
    }
    save_users(users)
    return token


def get_user(token: str) -> Optional[dict]:
    """Look up a user by token. Returns their credential dict or None."""
    return load_users().get(token)


def update_user(token: str, updates: dict):
    """Patch fields on an existing user record."""
    users = load_users()
    if token in users:
        users[token].update(updates)
        save_users(users)


def get_user_by_email(email: str) -> Optional[tuple[str, dict]]:
    """Look up a user by email. Returns (token, user_dict) or None."""
    for token, data in load_users().items():
        if data.get("email") == email:
            return token, data
    return None
