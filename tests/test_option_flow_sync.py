"""Tests for admin option-flow ingestion/sync."""

import json
import sys
from pathlib import Path

import pytest
from starlette.applications import Starlette
from starlette.routing import Route
from starlette.testclient import TestClient

sys.path.insert(0, str(Path(__file__).parent.parent))

import db as db_mod  # noqa: E402
from option_flow_sync import option_flow_sync_handler, upsert_option_flow_rows  # noqa: E402


@pytest.fixture()
def fresh_db(tmp_path):
    old_data = db_mod._DATA_DIR
    old_db = db_mod._DB_PATH
    db_mod._DATA_DIR = tmp_path
    db_mod._DB_PATH = tmp_path / "test.db"
    db_mod.init_db()
    yield tmp_path
    db_mod._DATA_DIR = old_data
    db_mod._DB_PATH = old_db


@pytest.fixture()
def sample_rows():
    return [
        {
            "trade_datetime": "2026-05-08 10:12:00",
            "trade_date": "2026-05-08",
            "order_type": "Puts Sold",
            "action": "sold",
            "symbol": "wolf",
            "strike": 45.0,
            "option_type": "P",
            "strike_label": "45P",
            "expiry": "2026-06-18",
            "contracts": 900,
            "source": "jamesbulltard",
            "source_page": "/daily_option_trades",
            "raw_json": {"example": True},
            "imported_at": "2026-05-13T08:51:46Z",
        },
        {
            "trade_datetime": "2026-05-07 11:00:00",
            "trade_date": "2026-05-07",
            "order_type": "Calls Bought",
            "action": "bought",
            "symbol": "NVTS",
            "strike": "17",
            "option_type": "C",
            "strike_label": "17C",
            "expiry": "2026-06-18",
            "contracts": 6000,
            "source": "jamesbulltard",
        },
    ]


def test_upsert_inserts_normalized_rows(fresh_db, sample_rows):
    result = upsert_option_flow_rows(sample_rows)
    assert result == {"received": 2, "inserted": 2, "updated": 0, "errors": []}

    with db_mod.connect() as c:
        rows = c.execute("SELECT * FROM option_flow ORDER BY trade_date DESC").fetchall()
    assert len(rows) == 2
    assert rows[0]["symbol"] == "WOLF"
    assert rows[0]["strike"] == "45.0"
    assert rows[0]["option_type"] == "P"
    assert rows[0]["source"] == "jamesbulltard"
    assert json.loads(rows[0]["raw_json"]) == {"example": True}
    assert rows[0]["sync_key"]


def test_upsert_is_idempotent_and_updates_existing(fresh_db, sample_rows):
    first = upsert_option_flow_rows(sample_rows)
    assert first["inserted"] == 2

    changed = [dict(sample_rows[0], contracts=950, notes="revised")]
    second = upsert_option_flow_rows(changed)
    assert second == {"received": 1, "inserted": 0, "updated": 1, "errors": []}

    with db_mod.connect() as c:
        rows = c.execute(
            "SELECT symbol, contracts, notes FROM option_flow ORDER BY symbol"
        ).fetchall()
    assert len(rows) == 2
    wolf = [r for r in rows if r["symbol"] == "WOLF"][0]
    assert wolf["contracts"] == 950
    assert wolf["notes"] == "revised"


def test_upsert_uses_global_namespace(fresh_db, sample_rows):
    upsert_option_flow_rows([sample_rows[0]])
    upsert_option_flow_rows([sample_rows[0]])
    with db_mod.connect() as c:
        row = c.execute("SELECT user_token, COUNT(*) AS n FROM option_flow").fetchone()
    assert row["user_token"] == "__global__"
    assert row["n"] == 1


def test_upsert_returns_row_errors_without_aborting(fresh_db, sample_rows):
    result = upsert_option_flow_rows([sample_rows[0], {"symbol": "BAD"}])
    assert result["inserted"] == 1
    assert result["received"] == 2
    assert len(result["errors"]) == 1
    assert result["errors"][0]["index"] == 1


@pytest.fixture()
def client(fresh_db, monkeypatch):
    monkeypatch.setenv("OPTION_FLOW_SYNC_TOKEN", "secret-admin-token")
    app = Starlette(
        routes=[Route("/admin/option-flow/sync", option_flow_sync_handler, methods=["POST"])]
    )
    return TestClient(app)


def test_sync_endpoint_requires_bearer_token(client, sample_rows):
    r = client.post("/admin/option-flow/sync", json={"rows": sample_rows})
    assert r.status_code == 401


def test_sync_endpoint_ingests_rows(client, sample_rows):
    r = client.post(
        "/admin/option-flow/sync",
        headers={"Authorization": "Bearer secret-admin-token"},
        json={"rows": sample_rows},
    )
    assert r.status_code == 200
    assert r.json()["inserted"] == 2


def test_sync_endpoint_ignores_user_token_and_writes_global(client, sample_rows):
    r = client.post(
        "/admin/option-flow/sync",
        headers={"Authorization": "Bearer secret-admin-token"},
        json={"user_token": "ignored-user", "rows": [sample_rows[0]]},
    )
    assert r.status_code == 200
    with db_mod.connect() as c:
        row = c.execute("SELECT user_token FROM option_flow").fetchone()
    assert row["user_token"] == "__global__"
