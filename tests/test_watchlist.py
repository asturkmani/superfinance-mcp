"""Tests for the watchlist tool."""
import json
from pathlib import Path

import pytest
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

from fastmcp import FastMCP
from tools.v2_watchlist import register_watchlist_v2
import users as users_mod


def _make_tool():
    server = FastMCP("test")
    register_watchlist_v2(server)
    for t in server._tool_manager._tools.values():
        if t.name == "watchlist":
            return t.fn
    raise RuntimeError("watchlist tool not found")


_tool_fn = _make_tool()


def call_tool(**kwargs) -> dict:
    return json.loads(_tool_fn(**kwargs))


@pytest.fixture()
def tmp_data_dir(tmp_path):
    old = users_mod._DATA_DIR
    users_mod._DATA_DIR = tmp_path
    users_mod._USERS_FILE = tmp_path / "users.json"
    yield tmp_path
    users_mod._DATA_DIR = old
    users_mod._USERS_FILE = old / "users.json"


@pytest.fixture()
def authenticated(tmp_data_dir):
    token = users_mod.create_user("wl@test.com", "uid-wl", "secret-wl")
    tok = users_mod.current_user_token.set(token)
    yield token
    users_mod.current_user_token.reset(tok)


class TestWatchlist:

    def test_add_ticker_with_note(self, authenticated):
        r = call_tool(action="add_ticker", ticker="NVDA", text="first note")
        assert r["success"] is True
        assert r["ticker"] == "NVDA"
        assert len(r["entry"]["notes"]) == 1
        assert r["entry"]["notes"][0]["text"] == "first note"

    def test_add_ticker_lowercases_to_upper(self, authenticated):
        r = call_tool(action="add_ticker", ticker="nvda")
        assert r["ticker"] == "NVDA"

    def test_add_ticker_duplicate_errors(self, authenticated):
        call_tool(action="add_ticker", ticker="NVDA")
        r = call_tool(action="add_ticker", ticker="NVDA")
        assert "error" in r

    def test_add_note_auto_creates_ticker(self, authenticated):
        r = call_tool(action="add_note", ticker="AAPL", text="earnings upcoming")
        assert r["success"] is True
        assert r["total_notes"] == 1

    def test_add_multiple_notes(self, authenticated):
        call_tool(action="add_ticker", ticker="NVDA")
        call_tool(action="add_note", ticker="NVDA", text="first")
        r = call_tool(action="add_note", ticker="NVDA", text="second")
        assert r["total_notes"] == 2

    def test_list(self, authenticated):
        call_tool(action="add_ticker", ticker="NVDA", text="n1")
        call_tool(action="add_note", ticker="AAPL", text="a1")
        r = call_tool(action="list")
        assert r["count"] == 2
        tickers = [t["ticker"] for t in r["tickers"]]
        assert "NVDA" in tickers and "AAPL" in tickers

    def test_get(self, authenticated):
        call_tool(action="add_ticker", ticker="NVDA", text="n1")
        call_tool(action="add_note", ticker="NVDA", text="n2")
        r = call_tool(action="get", ticker="NVDA")
        assert len(r["notes"]) == 2

    def test_update_note(self, authenticated):
        r = call_tool(action="add_ticker", ticker="NVDA", text="original")
        note_id = r["entry"]["notes"][0]["id"]
        r2 = call_tool(action="update_note", ticker="NVDA", note_id=note_id, text="edited")
        assert r2["note"]["text"] == "edited"

    def test_remove_note(self, authenticated):
        r = call_tool(action="add_ticker", ticker="NVDA", text="x")
        note_id = r["entry"]["notes"][0]["id"]
        r2 = call_tool(action="remove_note", ticker="NVDA", note_id=note_id)
        assert r2["success"] is True
        assert r2["remaining_notes"] == 0

    def test_remove_ticker(self, authenticated):
        call_tool(action="add_ticker", ticker="NVDA")
        r = call_tool(action="remove_ticker", ticker="NVDA")
        assert r["success"] is True
        r2 = call_tool(action="list")
        assert r2["count"] == 0

    def test_get_missing_ticker_errors(self, authenticated):
        r = call_tool(action="get", ticker="TSLA")
        assert "error" in r

    def test_update_missing_note_errors(self, authenticated):
        call_tool(action="add_ticker", ticker="NVDA")
        r = call_tool(action="update_note", ticker="NVDA", note_id="nope", text="x")
        assert "error" in r

    def test_invalid_action(self, authenticated):
        r = call_tool(action="foo")
        assert "error" in r
        assert "valid_actions" in r

    def test_no_user_context(self, tmp_data_dir):
        r = call_tool(action="list")
        assert "error" in r
