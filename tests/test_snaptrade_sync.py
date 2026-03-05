"""Tests for SnapTrade sync functionality."""

import os
import tempfile
import pytest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, patch, MagicMock

from services.snaptrade_service import SnapTradeService
from db import queries


@pytest.fixture
def test_db():
    """Create a temporary test database."""
    with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.db') as f:
        db_path = f.name
    
    os.environ['SUPERFINANCE_DB_PATH'] = db_path
    
    yield db_path
    
    # Cleanup
    if os.path.exists(db_path):
        os.unlink(db_path)


@pytest.fixture
def mock_snaptrade_client():
    """Mock SnapTrade client."""
    with patch("services.snaptrade_service.get_snaptrade_client") as mock:
        client = MagicMock()
        mock.return_value = client
        yield client


@pytest.fixture
def vault_user_id(test_db):
    """Create a test user."""
    return queries.create_user("test@vault.local", "Test User")


def test_sync_creates_accounts_with_snaptrade_id(test_db, vault_user_id, mock_snaptrade_client):
    """Test that sync creates accounts with SnapTrade account ID (not random ID)."""
    
    # Mock SnapTrade responses
    mock_accounts = [
        {
            "account_id": "snaptrade-account-123",
            "name": "Test Brokerage Account",
            "institution": "Test Brokerage",
            "brokerage_authorization": "auth-456",
            "meta": {"type": "brokerage"},
            "balance": {"currency": "USD"}
        }
    ]
    
    mock_holdings = {
        "success": True,
        "positions": []
    }
    
    async def mock_list_accounts(*args, **kwargs):
        return {"success": True, "accounts": mock_accounts}
    
    async def mock_get_holdings(*args, **kwargs):
        return mock_holdings
    
    async def mock_get_option_positions(*args, **kwargs):
        return {"success": True, "option_positions": []}
    
    async def mock_get_account_balances(*args, **kwargs):
        return {"success": True, "balances": []}
    
    async def mock_get_transactions(*args, **kwargs):
        return {"success": True, "transactions": []}
    
    with patch.object(SnapTradeService, "list_accounts", new=mock_list_accounts), \
         patch.object(SnapTradeService, "get_holdings", new=mock_get_holdings), \
         patch.object(SnapTradeService, "get_option_positions", new=mock_get_option_positions), \
         patch.object(SnapTradeService, "get_account_balances", new=mock_get_account_balances), \
         patch.object(SnapTradeService, "get_transactions", new=mock_get_transactions):
        
        # Run sync
        import asyncio
        result = asyncio.run(SnapTradeService.sync_to_db(
            vault_user_id=vault_user_id,
            snaptrade_user_id="test_user",
            snaptrade_user_secret="test_secret"
        ))
        
        assert result["success"] is True
        assert result["synced_accounts"] == 1
        
        # Verify account was created with SnapTrade ID
        account = queries.get_account("snaptrade-account-123")
        assert account is not None
        assert account["id"] == "snaptrade-account-123"
        assert account["name"] == "Test Brokerage Account"
        assert account["user_id"] == vault_user_id


def test_sync_creates_brokerage_and_connection(test_db, vault_user_id, mock_snaptrade_client):
    """Test that sync creates brokerage and connection records."""
    
    mock_accounts = [
        {
            "account_id": "snap-acc-1",
            "name": "Schwab Account",
            "institution": "Charles Schwab",
            "brokerage_authorization": "auth-789",
            "meta": {},
            "balance": None
        }
    ]
    
    async def mock_list_accounts(*args, **kwargs):
        return {"success": True, "accounts": mock_accounts}
    
    async def mock_get_holdings(*args, **kwargs):
        return {"success": True, "positions": []}
    
    async def mock_get_option_positions(*args, **kwargs):
        return {"success": True, "option_positions": []}
    
    async def mock_get_account_balances(*args, **kwargs):
        return {"success": True, "balances": []}
    
    async def mock_get_transactions(*args, **kwargs):
        return {"success": True, "transactions": []}
    
    with patch.object(SnapTradeService, "list_accounts", new=mock_list_accounts), \
         patch.object(SnapTradeService, "get_holdings", new=mock_get_holdings), \
         patch.object(SnapTradeService, "get_option_positions", new=mock_get_option_positions), \
         patch.object(SnapTradeService, "get_account_balances", new=mock_get_account_balances), \
         patch.object(SnapTradeService, "get_transactions", new=mock_get_transactions):
        
        import asyncio
        result = asyncio.run(SnapTradeService.sync_to_db(
            vault_user_id=vault_user_id,
            snaptrade_user_id="test_user",
            snaptrade_user_secret="test_secret"
        ))
        
        assert result["success"] is True
        
        # Verify brokerage was created
        from db.database import get_db
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM brokerages 
            WHERE provider = 'snaptrade' AND provider_institution_id = 'Charles Schwab'
        """)
        brokerage = cursor.fetchone()
        assert brokerage is not None
        
        # Verify connection was created
        connection = queries.get_connection_by_provider_account_id("auth-789")
        assert connection is not None
        assert connection["user_id"] == vault_user_id
        assert connection["provider_account_id"] == "auth-789"
        assert connection["status"] == "active"
        
        # Verify account is linked to connection
        account = queries.get_account("snap-acc-1")
        assert account is not None
        assert account["connection_id"] == connection["id"]


def test_sync_persists_transactions(test_db, vault_user_id, mock_snaptrade_client):
    """Test that sync persists transactions with external_id dedup."""
    
    mock_accounts = [
        {
            "account_id": "snap-acc-txn",
            "name": "Test Account",
            "institution": "Test Broker",
            "brokerage_authorization": "auth-txn",
            "meta": {},
            "balance": None
        }
    ]
    
    mock_transactions = [
        {
            "id": "txn-001",
            "symbol": "AAPL",
            "symbol_description": "Apple Inc.",
            "type": "BUY",
            "trade_date": "2024-01-15",
            "units": 10.0,
            "price": 150.0,
            "amount": -1500.0,
            "fee": 1.0,
            "currency": "USD",
            "is_option": False
        },
        {
            "id": "txn-002",
            "symbol": "MSFT",
            "symbol_description": "Microsoft Corp.",
            "type": "SELL",
            "trade_date": "2024-01-20",
            "units": 5.0,
            "price": 300.0,
            "amount": 1500.0,
            "fee": 1.0,
            "currency": "USD",
            "is_option": False
        }
    ]
    
    async def mock_list_accounts(*args, **kwargs):
        return {"success": True, "accounts": mock_accounts}
    
    async def mock_get_holdings(*args, **kwargs):
        return {"success": True, "positions": []}
    
    async def mock_get_option_positions(*args, **kwargs):
        return {"success": True, "option_positions": []}
    
    async def mock_get_account_balances(*args, **kwargs):
        return {"success": True, "balances": []}
    
    async def mock_get_transactions(*args, **kwargs):
        return {"success": True, "transactions": mock_transactions}
    
    with patch.object(SnapTradeService, "list_accounts", new=mock_list_accounts), \
         patch.object(SnapTradeService, "get_holdings", new=mock_get_holdings), \
         patch.object(SnapTradeService, "get_option_positions", new=mock_get_option_positions), \
         patch.object(SnapTradeService, "get_account_balances", new=mock_get_account_balances), \
         patch.object(SnapTradeService, "get_transactions", new=mock_get_transactions):
        
        import asyncio
        result = asyncio.run(SnapTradeService.sync_to_db(
            vault_user_id=vault_user_id,
            snaptrade_user_id="test_user",
            snaptrade_user_secret="test_secret"
        ))
        
        assert result["success"] is True
        assert result["synced_transactions"] == 2
        
        # Verify transactions were created
        txns = queries.get_transactions_for_account("snap-acc-txn")
        assert len(txns) == 2
        
        # Verify transaction details
        aapl_txn = next((t for t in txns if t["symbol"] == "AAPL"), None)
        assert aapl_txn is not None
        assert aapl_txn["transaction_type"] == "buy"
        assert aapl_txn["quantity"] == 10.0
        assert aapl_txn["price"] == 150.0
        assert aapl_txn["external_id"] == "txn-001"
        assert aapl_txn["source"] == "snaptrade"


def test_transaction_dedup(test_db, vault_user_id, mock_snaptrade_client):
    """Test that running sync twice doesn't create duplicate transactions."""
    
    mock_accounts = [
        {
            "account_id": "snap-acc-dedup",
            "name": "Dedup Test Account",
            "institution": "Test Broker",
            "brokerage_authorization": "auth-dedup",
            "meta": {},
            "balance": None
        }
    ]
    
    mock_transactions = [
        {
            "id": "txn-dedup-001",
            "symbol": "GOOGL",
            "symbol_description": "Alphabet Inc.",
            "type": "BUY",
            "trade_date": "2024-01-10",
            "units": 3.0,
            "price": 140.0,
            "amount": -420.0,
            "fee": 0.5,
            "currency": "USD",
            "is_option": False
        }
    ]
    
    async def mock_list_accounts(*args, **kwargs):
        return {"success": True, "accounts": mock_accounts}
    
    async def mock_get_holdings(*args, **kwargs):
        return {"success": True, "positions": []}
    
    async def mock_get_option_positions(*args, **kwargs):
        return {"success": True, "option_positions": []}
    
    async def mock_get_account_balances(*args, **kwargs):
        return {"success": True, "balances": []}
    
    async def mock_get_transactions(*args, **kwargs):
        return {"success": True, "transactions": mock_transactions}
    
    with patch.object(SnapTradeService, "list_accounts", new=mock_list_accounts), \
         patch.object(SnapTradeService, "get_holdings", new=mock_get_holdings), \
         patch.object(SnapTradeService, "get_option_positions", new=mock_get_option_positions), \
         patch.object(SnapTradeService, "get_account_balances", new=mock_get_account_balances), \
         patch.object(SnapTradeService, "get_transactions", new=mock_get_transactions):
        
        import asyncio
        
        # First sync
        result1 = asyncio.run(SnapTradeService.sync_to_db(
            vault_user_id=vault_user_id,
            snaptrade_user_id="test_user",
            snaptrade_user_secret="test_secret"
        ))
        assert result1["success"] is True
        assert result1["synced_transactions"] == 1
        
        # Second sync (should deduplicate)
        result2 = asyncio.run(SnapTradeService.sync_to_db(
            vault_user_id=vault_user_id,
            snaptrade_user_id="test_user",
            snaptrade_user_secret="test_secret"
        ))
        assert result2["success"] is True
        # Still reports 1 synced because it attempted to sync 1 transaction
        assert result2["synced_transactions"] == 1
        
        # Verify only one transaction exists
        txns = queries.get_transactions_for_account("snap-acc-dedup")
        assert len(txns) == 1
        assert txns[0]["external_id"] == "txn-dedup-001"


def test_sync_removes_stale_holdings(test_db, vault_user_id, mock_snaptrade_client):
    """Test that sold positions get cleaned up during sync."""
    
    mock_accounts = [
        {
            "account_id": "snap-acc-stale",
            "name": "Stale Test Account",
            "institution": "Test Broker",
            "brokerage_authorization": "auth-stale",
            "meta": {},
            "balance": None
        }
    ]
    
    # First sync has AAPL and MSFT
    initial_holdings = {
        "success": True,
        "positions": [
            {
                "symbol": "AAPL",
                "description": "Apple Inc.",
                "units": 10.0,
                "price": 150.0,
                "currency": "USD"
            },
            {
                "symbol": "MSFT",
                "description": "Microsoft Corp.",
                "units": 5.0,
                "price": 300.0,
                "currency": "USD"
            }
        ]
    }
    
    # Second sync only has AAPL (MSFT was sold)
    updated_holdings = {
        "success": True,
        "positions": [
            {
                "symbol": "AAPL",
                "description": "Apple Inc.",
                "units": 15.0,  # bought more
                "price": 155.0,
                "currency": "USD"
            }
        ]
    }
    
    async def mock_list_accounts(*args, **kwargs):
        return {"success": True, "accounts": mock_accounts}
    
    async def mock_get_option_positions(*args, **kwargs):
        return {"success": True, "option_positions": []}
    
    async def mock_get_account_balances(*args, **kwargs):
        return {"success": True, "balances": []}
    
    async def mock_get_transactions(*args, **kwargs):
        return {"success": True, "transactions": []}
    
    with patch.object(SnapTradeService, "list_accounts", new=mock_list_accounts), \
         patch.object(SnapTradeService, "get_option_positions", new=mock_get_option_positions), \
         patch.object(SnapTradeService, "get_account_balances", new=mock_get_account_balances), \
         patch.object(SnapTradeService, "get_transactions", new=mock_get_transactions):
        
        import asyncio
        
        # First sync - create initial holdings
        with patch.object(SnapTradeService, "get_holdings", new=AsyncMock(return_value=initial_holdings)):
            result1 = asyncio.run(SnapTradeService.sync_to_db(
                vault_user_id=vault_user_id,
                snaptrade_user_id="test_user",
                snaptrade_user_secret="test_secret"
            ))
            assert result1["success"] is True
            assert result1["synced_holdings"] == 2
        
        # Verify both holdings exist
        holdings = queries.get_holdings_for_account("snap-acc-stale")
        assert len(holdings) == 2
        symbols = {h["symbol"] for h in holdings}
        assert symbols == {"AAPL", "MSFT"}
        
        # Second sync - MSFT was sold
        with patch.object(SnapTradeService, "get_holdings", new=AsyncMock(return_value=updated_holdings)):
            result2 = asyncio.run(SnapTradeService.sync_to_db(
                vault_user_id=vault_user_id,
                snaptrade_user_id="test_user",
                snaptrade_user_secret="test_secret"
            ))
            assert result2["success"] is True
            assert result2["synced_holdings"] == 1
            assert result2["cleaned_stale_holdings"] == 1  # MSFT removed
        
        # Verify only AAPL remains
        holdings = queries.get_holdings_for_account("snap-acc-stale")
        assert len(holdings) == 1
        assert holdings[0]["symbol"] == "AAPL"
        assert holdings[0]["quantity"] == 15.0  # updated quantity


def test_sync_computes_market_value(test_db, vault_user_id, mock_snaptrade_client):
    """Test that market_value is computed as quantity * price."""
    
    mock_accounts = [
        {
            "account_id": "snap-acc-value",
            "name": "Value Test Account",
            "institution": "Test Broker",
            "brokerage_authorization": "auth-value",
            "meta": {},
            "balance": None
        }
    ]
    
    mock_holdings = {
        "success": True,
        "positions": [
            {
                "symbol": "TSLA",
                "description": "Tesla Inc.",
                "units": 8.5,
                "price": 250.75,
                "open_pnl": 100.0,  # for average_cost calculation
                "currency": "USD"
            }
        ]
    }
    
    async def mock_list_accounts(*args, **kwargs):
        return {"success": True, "accounts": mock_accounts}
    
    async def mock_get_holdings(*args, **kwargs):
        return mock_holdings
    
    async def mock_get_option_positions(*args, **kwargs):
        return {"success": True, "option_positions": []}
    
    async def mock_get_account_balances(*args, **kwargs):
        return {"success": True, "balances": []}
    
    async def mock_get_transactions(*args, **kwargs):
        return {"success": True, "transactions": []}
    
    with patch.object(SnapTradeService, "list_accounts", new=mock_list_accounts), \
         patch.object(SnapTradeService, "get_holdings", new=mock_get_holdings), \
         patch.object(SnapTradeService, "get_option_positions", new=mock_get_option_positions), \
         patch.object(SnapTradeService, "get_account_balances", new=mock_get_account_balances), \
         patch.object(SnapTradeService, "get_transactions", new=mock_get_transactions):
        
        import asyncio
        result = asyncio.run(SnapTradeService.sync_to_db(
            vault_user_id=vault_user_id,
            snaptrade_user_id="test_user",
            snaptrade_user_secret="test_secret"
        ))
        
        assert result["success"] is True
        assert result["synced_holdings"] == 1
        
        # Verify market_value was computed
        holdings = queries.get_holdings_for_account("snap-acc-value")
        assert len(holdings) == 1
        
        holding = holdings[0]
        assert holding["symbol"] == "TSLA"
        assert holding["quantity"] == 8.5
        assert holding["current_price"] == 250.75
        
        # market_value = quantity * price = 8.5 * 250.75 = 2131.375
        assert holding["market_value"] is not None
        assert abs(holding["market_value"] - 2131.375) < 0.01
        
        # average_cost should be computed from open_pnl
        # open_pnl = (current_price - average_cost) * quantity
        # 100 = (250.75 - average_cost) * 8.5
        # average_cost = 250.75 - (100 / 8.5) = 250.75 - 11.76 = 238.99
        assert holding["average_cost"] is not None
        expected_avg_cost = 250.75 - (100.0 / 8.5)
        assert abs(holding["average_cost"] - expected_avg_cost) < 0.01


def test_sync_extracts_account_metadata(test_db, vault_user_id, mock_snaptrade_client):
    """Test that account metadata (type, currency) is extracted."""
    
    mock_accounts = [
        {
            "account_id": "snap-acc-meta",
            "name": "Retirement Account",
            "institution": "Fidelity",
            "brokerage_authorization": "auth-meta",
            "meta": {"type": "retirement"},
            "balance": {"currency": "CAD"}
        }
    ]
    
    async def mock_list_accounts(*args, **kwargs):
        return {"success": True, "accounts": mock_accounts}
    
    async def mock_get_holdings(*args, **kwargs):
        return {"success": True, "positions": []}
    
    async def mock_get_option_positions(*args, **kwargs):
        return {"success": True, "option_positions": []}
    
    async def mock_get_account_balances(*args, **kwargs):
        return {"success": True, "balances": []}
    
    async def mock_get_transactions(*args, **kwargs):
        return {"success": True, "transactions": []}
    
    with patch.object(SnapTradeService, "list_accounts", new=mock_list_accounts), \
         patch.object(SnapTradeService, "get_holdings", new=mock_get_holdings), \
         patch.object(SnapTradeService, "get_option_positions", new=mock_get_option_positions), \
         patch.object(SnapTradeService, "get_account_balances", new=mock_get_account_balances), \
         patch.object(SnapTradeService, "get_transactions", new=mock_get_transactions):
        
        import asyncio
        result = asyncio.run(SnapTradeService.sync_to_db(
            vault_user_id=vault_user_id,
            snaptrade_user_id="test_user",
            snaptrade_user_secret="test_secret"
        ))
        
        assert result["success"] is True
        
        # Verify account metadata was extracted
        account = queries.get_account("snap-acc-meta")
        assert account is not None
        assert account["account_type"] == "retirement"
        assert account["currency"] == "CAD"


def test_option_position_parsing(test_db, vault_user_id, mock_snaptrade_client):
    """Test that option positions are parsed with correct symbol format."""
    
    mock_accounts = [
        {
            "account_id": "snap-acc-opts",
            "name": "Options Account",
            "institution": "Test Broker",
            "brokerage_authorization": "auth-opts",
            "meta": {},
            "balance": None
        }
    ]
    
    mock_option_positions = {
        "success": True,
        "option_positions": [
            {
                "symbol": {
                    "option_symbol": {
                        "underlying_symbol": {"symbol": "INTC"},
                        "strike_price": 58.0,
                        "option_type": "CALL",
                        "expiration_date": "2026-01-30",
                        "ticker": "INTC 58 C 2026-01-30",
                        "is_mini_option": False
                    },
                    "currency": {"code": "USD"}
                },
                "units": 2.0,
                "price": 1.50,
                "open_pnl": 50.0
            },
            {
                "symbol": {
                    "option_symbol": {
                        "underlying_symbol": {"symbol": "SIL"},
                        "strike_price": 100.0,
                        "option_type": "PUT",
                        "expiration_date": "2027-01-15",
                        "ticker": None,  # No pre-formatted ticker
                        "is_mini_option": True  # Mini option
                    },
                    "currency": {"code": "USD"}
                },
                "units": 5.0,
                "price": 2.25
            }
        ]
    }
    
    async def mock_list_accounts(*args, **kwargs):
        return {"success": True, "accounts": mock_accounts}
    
    async def mock_get_holdings(*args, **kwargs):
        return {"success": True, "positions": []}
    
    async def mock_get_option_positions(*args, **kwargs):
        return mock_option_positions
    
    async def mock_get_account_balances(*args, **kwargs):
        return {"success": True, "balances": []}
    
    async def mock_get_transactions(*args, **kwargs):
        return {"success": True, "transactions": []}
    
    with patch.object(SnapTradeService, "list_accounts", new=mock_list_accounts), \
         patch.object(SnapTradeService, "get_holdings", new=mock_get_holdings), \
         patch.object(SnapTradeService, "get_option_positions", new=mock_get_option_positions), \
         patch.object(SnapTradeService, "get_account_balances", new=mock_get_account_balances), \
         patch.object(SnapTradeService, "get_transactions", new=mock_get_transactions):
        
        import asyncio
        result = asyncio.run(SnapTradeService.sync_to_db(
            vault_user_id=vault_user_id,
            snaptrade_user_id="test_user",
            snaptrade_user_secret="test_secret"
        ))
        
        assert result["success"] is True
        assert result["synced_holdings"] == 2
        
        # Verify option holdings were created
        holdings = queries.get_holdings_for_account("snap-acc-opts")
        assert len(holdings) == 2
        
        # Check INTC call option
        intc_call = next((h for h in holdings if "INTC" in h["symbol"]), None)
        assert intc_call is not None
        assert intc_call["symbol"] == "INTC 58 C 2026-01-30"
        assert intc_call["asset_type"] == "option"
        assert intc_call["quantity"] == 2.0
        assert intc_call["current_price"] == 1.50
        # Standard option: market_value = qty * price * 100
        assert intc_call["market_value"] == 2.0 * 1.50 * 100  # 300.0
        
        # Check metadata
        import json
        metadata = json.loads(intc_call["metadata"])
        assert metadata["underlying_symbol"] == "INTC"
        assert metadata["strike"] == 58.0
        assert metadata["option_type"] == "CALL"
        assert metadata["expiration_date"] == "2026-01-30"
        assert metadata["is_mini_option"] is False
        
        # Check SIL put option (mini)
        sil_put = next((h for h in holdings if "SIL" in h["symbol"]), None)
        assert sil_put is not None
        assert sil_put["symbol"] == "SIL 100 P 2027-01-15"
        assert sil_put["asset_type"] == "option"
        assert sil_put["quantity"] == 5.0
        assert sil_put["current_price"] == 2.25
        # Mini option: market_value = qty * price * 10
        assert sil_put["market_value"] == 5.0 * 2.25 * 10  # 112.5
        
        metadata = json.loads(sil_put["metadata"])
        assert metadata["is_mini_option"] is True


def test_cash_balance_parsing(test_db, vault_user_id, mock_snaptrade_client):
    """Test that cash balances become holdings."""
    
    mock_accounts = [
        {
            "account_id": "snap-acc-cash",
            "name": "Cash Account",
            "institution": "Test Broker",
            "brokerage_authorization": "auth-cash",
            "meta": {},
            "balance": None
        }
    ]
    
    mock_balances = {
        "success": True,
        "balances": [
            {
                "cash": 5000.50,
                "currency": {"code": "USD"}
            },
            {
                "cash": 1200.75,
                "currency": {"code": "CAD"}
            },
            {
                "cash": 0.0,  # Should be skipped
                "currency": {"code": "EUR"}
            }
        ]
    }
    
    async def mock_list_accounts(*args, **kwargs):
        return {"success": True, "accounts": mock_accounts}
    
    async def mock_get_holdings(*args, **kwargs):
        return {"success": True, "positions": []}
    
    async def mock_get_option_positions(*args, **kwargs):
        return {"success": True, "option_positions": []}
    
    async def mock_get_account_balances(*args, **kwargs):
        return mock_balances
    
    async def mock_get_transactions(*args, **kwargs):
        return {"success": True, "transactions": []}
    
    with patch.object(SnapTradeService, "list_accounts", new=mock_list_accounts), \
         patch.object(SnapTradeService, "get_holdings", new=mock_get_holdings), \
         patch.object(SnapTradeService, "get_option_positions", new=mock_get_option_positions), \
         patch.object(SnapTradeService, "get_account_balances", new=mock_get_account_balances), \
         patch.object(SnapTradeService, "get_transactions", new=mock_get_transactions):
        
        import asyncio
        result = asyncio.run(SnapTradeService.sync_to_db(
            vault_user_id=vault_user_id,
            snaptrade_user_id="test_user",
            snaptrade_user_secret="test_secret"
        ))
        
        assert result["success"] is True
        assert result["synced_holdings"] == 2  # USD and CAD, not EUR (zero balance)
        
        # Verify cash holdings were created
        holdings = queries.get_holdings_for_account("snap-acc-cash")
        assert len(holdings) == 2
        
        # Check USD cash
        usd_cash = next((h for h in holdings if h["symbol"] == "USD"), None)
        assert usd_cash is not None
        assert usd_cash["name"] == "USD Cash"
        assert usd_cash["asset_type"] == "cash"
        assert usd_cash["quantity"] == 5000.50
        assert usd_cash["current_price"] == 1.0
        assert usd_cash["market_value"] == 5000.50
        assert usd_cash["currency"] == "USD"
        
        # Check CAD cash
        cad_cash = next((h for h in holdings if h["symbol"] == "CAD"), None)
        assert cad_cash is not None
        assert cad_cash["name"] == "CAD Cash"
        assert cad_cash["asset_type"] == "cash"
        assert cad_cash["quantity"] == 1200.75
        assert cad_cash["market_value"] == 1200.75
        assert cad_cash["currency"] == "CAD"


def test_transaction_type_mapping(test_db, vault_user_id, mock_snaptrade_client):
    """Test that all SnapTrade types map correctly."""
    
    mock_accounts = [
        {
            "account_id": "snap-acc-types",
            "name": "Type Test Account",
            "institution": "Test Broker",
            "brokerage_authorization": "auth-types",
            "meta": {},
            "balance": None
        }
    ]
    
    # Test various transaction types
    mock_transactions = [
        {"id": "t1", "symbol": "AAPL", "type": "BUY", "trade_date": "2024-01-01", "units": 10.0, "price": 150.0},
        {"id": "t2", "symbol": "MSFT", "type": "SELL", "trade_date": "2024-01-02", "units": 5.0, "price": 300.0},
        {"id": "t3", "symbol": "GOOGL", "type": "DIVIDEND", "trade_date": "2024-01-03", "units": 0, "amount": 50.0},
        {"id": "t4", "symbol": "TSLA", "type": "REI", "trade_date": "2024-01-04", "units": 1.5, "price": 200.0},
        {"id": "t5", "symbol": "AMZN", "type": "CONTRIBUTION", "trade_date": "2024-01-05", "amount": 1000.0},
        {"id": "t6", "symbol": "META", "type": "FEE", "trade_date": "2024-01-06", "amount": -5.0},
        {"id": "t7", "symbol": "NFLX", "type": "INTEREST", "trade_date": "2024-01-07", "amount": 2.5},
        {"id": "t8", "symbol": "NVDA", "type": "SPLIT", "trade_date": "2024-01-08", "units": 100.0},
        {"id": "t9", "symbol": "AMD", "type": "OPTIONEXPIRATION", "trade_date": "2024-01-09"},
        {"id": "t10", "symbol": "INTC", "type": "TAX", "trade_date": "2024-01-10", "amount": -10.0},
    ]
    
    async def mock_list_accounts(*args, **kwargs):
        return {"success": True, "accounts": mock_accounts}
    
    async def mock_get_holdings(*args, **kwargs):
        return {"success": True, "positions": []}
    
    async def mock_get_option_positions(*args, **kwargs):
        return {"success": True, "option_positions": []}
    
    async def mock_get_account_balances(*args, **kwargs):
        return {"success": True, "balances": []}
    
    async def mock_get_transactions(*args, **kwargs):
        return {"success": True, "transactions": mock_transactions}
    
    with patch.object(SnapTradeService, "list_accounts", new=mock_list_accounts), \
         patch.object(SnapTradeService, "get_holdings", new=mock_get_holdings), \
         patch.object(SnapTradeService, "get_option_positions", new=mock_get_option_positions), \
         patch.object(SnapTradeService, "get_account_balances", new=mock_get_account_balances), \
         patch.object(SnapTradeService, "get_transactions", new=mock_get_transactions):
        
        import asyncio
        result = asyncio.run(SnapTradeService.sync_to_db(
            vault_user_id=vault_user_id,
            snaptrade_user_id="test_user",
            snaptrade_user_secret="test_secret"
        ))
        
        assert result["success"] is True
        assert result["synced_transactions"] == 10
        
        # Verify transaction type mappings
        txns = queries.get_transactions_for_account("snap-acc-types")
        assert len(txns) == 10
        
        type_map = {t["symbol"]: t["transaction_type"] for t in txns}
        assert type_map["AAPL"] == "buy"
        assert type_map["MSFT"] == "sell"
        assert type_map["GOOGL"] == "dividend"
        assert type_map["TSLA"] == "dividend_reinvest"
        assert type_map["AMZN"] == "deposit"
        assert type_map["META"] == "fee"
        assert type_map["NFLX"] == "interest"
        assert type_map["NVDA"] == "split"
        assert type_map["AMD"] == "option_expiration"
        assert type_map["INTC"] == "tax"


def test_short_cover_detection(test_db, vault_user_id, mock_snaptrade_client):
    """Test that negative qty sell = short, negative qty buy on option = cover."""
    
    mock_accounts = [
        {
            "account_id": "snap-acc-short",
            "name": "Short Test Account",
            "institution": "Test Broker",
            "brokerage_authorization": "auth-short",
            "meta": {},
            "balance": None
        }
    ]
    
    # Test short/cover detection
    mock_transactions = [
        # Regular buy (positive quantity)
        {
            "id": "t1", 
            "symbol": "AAPL", 
            "type": "BUY", 
            "trade_date": "2024-01-01", 
            "units": 10.0, 
            "price": 150.0,
            "is_option": False
        },
        # Short sale (SELL with negative quantity)
        {
            "id": "t2", 
            "symbol": "TSLA", 
            "type": "SELL", 
            "trade_date": "2024-01-02", 
            "units": -5.0, 
            "price": 200.0,
            "is_option": False
        },
        # Cover on option (BUY with negative quantity on option)
        {
            "id": "t3", 
            "symbol": "SPY 400 C 2024-03-15", 
            "type": "BUY", 
            "trade_date": "2024-01-03", 
            "units": -2.0, 
            "price": 5.0,
            "is_option": True
        },
        # Regular sell (positive quantity)
        {
            "id": "t4", 
            "symbol": "MSFT", 
            "type": "SELL", 
            "trade_date": "2024-01-04", 
            "units": 8.0, 
            "price": 300.0,
            "is_option": False
        },
    ]
    
    async def mock_list_accounts(*args, **kwargs):
        return {"success": True, "accounts": mock_accounts}
    
    async def mock_get_holdings(*args, **kwargs):
        return {"success": True, "positions": []}
    
    async def mock_get_option_positions(*args, **kwargs):
        return {"success": True, "option_positions": []}
    
    async def mock_get_account_balances(*args, **kwargs):
        return {"success": True, "balances": []}
    
    async def mock_get_transactions(*args, **kwargs):
        return {"success": True, "transactions": mock_transactions}
    
    with patch.object(SnapTradeService, "list_accounts", new=mock_list_accounts), \
         patch.object(SnapTradeService, "get_holdings", new=mock_get_holdings), \
         patch.object(SnapTradeService, "get_option_positions", new=mock_get_option_positions), \
         patch.object(SnapTradeService, "get_account_balances", new=mock_get_account_balances), \
         patch.object(SnapTradeService, "get_transactions", new=mock_get_transactions):
        
        import asyncio
        result = asyncio.run(SnapTradeService.sync_to_db(
            vault_user_id=vault_user_id,
            snaptrade_user_id="test_user",
            snaptrade_user_secret="test_secret"
        ))
        
        assert result["success"] is True
        assert result["synced_transactions"] == 4
        
        # Verify transaction types
        txns = queries.get_transactions_for_account("snap-acc-short")
        assert len(txns) == 4
        
        type_map = {t["symbol"]: t["transaction_type"] for t in txns}
        
        # Regular buy should stay 'buy'
        assert type_map["AAPL"] == "buy"
        
        # SELL with negative qty should become 'short'
        assert type_map["TSLA"] == "short"
        
        # BUY with negative qty on option should become 'cover'
        assert type_map["SPY 400 C 2024-03-15"] == "cover"
        
        # Regular sell should stay 'sell'
        assert type_map["MSFT"] == "sell"
        
        # Verify quantities are stored as absolute values
        qty_map = {t["symbol"]: t["quantity"] for t in txns}
        assert qty_map["AAPL"] == 10.0  # Was positive
        assert qty_map["TSLA"] == 5.0   # Was -5.0, now abs
        assert qty_map["SPY 400 C 2024-03-15"] == 2.0  # Was -2.0, now abs
        assert qty_map["MSFT"] == 8.0   # Was positive
