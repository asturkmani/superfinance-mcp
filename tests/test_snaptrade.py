"""Integration tests for SnapTrade tool and user storage.

These tests hit the real SnapTrade API using credentials from .env.
Requires: SNAPTRADE_CONSUMER_KEY, SNAPTRADE_CLIENT_ID, SNAPTRADE_USER_ID, SNAPTRADE_USER_SECRET
"""

import json
import os
import shutil
import tempfile
import uuid
from pathlib import Path
from unittest.mock import patch

import pytest
from dotenv import load_dotenv

# Load .env from project root
load_dotenv(Path(__file__).parent.parent / ".env")

from fastmcp import FastMCP
from tools.v2_snaptrade import register_snaptrade_v2, _resolve_credentials
import users as users_mod


USER_ID = os.getenv("SNAPTRADE_USER_ID")
USER_SECRET = os.getenv("SNAPTRADE_USER_SECRET")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _reset_snaptrade_client():
    """Reset the singleton client before each test."""
    import tools.v2_snaptrade as mod
    mod._snaptrade_client = None


def _make_tool():
    """Create a callable portfolio tool backed by a real FastMCP server."""
    server = FastMCP("test")
    register_snaptrade_v2(server)
    tool_fn = None
    for tool in server._tool_manager._tools.values():
        if tool.name == "portfolio":
            tool_fn = tool.fn
            break
    assert tool_fn is not None, "portfolio tool not found in server"
    return tool_fn


_tool_fn = _make_tool()


def call_tool(**kwargs) -> dict:
    return json.loads(_tool_fn(**kwargs))


@pytest.fixture()
def tmp_data_dir(tmp_path):
    """Point user storage at a temp directory for isolation."""
    old = users_mod._DATA_DIR
    users_mod._DATA_DIR = tmp_path
    users_mod._USERS_FILE = tmp_path / "users.json"
    yield tmp_path
    users_mod._DATA_DIR = old
    users_mod._USERS_FILE = old / "users.json"


# ---------------------------------------------------------------------------
# User storage tests
# ---------------------------------------------------------------------------

class TestUserStorage:

    def test_create_and_get_user(self, tmp_data_dir):
        token = users_mod.create_user("a@test.com", "snap-uid", "snap-secret")
        assert len(token) == 32  # uuid hex

        user = users_mod.get_user(token)
        assert user["email"] == "a@test.com"
        assert user["snaptrade_user_id"] == "snap-uid"
        assert user["snaptrade_user_secret"] == "snap-secret"

    def test_get_unknown_token(self, tmp_data_dir):
        assert users_mod.get_user("nonexistent") is None

    def test_get_user_by_email(self, tmp_data_dir):
        token = users_mod.create_user("b@test.com", "uid-b", "secret-b")
        result = users_mod.get_user_by_email("b@test.com")
        assert result is not None
        found_token, data = result
        assert found_token == token
        assert data["snaptrade_user_id"] == "uid-b"

        assert users_mod.get_user_by_email("unknown@test.com") is None

    def test_multiple_users(self, tmp_data_dir):
        t1 = users_mod.create_user("x@test.com", "user-a", "secret-a")
        t2 = users_mod.create_user("y@test.com", "user-b", "secret-b")
        assert t1 != t2
        assert users_mod.get_user(t1)["snaptrade_user_id"] == "user-a"
        assert users_mod.get_user(t2)["snaptrade_user_id"] == "user-b"


# ---------------------------------------------------------------------------
# Credential resolution tests
# ---------------------------------------------------------------------------

class TestCredentialResolution:

    def test_explicit_args_win(self, tmp_data_dir):
        uid, secret = _resolve_credentials("explicit-id", "explicit-secret")
        assert uid == "explicit-id"
        assert secret == "explicit-secret"

    def test_user_token_context(self, tmp_data_dir):
        token = users_mod.create_user("ctx@test.com", "ctx-uid", "ctx-secret")
        tok = users_mod.current_user_token.set(token)
        try:
            uid, secret = _resolve_credentials(None, None)
            assert uid == "ctx-uid"
            assert secret == "ctx-secret"
        finally:
            users_mod.current_user_token.reset(tok)

    def test_env_fallback(self, tmp_data_dir):
        """With no explicit args and no token context, falls back to env vars."""
        uid, secret = _resolve_credentials(None, None)
        assert uid == os.getenv("SNAPTRADE_USER_ID")
        assert secret == os.getenv("SNAPTRADE_USER_SECRET")


# ---------------------------------------------------------------------------
# SnapTrade tool integration tests (hit real API via env-var credentials)
# ---------------------------------------------------------------------------

@pytest.mark.skipif(not USER_ID or not USER_SECRET, reason="USER_ID and USER_SECRET required")
class TestSnapTradeAccounts:

    def test_list_accounts(self):
        result = call_tool(action="accounts")

        assert result["success"] is True
        assert isinstance(result["accounts"], list)
        assert result["count"] == len(result["accounts"])
        assert result["count"] > 0

        account = result["accounts"][0]
        assert "account_id" in account
        assert "name" in account
        assert "institution" in account


@pytest.mark.skipif(not USER_ID or not USER_SECRET, reason="USER_ID and USER_SECRET required")
class TestSnapTradeHoldings:

    @pytest.fixture(scope="class")
    def first_account_id(self):
        result = call_tool(action="accounts")
        if result.get("count", 0) == 0:
            pytest.skip("No accounts connected")
        return result["accounts"][0]["account_id"]

    def test_get_holdings(self, first_account_id):
        result = call_tool(action="holdings", account_id=first_account_id)

        assert result["success"] is True
        assert "account" in result
        assert "positions" in result
        assert isinstance(result["positions"], list)
        assert result["account"]["id"] is not None

        if len(result["positions"]) > 0:
            pos = result["positions"][0]
            assert "symbol" in pos
            assert "units" in pos
            assert "current_price" in pos

    def test_holdings_missing_account_id(self):
        result = call_tool(action="holdings")
        assert "error" in result
        assert "account_id" in result["error"].lower()


@pytest.mark.skipif(not USER_ID or not USER_SECRET, reason="USER_ID and USER_SECRET required")
class TestSnapTradeConnect:

    def test_get_connect_url(self):
        result = call_tool(action="connect")

        assert result["success"] is True
        assert result["connection_url"] is not None
        assert result["connection_url"].startswith("http")


class TestSnapTradeCurrency:

    def test_set_currency(self, tmp_data_dir):
        token = users_mod.create_user("curr@test.com", "uid-c", "secret-c")
        tok = users_mod.current_user_token.set(token)
        try:
            result = call_tool(action="set_currency", currency="GBP")
            assert result["success"] is True
            assert result["base_currency"] == "GBP"
            assert result["previous"] == "USD"

            user = users_mod.get_user(token)
            assert user["base_currency"] == "GBP"
        finally:
            users_mod.current_user_token.reset(tok)

    def test_set_currency_invalid(self, tmp_data_dir):
        token = users_mod.create_user("inv@test.com", "uid-i", "secret-i")
        tok = users_mod.current_user_token.set(token)
        try:
            result = call_tool(action="set_currency", currency="XX")
            assert "error" in result
        finally:
            users_mod.current_user_token.reset(tok)

    def test_set_currency_no_user_context(self):
        result = call_tool(action="set_currency", currency="EUR")
        assert "error" in result


@pytest.mark.skipif(not USER_ID or not USER_SECRET, reason="USER_ID and USER_SECRET required")
class TestSnapTradeEnrichedHoldings:

    @pytest.fixture(scope="class")
    def first_account_id(self):
        result = call_tool(action="accounts")
        if result.get("count", 0) == 0:
            pytest.skip("No accounts connected")
        return result["accounts"][0]["account_id"]

    def test_holdings_have_enriched_fields(self, first_account_id):
        result = call_tool(action="holdings", account_id=first_account_id)
        assert result["success"] is True
        assert "base_currency" in result
        assert "total_value_base" in result
        assert isinstance(result["total_value_base"], (int, float))
        assert "cash_balances" in result

        if len(result["positions"]) > 0:
            pos = result["positions"][0]
            assert "market_value" in pos
            assert "market_value_base" in pos
            assert "currency" in pos
            assert "unrealised_pnl" in pos
            assert "unrealised_pnl_pct" in pos


@pytest.mark.skipif(not USER_ID or not USER_SECRET, reason="USER_ID and USER_SECRET required")
class TestSnapTradePortfolio:

    def test_portfolio_returns_all_accounts(self):
        result = call_tool(action="overview")
        assert result["success"] is True
        assert "base_currency" in result
        assert "grand_total_base" in result
        assert isinstance(result["accounts"], list)
        assert len(result["accounts"]) > 0

        acct = result["accounts"][0]
        assert "account" in acct
        assert "positions" in acct
        assert "cash_balances" in acct
        assert "total_value_base" in acct
        assert "positions_value_base" in acct
        assert "cash_value_base" in acct


class TestSnapTradeErrorCases:

    def test_missing_credentials_no_env(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("SNAPTRADE_USER_ID", None)
            os.environ.pop("SNAPTRADE_USER_SECRET", None)
            result = call_tool(action="accounts")
        assert "error" in result

    def test_invalid_action(self):
        result = call_tool(action="invalid_action")
        assert "error" in result
        assert "valid_actions" in result


# ---------------------------------------------------------------------------
# Manual holdings tests
# ---------------------------------------------------------------------------

class TestManualHoldings:

    def test_add_holding_trackable(self, tmp_data_dir):
        token = users_mod.create_user("h@test.com", "uid-h", "secret-h")
        tok = users_mod.current_user_token.set(token)
        try:
            result = call_tool(
                action="add_holding", description="Pension VOO",
                symbol="VOO", units=500, currency="USD", cost_price=420,
            )
            assert result["success"] is True
            h = result["holding"]
            assert h["symbol"] == "VOO"
            assert h["units"] == 500
            assert h["cost_price"] == 420
            assert h["account_name"] == "Manual"
            assert len(h["id"]) == 8

            user = users_mod.get_user(token)
            assert len(user["manual_holdings"]) == 1
        finally:
            users_mod.current_user_token.reset(tok)

    def test_add_holding_fixed_value(self, tmp_data_dir):
        token = users_mod.create_user("f@test.com", "uid-f", "secret-f")
        tok = users_mod.current_user_token.set(token)
        try:
            result = call_tool(
                action="add_holding", description="Loan to Mobility Giant",
                units=1, currency="GBP", manual_price=25000,
                account_name="Private",
            )
            assert result["success"] is True
            h = result["holding"]
            assert h["symbol"] is None
            assert h["manual_price"] == 25000
            assert h["account_name"] == "Private"
        finally:
            users_mod.current_user_token.reset(tok)

    def test_add_holding_missing_fields(self, tmp_data_dir):
        token = users_mod.create_user("m@test.com", "uid-m", "secret-m")
        tok = users_mod.current_user_token.set(token)
        try:
            result = call_tool(action="add_holding", description="X")
            assert "error" in result
        finally:
            users_mod.current_user_token.reset(tok)

    def test_update_holding(self, tmp_data_dir):
        token = users_mod.create_user("u@test.com", "uid-u", "secret-u")
        tok = users_mod.current_user_token.set(token)
        try:
            add_result = call_tool(
                action="add_holding", description="Test",
                units=10, currency="USD", manual_price=100,
            )
            hid = add_result["holding"]["id"]

            result = call_tool(action="update_holding", id=hid, units=20, manual_price=150)
            assert result["success"] is True
            assert result["holding"]["units"] == 20
            assert result["holding"]["manual_price"] == 150
        finally:
            users_mod.current_user_token.reset(tok)

    def test_remove_holding(self, tmp_data_dir):
        token = users_mod.create_user("r@test.com", "uid-r", "secret-r")
        tok = users_mod.current_user_token.set(token)
        try:
            add_result = call_tool(
                action="add_holding", description="To Remove",
                units=1, currency="USD", manual_price=50,
            )
            hid = add_result["holding"]["id"]

            result = call_tool(action="remove_holding", id=hid)
            assert result["success"] is True

            user = users_mod.get_user(token)
            assert len(user.get("manual_holdings", [])) == 0
        finally:
            users_mod.current_user_token.reset(tok)

    def test_remove_nonexistent(self, tmp_data_dir):
        token = users_mod.create_user("n@test.com", "uid-n", "secret-n")
        tok = users_mod.current_user_token.set(token)
        try:
            result = call_tool(action="remove_holding", id="nonexistent")
            assert "error" in result
        finally:
            users_mod.current_user_token.reset(tok)

    def test_list_holdings_empty(self, tmp_data_dir):
        token = users_mod.create_user("e@test.com", "uid-e", "secret-e")
        tok = users_mod.current_user_token.set(token)
        try:
            result = call_tool(action="list_holdings")
            assert result["success"] is True
            assert result["count"] == 0
        finally:
            users_mod.current_user_token.reset(tok)

    def test_no_user_context(self):
        result = call_tool(action="add_holding", description="X", units=1, currency="USD")
        assert "error" in result
