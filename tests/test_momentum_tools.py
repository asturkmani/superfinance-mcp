"""Tests for momentum_group_scan and momentum_stock_scan tools."""

import json
import sys
from pathlib import Path

import pandas as pd
from fastmcp import FastMCP

sys.path.insert(0, str(Path(__file__).parent.parent))

from tools.v2_momentum import register_momentum_v2  # noqa: E402


def _make_tools():
    server = FastMCP("test")
    register_momentum_v2(server)
    tools = {}
    for t in server._tool_manager._tools.values():
        tools[t.name] = t.fn
    assert "momentum_group_scan" in tools
    assert "momentum_stock_scan" in tools
    return tools


def _json_call(fn, **kwargs):
    return json.loads(fn(**kwargs))


class _FakeGroupPerf:
    def screener_view(self, group, order):
        assert group in {"Industry", "Sector"}
        assert order == "Performance (Quarter)"
        return pd.DataFrame(
            [
                {"Name": "Computer Hardware", "Perf Week": "3.00%", "Perf Month": 0.10, "Perf Quart": 0.30, "Perf Half": 0.60, "Perf Year": 1.00, "Perf YTD": 0.20},
                {"Name": "Oil & Gas Drilling", "Perf Week": "2.00%", "Perf Month": 0.12, "Perf Quart": 0.18, "Perf Half": 0.55, "Perf Year": 0.90, "Perf YTD": 0.15},
            ]
        )


class _FakeStockPerf:
    def set_filter(self, filters_dict):
        self.filters = filters_dict

    def screener_view(self):
        return pd.DataFrame(
            [
                {"Ticker": "AAA", "Perf Week": "2.0%", "Perf Month": 0.10, "Perf Quart": 0.20, "Perf Half": 0.30, "Perf Year": 0.40, "Price": 55.2, "Avg Volume": 1500000},
                {"Ticker": "BBB", "Perf Week": "1.0%", "Perf Month": 0.05, "Perf Quart": 0.08, "Perf Half": 0.10, "Perf Year": 0.12, "Price": 12.7, "Avg Volume": 600000},
            ]
        )


def test_group_scan_success(monkeypatch):
    tools = _make_tools()
    monkeypatch.setattr("tools.v2_momentum.GroupPerf", _FakeGroupPerf)
    r = _json_call(tools["momentum_group_scan"], group="Industry", limit=2, sort_by="score")
    assert r["success"] is True
    assert r["count"] == 2
    assert r["items"][0]["name"] == "Computer Hardware"
    assert r["items"][0]["score"] > r["items"][1]["score"]


def test_group_scan_invalid_group():
    tools = _make_tools()
    r = _json_call(tools["momentum_group_scan"], group="Theme")
    assert "error" in r
    assert "valid_group_options" in r


def test_stock_scan_success(monkeypatch):
    tools = _make_tools()
    monkeypatch.setattr("tools.v2_momentum.StockPerf", _FakeStockPerf)
    r = _json_call(
        tools["momentum_stock_scan"],
        industry="Oil & Gas Drilling",
        market_cap="large",
        min_price=5,
        min_avg_volume=500000,
        limit=5,
    )
    assert r["success"] is True
    assert r["count"] == 2
    assert r["filters_applied"]["Industry"] == "Oil & Gas Drilling"
    assert "Market Cap." in r["filters_applied"]


def test_stock_scan_requires_exactly_one_group_filter():
    tools = _make_tools()
    r = _json_call(tools["momentum_stock_scan"], industry="X", sector="Y")
    assert "error" in r

