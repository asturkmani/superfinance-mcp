"""Tests for x_accounts tool."""

import json
from pathlib import Path

import pytest
from dotenv import load_dotenv
from fastmcp import FastMCP

load_dotenv(Path(__file__).parent.parent / ".env")

import users as users_mod  # noqa: E402
from tools.v2_x_accounts import register_x_accounts_v2  # noqa: E402


def _make_tool():
    server = FastMCP("test")
    register_x_accounts_v2(server)
    for t in server._tool_manager._tools.values():
        if t.name == "x_accounts":
            return t.fn
    raise RuntimeError("x_accounts tool not found")


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
    token = users_mod.create_user("x@test.com", "uid-x", "secret-x")
    tok = users_mod.current_user_token.set(token)
    yield token
    users_mod.current_user_token.reset(tok)


class TestXAccounts:

    def test_add_account_normalizes_handle(self, authenticated):
        r = call_tool(
            action="add",
            handle="@unusual_whales",
            note="options flow / unusual sweeps",
        )
        assert r["success"] is True
        assert r["account"]["handle"] == "unusual_whales"
        assert r["account"]["note"] == "options flow / unusual sweeps"
        assert r["account"]["added_at"]
        assert r["account"]["updated_at"]

    def test_add_requires_handle_and_note(self, authenticated):
        assert "error" in call_tool(action="add", handle="@foo")
        assert "error" in call_tool(action="add", note="macro")

    def test_add_duplicate_errors(self, authenticated):
        call_tool(action="add", handle="DeItaone", note="breaking market news")
        r = call_tool(action="add", handle="@DeItaone", note="duplicate")
        assert "error" in r

    def test_upsert_creates_then_updates(self, authenticated):
        r1 = call_tool(action="upsert", handle="zerohedge", note="macro rumour mill")
        assert r1["created"] is True
        r2 = call_tool(action="upsert", handle="@zerohedge", note="macro risk / rumour mill")
        assert r2["created"] is False
        got = call_tool(action="get", handle="zerohedge")
        assert got["account"]["note"] == "macro risk / rumour mill"

    def test_list_sorted_and_prompt_handles(self, authenticated):
        call_tool(action="add", handle="b", note="second")
        call_tool(action="add", handle="@a", note="first")
        r = call_tool(action="list")
        assert r["count"] == 2
        assert [a["handle"] for a in r["accounts"]] == ["a", "b"]
        assert r["handles_csv"] == "a,b"
        assert r["handles_for_x_search"] == "a,b"

    def test_get(self, authenticated):
        call_tool(action="add", handle="litcapital", note="finmemes and sentiment")
        r = call_tool(action="get", handle="@litcapital")
        assert r["success"] is True
        assert r["account"]["handle"] == "litcapital"

    def test_update_note(self, authenticated):
        call_tool(action="add", handle="TheTranscript_", note="earnings transcript snippets")
        r = call_tool(
            action="update",
            handle="TheTranscript_",
            note="earnings transcript snippets / guide downs",
        )
        assert r["success"] is True
        assert "guide downs" in r["account"]["note"]

    def test_remove(self, authenticated):
        call_tool(action="add", handle="foo", note="bar")
        r = call_tool(action="remove", handle="@foo")
        assert r["success"] is True
        assert call_tool(action="list")["count"] == 0

    def test_search_filters_by_note(self, authenticated):
        call_tool(action="add", handle="unusual_whales", note="options flow")
        call_tool(action="add", handle="DeItaone", note="breaking macro news")
        r = call_tool(action="search", query="macro")
        assert r["count"] == 1
        assert r["accounts"][0]["handle"] == "DeItaone"
        assert r["handles_csv"] == "DeItaone"

    def test_user_isolation(self, tmp_data_dir):
        token_a = users_mod.create_user("a@test.com", "uid-a", "secret-a")
        token_b = users_mod.create_user("b@test.com", "uid-b", "secret-b")
        tok = users_mod.current_user_token.set(token_a)
        call_tool(action="add", handle="a", note="only a")
        users_mod.current_user_token.reset(tok)

        tok = users_mod.current_user_token.set(token_b)
        try:
            assert call_tool(action="list")["count"] == 0
        finally:
            users_mod.current_user_token.reset(tok)

    def test_invalid_action_and_no_context(self, authenticated, tmp_data_dir):
        assert "error" in call_tool(action="bogus")
        users_mod.current_user_token.set(None)
        assert "error" in call_tool(action="list")
