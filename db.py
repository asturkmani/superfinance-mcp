"""SQLite database for option flow and other structured data."""

import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path

_DATA_DIR = Path(os.getenv("DATA_DIR", "/data"))
_DB_PATH = _DATA_DIR / "superfinance.db"


def _ensure_dir():
    _DATA_DIR.mkdir(parents=True, exist_ok=True)


@contextmanager
def connect():
    """Yield a SQLite connection with row_factory and foreign keys on."""
    _ensure_dir()
    conn = sqlite3.connect(_DB_PATH, isolation_level=None)  # autocommit
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")  # better concurrent reads
    try:
        yield conn
    finally:
        conn.close()


def init_db():
    """Create tables if they don't exist."""
    with connect() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS option_flow (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_token TEXT NOT NULL,
            trade_date TEXT NOT NULL,
            order_type TEXT NOT NULL,
            symbol TEXT NOT NULL,
            strike TEXT NOT NULL,
            expiry TEXT NOT NULL,
            contracts INTEGER NOT NULL,
            notes TEXT,
            source TEXT DEFAULT 'manual',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS idx_of_user_symbol
            ON option_flow(user_token, symbol);
        CREATE INDEX IF NOT EXISTS idx_of_user_date
            ON option_flow(user_token, trade_date);
        """)


def row_to_dict(row: sqlite3.Row) -> dict:
    return {k: row[k] for k in row.keys()}
