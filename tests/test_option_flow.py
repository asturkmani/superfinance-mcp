"""Integration tests for the option_flow SQLite-backed tool."""

import json
import sys
from pathlib import Path

import pytest
from fastmcp import FastMCP

sys.path.insert(0, str(Path(__file__).parent.parent))

import db as db_mod  # noqa: E402
import users as users_mod  # noqa: E402
from tools.v2_option_flow import register_option_flow_v2  # noqa: E402


@pytest.fixture()
def fresh_db(tmp_path):
    """Point the SQLite DB at a temp file and re-init."""
    old_data = db_mod._DATA_DIR
    old_db = db_mod._DB_PATH
    db_mod._DATA_DIR = tmp_path
    db_mod._DB_PATH = tmp_path / "test.db"
    db_mod.init_db()
    yield tmp_path
    db_mod._DATA_DIR = old_data
    db_mod._DB_PATH = old_db


@pytest.fixture()
def tool_fn(fresh_db):
    server = FastMCP("test")
    register_option_flow_v2(server)
    for t in server._tool_manager._tools.values():
        if t.name == "option_flow":
            return t.fn
    raise AssertionError("option_flow tool not registered")


@pytest.fixture()
def user_token():
    """Set a fake user token in the context."""
    tok = users_mod.current_user_token.set("test-token-xyz")
    yield "test-token-xyz"
    users_mod.current_user_token.reset(tok)


def call(fn, **kwargs):
    return json.loads(fn(**kwargs))


# ---------------------------------------------------------------------------


class TestOptionFlowAdd:

    def test_add_basic(self, tool_fn, user_token):
        r = call(
            tool_fn,
            action="add",
            symbol="AMZN",
            order_type="Calls Bought",
            strike="270C",
            expiry="2026-06-05",
            contracts=5000,
            trade_date="2026-05-04 10:37",
        )
        assert r["success"] is True
        assert r["trade"]["symbol"] == "AMZN"
        assert r["trade"]["contracts"] == 5000
        assert r["trade"]["source"] == "manual"
        assert r["trade"]["id"] >= 1

    def test_add_validates_order_type(self, tool_fn, user_token):
        r = call(
            tool_fn,
            action="add",
            symbol="AMZN",
            order_type="bogus",
            strike="270C",
            expiry="2026-06-05",
            contracts=5000,
            trade_date="2026-05-04 10:37",
        )
        assert "error" in r

    def test_add_requires_fields(self, tool_fn, user_token):
        r = call(tool_fn, action="add", symbol="AMZN")
        assert "error" in r

    def test_add_no_user_context(self, tool_fn):
        r = call(
            tool_fn,
            action="add",
            symbol="AMZN",
            order_type="Calls Bought",
            strike="270C",
            expiry="2026-06-05",
            contracts=5000,
            trade_date="2026-05-04 10:37",
        )
        assert "error" in r

    def test_symbol_uppercased(self, tool_fn, user_token):
        r = call(
            tool_fn,
            action="add",
            symbol="amzn",
            order_type="Calls Bought",
            strike="270C",
            expiry="2026-06-05",
            contracts=5000,
            trade_date="2026-05-04 10:37",
        )
        assert r["trade"]["symbol"] == "AMZN"


class TestOptionFlowBulk:

    def test_add_bulk(self, tool_fn, user_token):
        rows = json.dumps(
            [
                {
                    "symbol": "AMZN",
                    "order_type": "Calls Bought",
                    "strike": "270C",
                    "expiry": "2026-06-05",
                    "contracts": 5000,
                    "trade_date": "2026-05-04 10:37",
                },
                {
                    "symbol": "TSLA",
                    "order_type": "Puts Bought",
                    "strike": "250P",
                    "expiry": "2026-06-18",
                    "contracts": 2500,
                    "trade_date": "2026-05-04 10:12",
                },
            ]
        )
        r = call(tool_fn, action="add_bulk", rows=rows)
        assert r["success"] is True
        assert r["inserted"] == 2

    def test_bulk_partial_failures(self, tool_fn, user_token):
        rows = json.dumps(
            [
                {
                    "symbol": "AMZN",
                    "order_type": "Calls Bought",
                    "strike": "270C",
                    "expiry": "2026-06-05",
                    "contracts": 5000,
                    "trade_date": "2026-05-04 10:37",
                },
                {"symbol": "BAD", "order_type": "Invalid Type"},
            ]
        )
        r = call(tool_fn, action="add_bulk", rows=rows)
        assert r["inserted"] == 1
        assert len(r["errors"]) == 1

    def test_bulk_invalid_json(self, tool_fn, user_token):
        r = call(tool_fn, action="add_bulk", rows="not json")
        assert "error" in r


class TestOptionFlowQuery:

    def _seed(self, fn):
        for sym, ot, strike, exp, c, d in [
            ("AMZN", "Calls Bought", "270C", "2026-06-05", 5000, "2026-05-04 10:37"),
            ("AMZN", "Puts Bought", "250P", "2026-06-18", 2500, "2026-05-04 10:12"),
            ("TSLA", "Calls Bought", "300C", "2026-06-21", 1000, "2026-05-03 09:00"),
            ("AMZN", "Calls Bought", "315C", "2026-08-21", 3000, "2026-05-01 13:55"),
        ]:
            call(
                fn,
                action="add",
                symbol=sym,
                order_type=ot,
                strike=strike,
                expiry=exp,
                contracts=c,
                trade_date=d,
            )

    def test_list_all(self, tool_fn, user_token):
        self._seed(tool_fn)
        r = call(tool_fn, action="list")
        assert r["count"] == 4
        # Sorted by trade_date DESC
        assert r["trades"][0]["trade_date"] == "2026-05-04 10:37"

    def test_list_filter_symbol(self, tool_fn, user_token):
        self._seed(tool_fn)
        r = call(tool_fn, action="list", symbol="AMZN")
        assert r["count"] == 3

    def test_list_filter_order_type(self, tool_fn, user_token):
        self._seed(tool_fn)
        r = call(tool_fn, action="list", order_type="Calls Bought")
        assert r["count"] == 3

    def test_list_filter_date_range(self, tool_fn, user_token):
        self._seed(tool_fn)
        r = call(tool_fn, action="list", from_date="2026-05-04 00:00", to_date="2026-05-04 23:59")
        assert r["count"] == 2

    def test_list_limit(self, tool_fn, user_token):
        self._seed(tool_fn)
        r = call(tool_fn, action="list", limit=2)
        assert r["count"] == 2
        assert r["total_matching"] == 4

    def test_get_by_id(self, tool_fn, user_token):
        self._seed(tool_fn)
        listed = call(tool_fn, action="list")
        first_id = listed["trades"][0]["id"]
        r = call(tool_fn, action="get", id=first_id)
        assert r["trade"]["id"] == first_id

    def test_aggregate_uses_full_window_not_list_limit(self, tool_fn, user_token):
        for i in range(60):
            call(
                tool_fn,
                action="add",
                symbol="INTC",
                order_type="Calls Bought",
                strike="120C",
                expiry="2026-06-18",
                contracts=1000 + i,
                trade_date="2026-05-20",
            )
        call(
            tool_fn,
            action="add",
            symbol="INTC",
            order_type="Puts Bought",
            strike="90P",
            expiry="2027-01-15",
            contracts=3000,
            trade_date="2026-05-20",
        )
        for i in range(3):
            call(
                tool_fn,
                action="add",
                symbol="NVDA",
                order_type="Calls Bought",
                strike="250C",
                expiry="2026-06-18",
                contracts=2000,
                trade_date="2026-05-20",
            )

        listed = call(tool_fn, action="list", limit=50)
        assert listed["count"] == 50

        aggregate = call(tool_fn, action="aggregate")
        assert aggregate["success"] is True
        assert aggregate["summary"]["rows"] == 64
        assert aggregate["periods"]["day"]["summary"]["contracts"] == sum(1000 + i for i in range(60)) + 3000 + 6000
        assert aggregate["periods"]["day"]["bullishLeaders"][0]["symbol"] == "INTC"
        assert aggregate["periods"]["day"]["bullishLeaders"][0]["bullish_score"] == 60
        assert aggregate["periods"]["day"]["bullishLeaders"][0]["bearish_score"] == 1
        assert aggregate["shortBullishSlams"][0]["symbol"] == "INTC"

    def test_signals_simple_directional_scoring_and_cumulative_net(self, tool_fn, user_token):
        for order_type, day in [
            ("Calls Bought", "2026-05-18"),
            ("Puts Sold", "2026-05-18"),
            ("Puts Bought", "2026-05-19"),
            ("Calls Bought", "2026-05-20"),
        ]:
            call(
                tool_fn,
                action="add",
                symbol="INTC",
                order_type=order_type,
                strike="120C" if "Call" in order_type else "90P",
                expiry="2027-01-15",
                contracts=1000,
                trade_date=day,
            )
        call(
            tool_fn,
            action="add",
            symbol="NVDA",
            order_type="Puts Bought",
            strike="170P",
            expiry="2027-01-15",
            contracts=2000,
            trade_date="2026-05-20",
        )

        signals = call(tool_fn, action="signals", from_date="2026-05-18", to_date="2026-05-20")
        intc_days = [x for x in signals["daily"] if x["symbol"] == "INTC"]
        assert [x["net_score"] for x in intc_days] == [2, -1, 1]
        assert [x["cumulative_net"] for x in intc_days] == [2, 1, 2]

        intc = next(x for x in signals["symbols"] if x["symbol"] == "INTC")
        assert intc["cumulative_net"] == 2
        assert intc["seven_day"]["bullish_points"] == 3
        assert intc["seven_day"]["bearish_points"] == 1
        assert intc["seven_day"]["net"] == 2

        nvda = next(x for x in signals["symbols"] if x["symbol"] == "NVDA")
        assert nvda["cumulative_net"] == -1
        assert signals["topBearish"][0]["symbol"] == "NVDA"

    def test_signals_weekly_buckets_over_explicit_range(self, tool_fn, user_token):
        for order_type, day in [
            ("Calls Bought", "2026-05-04"),
            ("Puts Sold", "2026-05-06"),
            ("Puts Bought", "2026-05-12"),
            ("Calls Bought", "2026-05-20"),
        ]:
            call(
                tool_fn,
                action="add",
                symbol="INTC",
                order_type=order_type,
                strike="120C" if "Call" in order_type else "90P",
                expiry="2027-01-15",
                contracts=1000,
                trade_date=day,
            )

        signals = call(tool_fn, action="signals", symbol="INTC", from_date="2026-05-01", to_date="2026-05-21", bucket="week")
        assert signals["range"] == {"startDate": "2026-05-01", "endDate": "2026-05-21", "bucket": "week"}
        buckets = signals["buckets"]
        assert [(x["period_start"], x["net_score"], x["range_cumulative_net"], x["cumulative_net"]) for x in buckets] == [
            ("2026-05-04", 2, 2, 2),
            ("2026-05-11", -1, 1, 1),
            ("2026-05-18", 1, 2, 2),
        ]


class TestOptionFlowMutations:

    def _add(self, fn):
        return call(
            fn,
            action="add",
            symbol="AMZN",
            order_type="Calls Bought",
            strike="270C",
            expiry="2026-06-05",
            contracts=5000,
            trade_date="2026-05-04 10:37",
        )

    def test_update(self, tool_fn, user_token):
        added = self._add(tool_fn)
        tid = added["trade"]["id"]
        r = call(tool_fn, action="update", id=tid, contracts=7500, notes="big")
        assert r["trade"]["contracts"] == 7500
        assert r["trade"]["notes"] == "big"
        # Other fields preserved
        assert r["trade"]["symbol"] == "AMZN"

    def test_update_invalid_order_type(self, tool_fn, user_token):
        tid = self._add(tool_fn)["trade"]["id"]
        r = call(tool_fn, action="update", id=tid, order_type="bogus")
        assert "error" in r

    def test_remove(self, tool_fn, user_token):
        tid = self._add(tool_fn)["trade"]["id"]
        r = call(tool_fn, action="remove", id=tid)
        assert r["success"] is True
        # Now gone
        gone = call(tool_fn, action="get", id=tid)
        assert "error" in gone

    def test_remove_unknown(self, tool_fn, user_token):
        r = call(tool_fn, action="remove", id=99999)
        assert "error" in r


class TestOptionFlowIsolation:

    def test_users_dont_see_each_others_trades(self, tool_fn):
        # Insert as user A
        tok_a = users_mod.current_user_token.set("user-A")
        call(
            tool_fn,
            action="add",
            symbol="AMZN",
            order_type="Calls Bought",
            strike="270C",
            expiry="2026-06-05",
            contracts=5000,
            trade_date="2026-05-04 10:37",
        )
        users_mod.current_user_token.reset(tok_a)

        # Switch to user B — should see nothing
        tok_b = users_mod.current_user_token.set("user-B")
        try:
            r = call(tool_fn, action="list")
            assert r["count"] == 0
        finally:
            users_mod.current_user_token.reset(tok_b)


class TestOptionFlowClear:

    def test_clear_requires_confirm(self, tool_fn, user_token):
        call(
            tool_fn,
            action="add",
            symbol="AMZN",
            order_type="Calls Bought",
            strike="270C",
            expiry="2026-06-05",
            contracts=5000,
            trade_date="2026-05-04 10:37",
        )
        r = call(tool_fn, action="clear")
        assert "error" in r
        # Still there
        assert call(tool_fn, action="list")["count"] == 1

    def test_clear_with_confirm(self, tool_fn, user_token):
        call(
            tool_fn,
            action="add",
            symbol="AMZN",
            order_type="Calls Bought",
            strike="270C",
            expiry="2026-06-05",
            contracts=5000,
            trade_date="2026-05-04 10:37",
        )
        r = call(tool_fn, action="clear", source="CONFIRM_DELETE_ALL")
        assert r["deleted"] == 1
        assert call(tool_fn, action="list")["count"] == 0


class TestOptionFlowGlobalRows:

    def test_all_users_can_see_synced_global_rows(self, tool_fn):
        with db_mod.connect() as c:
            c.execute(
                """INSERT INTO option_flow
                   (user_token, trade_date, order_type, symbol, strike, expiry, contracts, source, sync_key)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    "__global__",
                    "2026-05-08",
                    "Puts Sold",
                    "WOLF",
                    "45.0",
                    "2026-06-18",
                    900,
                    "jamesbulltard",
                    "global-row-1",
                ),
            )

        tok_a = users_mod.current_user_token.set("user-A")
        try:
            a = call(tool_fn, action="list", symbol="WOLF")
            assert a["count"] == 1
            assert a["trades"][0]["user_token"] == "__global__"
            global_id = a["trades"][0]["id"]
            got = call(tool_fn, action="get", id=global_id)
            assert got["trade"]["symbol"] == "WOLF"
        finally:
            users_mod.current_user_token.reset(tok_a)

        tok_b = users_mod.current_user_token.set("user-B")
        try:
            b = call(tool_fn, action="list", symbol="WOLF")
            assert b["count"] == 1
            assert b["trades"][0]["source"] == "jamesbulltard"
        finally:
            users_mod.current_user_token.reset(tok_b)

    def test_user_clear_does_not_delete_global_rows(self, tool_fn, user_token):
        call(
            tool_fn,
            action="add",
            symbol="AMZN",
            order_type="Calls Bought",
            strike="270C",
            expiry="2026-06-05",
            contracts=5000,
            trade_date="2026-05-04 10:37",
        )
        with db_mod.connect() as c:
            c.execute(
                """INSERT INTO option_flow
                   (user_token, trade_date, order_type, symbol, strike, expiry, contracts, source, sync_key)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    "__global__",
                    "2026-05-08",
                    "Puts Sold",
                    "WOLF",
                    "45.0",
                    "2026-06-18",
                    900,
                    "jamesbulltard",
                    "global-row-1",
                ),
            )

        r = call(tool_fn, action="clear", source="CONFIRM_DELETE_ALL")
        assert r["deleted"] == 1
        remaining = call(tool_fn, action="list")
        assert remaining["count"] == 1
        assert remaining["trades"][0]["user_token"] == "__global__"
