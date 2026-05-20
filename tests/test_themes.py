"""Tests for themes tool."""

import json
from pathlib import Path

import pytest
from dotenv import load_dotenv
from fastmcp import FastMCP

load_dotenv(Path(__file__).parent.parent / ".env")

import users as users_mod  # noqa: E402
from tools.v2_themes import register_themes_v2  # noqa: E402


def _make_tool():
    server = FastMCP("test")
    register_themes_v2(server)
    for t in server._tool_manager._tools.values():
        if t.name == "themes":
            return t.fn
    raise RuntimeError("themes tool not found")


_tool_fn = _make_tool()


def call_tool(**kwargs) -> dict:
    return json.loads(_tool_fn(**kwargs))


@pytest.fixture()
def tmp_data_dir(tmp_path):
    old_data = users_mod._DATA_DIR
    old_file = users_mod._USERS_FILE
    users_mod._DATA_DIR = tmp_path
    users_mod._USERS_FILE = tmp_path / "users.json"
    yield tmp_path
    users_mod._DATA_DIR = old_data
    users_mod._USERS_FILE = old_file


@pytest.fixture()
def authenticated(tmp_data_dir):
    token = users_mod.create_user("themes@test.com", "uid-themes", "secret-themes")
    tok = users_mod.current_user_token.set(token)
    yield token
    users_mod.current_user_token.reset(tok)


class TestThemes:

    def test_upsert_theme_and_add_ticker(self, authenticated):
        r = call_tool(
            action="upsert_theme",
            name=" Packaging & Test ",
            description="AI advanced packaging bottleneck",
        )
        assert r["success"] is True
        assert r["created"] is True
        assert r["theme"]["name"] == "Packaging & Test"

        r = call_tool(action="add_ticker", name="Packaging & Test", ticker="amkr", note="OSAT exposure")
        assert r["success"] is True
        assert r["theme"]["ticker_count"] == 1
        assert r["theme"]["tickers"][0]["ticker"] == "AMKR"

    def test_list_returns_union_tickers(self, authenticated):
        call_tool(action="add_ticker", name="Memory", ticker="MU")
        call_tool(action="add_ticker", name="Memory", ticker="SNDK")
        call_tool(action="add_ticker", name="Photonics", ticker="LITE")
        r = call_tool(action="list")
        assert r["count"] == 2
        assert r["tickers"] == ["LITE", "MU", "SNDK"]

    def test_set_tickers_replaces_membership(self, authenticated):
        call_tool(action="add_ticker", name="MLCC", ticker="MURATA")
        r = call_tool(action="set_tickers", name="MLCC", tickers="6762.T, KYOCY")
        assert r["success"] is True
        assert [x["ticker"] for x in r["theme"]["tickers"]] == ["6762.T", "KYOCY"]

    def test_user_isolation(self, tmp_data_dir):
        token_a = users_mod.create_user("a@test.com", "uid-a", "secret-a")
        token_b = users_mod.create_user("b@test.com", "uid-b", "secret-b")

        tok = users_mod.current_user_token.set(token_a)
        call_tool(action="add_ticker", name="Memory", ticker="MU")
        users_mod.current_user_token.reset(tok)

        tok = users_mod.current_user_token.set(token_b)
        try:
            assert call_tool(action="list")["count"] == 0
        finally:
            users_mod.current_user_token.reset(tok)
