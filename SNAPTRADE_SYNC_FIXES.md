# SnapTrade Sync Fixes - Implementation Summary

## Date
2026-02-27

## Overview
Fixed all 6 issues in the SnapTrade sync functionality to properly persist holdings and transactions to SQLite.

## Issues Fixed

### 1. Account Creation (FIXED ✅)
**Problem:** Account creation used `queries.create_account()` with random ID, then tried to UPDATE it to the SnapTrade account ID. This was fragile and wrong.

**Solution:** 
- Added `account_id` parameter to `queries.create_account()` function
- If `account_id` is `None`, generates random ID (backward compatible)
- If `account_id` is provided, uses it directly
- Updated `sync_to_db` to pass SnapTrade account ID directly when creating accounts

**Files Changed:**
- `db/queries.py` - Modified `create_account()` function
- `services/snaptrade_service.py` - Updated sync logic

**Test:** `test_sync_creates_accounts_with_snaptrade_id`

### 2. Connection/Brokerage Linking (FIXED ✅)
**Problem:** Accounts were created without linking to the `connections` or `brokerages` tables.

**Solution:**
- Upsert brokerage using institution name from SnapTrade
- Create or get connection record linking user → brokerage (using brokerage_authorization as provider_account_id)
- Link account to connection via `connection_id` field
- Added `get_connection_by_provider_account_id()` query function

**Files Changed:**
- `db/queries.py` - Added `get_connection_by_provider_account_id()`
- `services/snaptrade_service.py` - Updated sync logic to create connections

**Test:** `test_sync_creates_brokerage_and_connection`

### 3. Transaction Sync (FIXED ✅)
**Problem:** `sync_to_db` only synced holdings, not transactions.

**Solution:**
- After syncing holdings for each account, fetch transactions for last 90 days
- Persist transactions with deduplication by external_id
- Added `get_transaction_by_external_id()` query function
- Modified `create_transaction()` to check for existing transaction before insert

**Files Changed:**
- `db/queries.py` - Added `get_transaction_by_external_id()`, modified `create_transaction()`
- `services/snaptrade_service.py` - Added transaction fetching and persistence logic

**Test:** `test_sync_persists_transactions`, `test_transaction_dedup`

### 4. Stale Holdings Cleanup (FIXED ✅)
**Problem:** If you sold a position, the old holding stayed in the DB after sync.

**Solution:**
- Track which symbols were seen during sync (using a `seen_symbols` set)
- After upserting holdings, call `delete_stale_holdings()` to remove positions not in the sync
- Added `delete_stale_holdings()` query function

**Files Changed:**
- `db/queries.py` - Added `delete_stale_holdings()`
- `services/snaptrade_service.py` - Added stale cleanup logic

**Test:** `test_sync_removes_stale_holdings`

### 5. Market Value Computation (FIXED ✅)
**Problem:** Holdings were upserted with `market_value=None`.

**Solution:**
- Compute `market_value = quantity * current_price` when both values available
- Extract `average_cost` from SnapTrade's `open_pnl` field using formula:
  `average_cost = current_price - (open_pnl / quantity)`

**Files Changed:**
- `services/snaptrade_service.py` - Added market_value and average_cost computation

**Test:** `test_sync_computes_market_value`

### 6. Account Metadata Extraction (FIXED ✅)
**Problem:** Account type, currency, and balance info from SnapTrade were ignored.

**Solution:**
- Extract `account_type` from `account_data.get("meta", {}).get("type")`
- Extract `currency` from balance info if available (defaults to "USD")
- Pass these values to `create_account()`

**Files Changed:**
- `services/snaptrade_service.py` - Added metadata extraction logic

**Test:** `test_sync_extracts_account_metadata`

## New Functions Added

### db/queries.py
1. **`get_transaction_by_external_id(external_id: str) -> Optional[Dict]`**
   - Looks up transaction by external_id for deduplication

2. **`delete_stale_holdings(account_id: str, active_symbols: set) -> int`**
   - Deletes holdings not in the active_symbols set
   - Returns count of deleted holdings

3. **`get_connection_by_provider_account_id(provider_account_id: str) -> Optional[Dict]`**
   - Looks up connection by provider account ID

### Modified Functions

#### db/queries.py
1. **`create_account(..., account_id: Optional[str] = None, ...)`**
   - Now accepts optional `account_id` parameter
   - If None, generates random ID (backward compatible)
   - If provided, uses it directly

2. **`create_transaction(...)`**
   - Now checks for existing transaction by external_id before insert
   - Returns existing transaction ID if duplicate found

#### services/snaptrade_service.py
1. **`sync_to_db(...)`**
   - Completely rewritten to fix all 6 issues
   - Now syncs accounts, holdings, AND transactions
   - Properly links accounts to connections and brokerages
   - Computes market_value and average_cost
   - Cleans up stale holdings
   - Extracts account metadata

## Test Suite

### New Test File: tests/test_snaptrade_sync.py
7 comprehensive tests covering all 6 fixes:

1. **test_sync_creates_accounts_with_snaptrade_id** - Verifies account ID matches SnapTrade ID
2. **test_sync_creates_brokerage_and_connection** - Verifies brokerage + connection records created
3. **test_sync_persists_transactions** - Verifies transactions stored with external_id
4. **test_transaction_dedup** - Verifies running sync twice doesn't create duplicates
5. **test_sync_removes_stale_holdings** - Verifies sold positions get cleaned up
6. **test_sync_computes_market_value** - Verifies market_value = qty * price
7. **test_sync_extracts_account_metadata** - Verifies account_type and currency extraction

### Test Results
```
Total Tests: 36
Passed: 36 ✅
Failed: 0

Breakdown:
- test_database.py: 5/5 ✅
- test_queries.py: 13/13 ✅
- test_portfolio_service.py: 5/5 ✅
- test_integration.py: 6/6 ✅
- test_snaptrade_sync.py: 7/7 ✅ (NEW)
```

**All existing 29 tests continue to pass - no breaking changes.**

## Files Modified

1. **db/queries.py**
   - +65 lines (3 new functions, 2 modified functions)

2. **services/snaptrade_service.py**
   - ~150 lines rewritten in `sync_to_db()` method

3. **tests/test_snaptrade_sync.py**
   - +500 lines (new test file)

4. **tests/.test-evidence.json**
   - Updated with Phase 3 results

## Backward Compatibility

✅ All changes are backward compatible:
- `create_account()` still works without `account_id` parameter
- Existing code that doesn't use sync_to_db is unaffected
- All 29 existing tests still pass

## Usage Example

```python
from services.snaptrade_service import SnapTradeService
import asyncio

# Sync all accounts, holdings, and transactions
result = asyncio.run(SnapTradeService.sync_to_db(
    vault_user_id="user-123",
    snaptrade_user_id="snap-user",
    snaptrade_user_secret="snap-secret"
))

# Result includes:
# {
#   "success": True,
#   "synced_accounts": 3,
#   "synced_holdings": 15,
#   "synced_transactions": 42,
#   "cleaned_stale_holdings": 2,
#   "timestamp": "2026-02-27T23:08:00Z"
# }
```

## Next Steps

The SnapTrade sync is now fully functional and production-ready. Future enhancements could include:

1. **Incremental sync** - Track last sync time per account, only fetch new transactions
2. **Performance optimization** - Batch inserts for large transaction sets
3. **Error recovery** - Better handling of partial failures (e.g., one account fails)
4. **Sync scheduling** - Background job to auto-sync daily
5. **Conflict resolution** - Handle edge cases where SnapTrade and local data diverge

## Verification Checklist

- [x] Issue 1: Account creation fixed
- [x] Issue 2: Connection/brokerage linking fixed
- [x] Issue 3: Transaction sync implemented
- [x] Issue 4: Stale holdings cleanup implemented
- [x] Issue 5: Market value computation implemented
- [x] Issue 6: Account metadata extraction implemented
- [x] All 7 new tests pass
- [x] All 29 existing tests still pass
- [x] Test evidence updated
- [x] No breaking changes
- [x] Code documented
