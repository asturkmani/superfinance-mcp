# Superfinance v2 — Product Requirements Document

## Overview

Superfinance is an MCP (Model Context Protocol) server that gives any AI client complete portfolio management and financial analytics capabilities. It contains **zero AI** — the user's own model (Claude, GPT, etc.) does all the thinking. Superfinance just provides data, tools, and charts.

**One-liner:** "Connect your brokerage, ask your AI anything about your money."

## Architecture

```
┌──────────────────────────────────┐
│       ANY MCP CLIENT             │
│  (Claude Desktop, Cursor,        │
│   OpenClaw, ChatGPT, etc.)       │
└──────────┬───────────────────────┘
           │ MCP Protocol
┌──────────▼───────────────────────┐
│      SUPERFINANCE MCP SERVER     │
│                                  │
│  SQLite (persistence)            │
│  Redis  (price cache only)       │
└──────────┬───────────────────────┘
           │
     ┌─────┼──────┬──────────┐
     ▼     ▼      ▼          ▼
  SnapTrade  FinanceDB  Toolkit  Plotly
  (broker)   (universe) (brain)  (charts)
```

### Infrastructure
- **Host:** VPS (ubuntu-4gb-hel1-2), same server as OpenClaw
- **Domain:** joinvault.xyz (nginx reverse proxy)
- **Process:** systemd service
- **Database:** SQLite (single file on disk)
- **Cache:** Upstash Redis (ephemeral price/FX cache only)

### Primitives (we build nothing ourselves)
| Primitive | Purpose | Cost |
|-----------|---------|------|
| **SnapTrade** | Brokerage OAuth + holdings sync | Free tier |
| **FinanceDatabase** | 160k equities, 36k ETFs, GICS classification | Free (GitHub CSV) |
| **FinanceToolkit** | Technicals, ratios, risk, performance, options Greeks | Free (Yahoo) |
| **Plotly** | Interactive chart generation | Free |
| **Upstash Redis** | Price/FX cache with TTL | Free tier |

### What we build (the glue)
- SQLite schema + CRUD
- SnapTrade → SQLite sync pipeline
- Thin wrappers around FinanceDB and FinanceToolkit
- Chart generation + saved views (permanent URLs)
- Alert scheduler + notifications
- MCP tool definitions
- Tiny web server for chart URLs

---

## Database Schema (SQLite)

```sql
-- Users
CREATE TABLE users (
    id TEXT PRIMARY KEY,
    email TEXT UNIQUE,
    name TEXT,
    notification_email TEXT,
    notification_phone TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Accounts (synced brokerage or manual)
CREATE TABLE accounts (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id),
    name TEXT NOT NULL,
    type TEXT NOT NULL CHECK (type IN ('synced', 'manual')),
    currency TEXT DEFAULT 'USD',
    -- SnapTrade fields (NULL for manual accounts)
    snaptrade_user_id TEXT,
    snaptrade_user_secret TEXT,
    snaptrade_brokerage_authorization_id TEXT,
    snaptrade_brokerage_name TEXT,
    last_synced_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Holdings snapshots (append-only log from SnapTrade syncs)
CREATE TABLE holdings_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id TEXT NOT NULL REFERENCES accounts(id),
    ticker TEXT NOT NULL,
    name TEXT,
    quantity REAL NOT NULL,
    avg_cost REAL,
    market_value REAL,
    currency TEXT DEFAULT 'USD',
    -- Option-specific fields
    option_type TEXT CHECK (option_type IN ('call', 'put', NULL)),
    strike_price REAL,
    expiration_date TEXT,
    underlying_ticker TEXT,
    snapshot_date DATE NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_snapshots_account_date ON holdings_snapshots(account_id, snapshot_date);
CREATE INDEX idx_snapshots_ticker ON holdings_snapshots(ticker);

-- Transactions (real only — from brokerage API or manual entry)
CREATE TABLE transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id TEXT NOT NULL REFERENCES accounts(id),
    ticker TEXT NOT NULL,
    name TEXT,
    date DATE NOT NULL,
    price REAL NOT NULL,
    volume REAL NOT NULL,  -- positive=buy, negative=sell
    costs REAL DEFAULT 0,
    currency TEXT DEFAULT 'USD',
    source TEXT NOT NULL CHECK (source IN ('snaptrade', 'manual', 'import')),
    external_id TEXT,  -- dedup key for SnapTrade transactions
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_transactions_account ON transactions(account_id);
CREATE INDEX idx_transactions_ticker ON transactions(ticker);
CREATE INDEX idx_transactions_date ON transactions(date);

-- Classifications (custom themes on top of FinanceDB GICS)
CREATE TABLE classifications (
    ticker TEXT PRIMARY KEY,
    display_name TEXT,  -- consolidated name (e.g., "Google" for GOOG+GOOGL)
    category TEXT,      -- custom theme (e.g., "AI Infrastructure")
    source TEXT DEFAULT 'manual' CHECK (source IN ('manual', 'perplexity', 'financedb')),
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Saved views (chart recipes — permanent URLs with live data)
CREATE TABLE saved_views (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id),
    name TEXT,
    dashboard_id TEXT,  -- NULL = standalone, set = part of dashboard
    query_type TEXT NOT NULL,  -- 'portfolio_allocation', 'returns', 'correlation', etc.
    chart_type TEXT NOT NULL,  -- 'pie', 'treemap', 'bar', 'heatmap', 'line', etc.
    config TEXT NOT NULL,      -- JSON: {group_by, color_by, tickers, date_range, ...}
    sort_order INTEGER DEFAULT 0,  -- ordering within dashboard
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Dashboards (groups of saved views)
CREATE TABLE dashboards (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id),
    name TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Alerts
CREATE TABLE alerts (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id),
    name TEXT,
    type TEXT NOT NULL,  -- 'delta_threshold', 'price_alert', 'portfolio_change', 'scheduled_report'
    config TEXT NOT NULL, -- JSON: {ticker, threshold, direction, schedule, ...}
    notification_channel TEXT DEFAULT 'email', -- 'email', 'sms', 'webhook'
    active INTEGER DEFAULT 1,
    last_triggered_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Watchlists
CREATE TABLE watchlists (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id),
    name TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE watchlist_tickers (
    watchlist_id TEXT NOT NULL REFERENCES watchlists(id),
    ticker TEXT NOT NULL,
    added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (watchlist_id, ticker)
);

-- Liabilities (for net worth calculation)
CREATE TABLE liabilities (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id),
    name TEXT NOT NULL,
    type TEXT DEFAULT 'other',  -- 'mortgage', 'auto_loan', 'credit_card', 'student_loan', 'personal_loan', 'other'
    balance REAL NOT NULL,
    interest_rate REAL,
    currency TEXT DEFAULT 'USD',
    notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Option price snapshots (for delisted options history)
CREATE TABLE option_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker TEXT NOT NULL,
    date DATE NOT NULL,
    open REAL, high REAL, low REAL, close REAL,
    volume INTEGER,
    implied_volatility REAL,
    delta REAL,
    source TEXT DEFAULT 'yahoo', -- 'yahoo', 'massive', 'computed'
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(ticker, date)
);
CREATE INDEX idx_option_snapshots_ticker ON option_snapshots(ticker);
```

---

## User Stories & MCP Tools

### 1. Portfolio Management

**Story: "Connect my brokerage"**
```
Tool: connect_brokerage
Args: user_id, brokerage_name
Returns: OAuth URL for user to complete
Flow:
  1. Create SnapTrade user (if first time)
  2. Generate OAuth redirect URL
  3. User completes auth in browser
  4. Webhook fires → create account in SQLite
  5. Initial holdings sync → store snapshot
```

**Story: "Show my holdings"**
```
Tool: get_holdings
Args: user_id, account_id? (optional, all accounts if omitted), currency?
Returns: list of positions with live prices, P&L, return %
Flow:
  1. Get latest holdings_snapshot per account
  2. Fetch live prices (Redis cache → Yahoo fallback)
  3. Compute: current_value, pnl, return_pct per position
  4. Convert to requested currency if needed
  5. Return sorted by value
```

**Story: "Add a manual position"**
```
Tool: add_transaction
Args: user_id, account_id, ticker, date, price, volume, costs?, currency?
Returns: confirmation + updated holdings
Flow:
  1. Validate account exists and is manual (or create new manual account)
  2. Insert transaction row
  3. Return updated position
Notes: volume positive = buy, negative = sell
```

**Story: "What's my portfolio worth?"**
```
Tool: get_portfolio_summary
Args: user_id, currency?
Returns: total value, total cost, total P&L, return %, breakdown by account
```

**Story: "Are my transactions complete?"**
```
Tool: reconcile
Args: user_id, account_id
Returns: list of discrepancies (ticker, holdings_qty, transactions_qty, gap)
Flow:
  1. Get latest holdings snapshot for account
  2. Compute implied holdings from SUM(transactions.volume) GROUP BY ticker
  3. Compare — flag any differences
  4. Return actionable list
```

### 2. Analysis

**Story: "Is MU overbought?"**
```
Tool: get_technicals
Args: tickers (comma-separated), indicators? (default: RSI, MACD, Bollinger), period?
Returns: latest indicator values per ticker
Flow:
  1. Instantiate Toolkit(tickers, start_date)
  2. Call relevant technicals methods
  3. Return latest values with interpretation hints
```

**Story: "How correlated are my positions?"**
```
Tool: get_correlation
Args: user_id (uses portfolio tickers), or tickers (explicit list), period?
Returns: correlation matrix
Flow:
  1. Get tickers from holdings or explicit list
  2. Toolkit → get_historical_data → compute correlation
  3. Return matrix
```

**Story: "What's my risk exposure?"**
```
Tool: get_risk_metrics
Args: user_id or tickers, period?
Returns: VaR, CVaR, max drawdown, beta, Sharpe, Sortino per position + portfolio
Flow:
  1. Toolkit → risk + performance modules
  2. Return per-position and aggregate metrics
```

**Story: "Show me the Greeks on my SIL LEAPS"**
```
Tool: get_options_analysis
Args: ticker (Yahoo option symbol or underlying + params)
Returns: chain data, Greeks, IV, theoretical price
Flow:
  1. Toolkit → options.get_option_chains()
  2. Toolkit → options.get_delta(), get_gamma(), get_theta(), get_vega()
  3. Return formatted data
```

**Story: "Compare quality metrics across my gold miners"**
```
Tool: get_ratios
Args: tickers, ratio_group? ('profitability', 'valuation', 'solvency', 'all')
Returns: ratio comparison table
Flow:
  1. Toolkit → ratios.collect_profitability_ratios() etc.
  2. Return as comparison table
```

### 3. Discovery

**Story: "Show me all semiconductor stocks"**
```
Tool: search_securities
Args: sector?, industry?, country?, market_cap?, asset_class? ('equities', 'etfs')
Returns: filtered list from FinanceDatabase
Flow:
  1. FinanceDB → Equities() or ETFs()
  2. Filter by provided params
  3. Return list with key fields (name, sector, industry, exchange, market_cap)
```

**Story: "What sector is AXTI in?"**
```
Tool: lookup_security
Args: ticker
Returns: name, sector, industry_group, industry, country, market_cap, ISIN
Flow:
  1. FinanceDB → Equities().select() → filter by ticker
  2. Supplement with classification override if exists
  3. Return combined data
```

**Story: "Find ETFs that track uranium"**
```
Tool: search_etfs
Args: category?, family?, name_search?
Returns: filtered ETF list
Flow:
  1. FinanceDB → ETFs()
  2. Filter by category/family/name
  3. Return list
```

### 4. Visualization

**Story: "Show my allocation"**
```
Tool: create_chart
Args: user_id, query_type, chart_type, config (JSON), save? (bool), name?
Returns: chart URL (joinvault.xyz/charts/{id})
Flow:
  1. Run query (e.g., portfolio_allocation → get holdings + values)
  2. Generate Plotly chart (pie, treemap, bar, heatmap, line, etc.)
  3. Save HTML to disk, serve via web server
  4. If save=true, store recipe in saved_views table → permanent URL
  5. Return URL

Supported query_types:
  - portfolio_allocation (values by position/category/account)
  - returns (P&L by position)
  - historical_performance (time series)
  - correlation (heatmap)
  - sector_exposure (from FinanceDB classification)
  - technicals (RSI/MACD/price chart)
  - comparison (multiple tickers)

Supported chart_types:
  - pie, donut, treemap, sunburst
  - bar, grouped_bar, stacked_bar
  - line, area
  - heatmap
  - scatter
  - table
```

**Story: "Build me a dashboard"**
```
Tool: create_dashboard
Args: user_id, name, views (list of {query_type, chart_type, config})
Returns: dashboard URL (joinvault.xyz/dash/{id})
Flow:
  1. Create dashboard record
  2. Create saved_view for each chart
  3. Generate combined HTML page
  4. Return URL
```

**Story: "Update my dashboard — add a returns chart"**
```
Tool: add_to_dashboard
Args: dashboard_id, query_type, chart_type, config
Returns: updated dashboard URL
```

### 5. Alerts & Monitoring

**Story: "Alert me if any option hits delta > 0.70"**
```
Tool: create_alert
Args: user_id, type='delta_threshold', config={threshold: 0.70, direction: 'above'}, channel='email'
Returns: confirmation
```

**Story: "Weekly portfolio review every Friday"**
```
Tool: create_alert
Args: user_id, type='scheduled_report', config={schedule: 'weekly', day: 'friday', time: '09:00', report_type: 'portfolio_review'}, channel='email'
Returns: confirmation
```

**Story: "Tell me if portfolio drops 5% in a day"**
```
Tool: create_alert
Args: user_id, type='portfolio_change', config={threshold: -5, period: '1d'}, channel='sms'
Returns: confirmation
```

```
Tool: list_alerts
Args: user_id
Returns: all active alerts

Tool: delete_alert
Args: alert_id
Returns: confirmation
```

### 6. Classification

**Story: "Reclassify IREN as AI Infrastructure"**
```
Tool: update_classification
Args: ticker, display_name?, category?
Returns: confirmation
```

**Story: "What categories do I have?"**
```
Tool: list_categories
Args: user_id? (show categories used in their portfolio)
Returns: list of categories with ticker counts
```

### 7. Watchlists

```
Tool: create_watchlist
Args: user_id, name, tickers
Returns: watchlist with current prices

Tool: get_watchlist
Args: watchlist_id
Returns: tickers with live prices, daily change, technicals summary
```

### 8. Liabilities

```
Tool: add_liability
Args: user_id, name, type, balance, interest_rate?, currency?
Returns: confirmation

Tool: get_net_worth
Args: user_id, currency?
Returns: total assets, total liabilities, net worth
```

---

## File Structure

```
superfinance/
├── server.py                 ← MCP server entry point (FastMCP)
├── web.py                    ← Flask/FastAPI for chart URLs + webhooks
├── requirements.txt
├── pyproject.toml
│
├── db/
│   ├── schema.sql            ← SQLite schema (above)
│   ├── database.py           ← Connection, migrations, helpers
│   └── queries.py            ← Named queries (get_holdings, etc.)
│
├── services/
│   ├── snaptrade.py          ← OAuth, sync, webhook handler
│   ├── portfolio.py          ← Holdings math, P&L, reconciliation
│   ├── analytics.py          ← FinanceToolkit wrapper
│   ├── universe.py           ← FinanceDatabase wrapper
│   ├── charts.py             ← Plotly generation + saved views
│   ├── alerts.py             ← Scheduler + email/SMS
│   ├── options.py            ← Daily snapshots + Massive API
│   ├── classification.py     ← Custom themes (Perplexity + manual)
│   └── cache.py              ← Redis price/FX cache
│
├── tools/
│   ├── portfolio.py          ← MCP tools: holdings, P&L, reconcile
│   ├── analysis.py           ← MCP tools: technicals, risk, ratios, Greeks
│   ├── discovery.py          ← MCP tools: search, lookup, screen
│   ├── charts.py             ← MCP tools: create chart, dashboard
│   ├── alerts.py             ← MCP tools: create/list/delete alerts
│   ├── accounts.py           ← MCP tools: connect brokerage, manage accounts
│   ├── watchlists.py         ← MCP tools: watchlist CRUD
│   └── liabilities.py        ← MCP tools: liabilities, net worth
│
├── web/
│   ├── templates/
│   │   ├── chart.html        ← Single chart page
│   │   └── dashboard.html    ← Multi-chart dashboard page
│   └── static/               ← CSS if needed
│
└── data/
    └── superfinance.db       ← SQLite database file
```

---

## Build Phases

### Phase 1 — Foundation (SQLite + basic CRUD)
- [ ] SQLite schema + database.py (connection, migrations)
- [ ] queries.py (named queries for all tables)
- [ ] Basic user/account CRUD
- [ ] Manual transaction + holdings entry
- [ ] MCP server skeleton with FastMCP
- [ ] Basic MCP tools: add_transaction, get_holdings, get_portfolio_summary
- **Test:** Can add manual positions and see portfolio value

### Phase 2 — SnapTrade Integration
- [ ] Port snaptrade_service.py → use SQLite instead of Redis
- [ ] OAuth flow (connect_brokerage tool)
- [ ] Holdings sync → holdings_snapshots table
- [ ] Transaction sync (for brokerages that support it)
- [ ] Webhook handler for real-time updates
- [ ] Reconciliation tool
- [ ] MCP tools: connect_brokerage, sync, reconcile
- **Test:** Can connect IBKR, see synced holdings alongside manual positions

### Phase 3 — Analytics (FinanceDB + FinanceToolkit)
- [ ] universe.py — FinanceDB wrapper (search, lookup, classify)
- [ ] analytics.py — FinanceToolkit wrapper
  - [ ] Technicals (RSI, MACD, Bollinger, EMA, all momentum indicators)
  - [ ] Performance (Sharpe, Sortino, alpha, beta, CAGR)
  - [ ] Risk (VaR, CVaR, max drawdown, GARCH)
  - [ ] Ratios (profitability, valuation, solvency — 77 ratios)
  - [ ] Options (chains, Greeks via Black-Scholes)
- [ ] classification.py — Perplexity for unknown tickers, FinanceDB for GICS
- [ ] MCP tools: get_technicals, get_risk_metrics, get_ratios, get_options_analysis, search_securities, lookup_security
- **Test:** Can ask "is MU overbought?" and get RSI/MACD answer

### Phase 4 — Visualization (Plotly + saved views)
- [ ] charts.py — Plotly chart generation from query results
  - [ ] Pie, treemap, bar, line, heatmap, scatter, table
  - [ ] Saved views (recipes in SQLite)
  - [ ] Dashboard composition (multiple charts on one page)
- [ ] web.py — Flask/FastAPI server for chart URLs
  - [ ] GET /charts/{id} → render saved view with live data
  - [ ] GET /dash/{id} → render dashboard
  - [ ] GET /health → health check
- [ ] Nginx config for joinvault.xyz
- [ ] MCP tools: create_chart, create_dashboard, add_to_dashboard
- **Test:** Can generate portfolio treemap, get permanent URL, bookmark it

### Phase 5 — Alerts & Scheduling
- [ ] alerts.py — APScheduler for background checks
  - [ ] Delta threshold alerts (options)
  - [ ] Price alerts (watchlist)
  - [ ] Portfolio change alerts (% drop/gain)
  - [ ] Scheduled reports (weekly review)
- [ ] Email notifications (SendGrid/Resend)
- [ ] SMS notifications (Twilio, optional)
- [ ] Option price snapshots (daily job)
- [ ] options.py — Massive API for historical option prices
- [ ] MCP tools: create_alert, list_alerts, delete_alert
- **Test:** Set delta alert, receive email when triggered

### Phase 6 — Polish & Deploy
- [ ] Systemd service file
- [ ] Nginx config on joinvault.xyz
- [ ] Redis cache for price/FX (port from v1)
- [ ] Watchlist tools
- [ ] Liability tools + net worth
- [ ] Error handling, logging, rate limiting
- [ ] README + setup docs
- **Test:** Full end-to-end: connect brokerage → view portfolio → get analysis → see charts → receive alerts

---

## Migration from v1

### What to port
| v1 File | v2 Destination | Notes |
|---------|---------------|-------|
| services/snaptrade_service.py | services/snaptrade.py | Swap Redis → SQLite storage |
| helpers/classification.py | services/classification.py | Swap Redis → SQLite, keep Perplexity |
| cache.py | services/cache.py | Keep Redis for price/FX cache only |
| services/portfolio_service.py | services/portfolio.py | Swap JSON file → SQLite |
| tools/snaptrade.py | tools/accounts.py | Clean up, simplify |

### What to delete
| v1 File | Reason |
|---------|--------|
| services/yahoo_finance_service.py | Replaced by FinanceToolkit |
| helpers/pricing.py | Replaced by FinanceToolkit |
| tools/yahoo_finance.py | Replaced by FinanceToolkit |
| helpers/chart_templates.py | Replaced by Plotly |
| tools/charts.py | Replaced by Plotly |
| tools/visualization.py | Replaced by Plotly |
| helpers/portfolio.py | Replaced by SQLite queries |
| api/ (all routes) | MCP is the interface, no REST API needed |
| refresh.py | Rewrite as alerts.py |
| Dockerfile, fly.toml | Running on VPS now |

### Data migration
- Manual portfolios: `~/.superfinance/portfolios.json` → SQLite transactions table
- Redis classifications: `superfinance:classification:*` → SQLite classifications table
- Redis accounts/holdings: re-sync from SnapTrade (cache, not persistent)

---

## Key Design Decisions

1. **Holdings = source of truth** for "what do I own." Transactions are optional enrichment.
2. **No inferred transactions.** Reconciliation flags gaps; user fills them.
3. **Charts are recipes, not images.** Saved views re-render with live data on every visit.
4. **Zero AI in the product.** User's model does all reasoning. We provide tools.
5. **MCP is the interface.** No REST API needed. Any MCP client works.
6. **SQLite for persistence, Redis for ephemeral cache only.** Simple, no infrastructure.
7. **FinanceToolkit for all analytics.** We don't compute anything ourselves.
8. **FinanceDatabase for classification.** Perplexity only for unknown/custom tickers.
9. **Options tracked via daily snapshots** + Massive API for historical backfill.
10. **Runs on VPS** at joinvault.xyz. No cloud deployment complexity.

---

## Dependencies

```
# Core
fastmcp              # MCP server framework
sqlite3              # Built into Python

# Data
financedatabase      # Security universe (160k equities, 36k ETFs)
financetoolkit       # Analytics engine (technicals, ratios, risk, options)
snaptrade-python-sdk # Brokerage API

# Cache
upstash-redis        # Ephemeral price cache

# Charts
plotly               # Chart generation

# Web
flask                # Tiny server for chart URLs (or fastapi+uvicorn)

# Notifications
sendgrid             # Email (or resend)
twilio               # SMS (optional)

# Scheduling
apscheduler          # Background jobs

# Classification
httpx                # Perplexity API calls

# Utilities
python-dotenv
```

---

## Success Metrics

- [ ] Connect a brokerage in < 2 minutes
- [ ] Portfolio summary with live prices in < 3 seconds
- [ ] Any technical indicator in < 5 seconds
- [ ] Chart generation in < 5 seconds
- [ ] Permanent chart URL loads in < 2 seconds
- [ ] Total codebase < 4,000 lines (vs v1's 9,853)
- [ ] Works with any MCP client (not just OpenClaw)
