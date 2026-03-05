-- Users
CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    email TEXT UNIQUE,
    name TEXT,
    password_hash TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- API Tokens for user authentication
CREATE TABLE IF NOT EXISTS api_tokens (
    token TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name TEXT DEFAULT 'default',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_used_at TIMESTAMP,
    revoked INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_api_tokens_user ON api_tokens(user_id);

-- Brokerages (shared reference table — e.g., Interactive Brokers, Schwab)
CREATE TABLE IF NOT EXISTS brokerages (
    id TEXT PRIMARY KEY,
    provider TEXT NOT NULL,  -- 'snaptrade'
    provider_institution_id TEXT NOT NULL,
    name TEXT NOT NULL,
    logo_url TEXT,
    supports_holdings INTEGER DEFAULT 1,
    supports_transactions INTEGER DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(provider, provider_institution_id)
);

-- Connections (user's OAuth link to a brokerage via SnapTrade)
CREATE TABLE IF NOT EXISTS connections (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    brokerage_id TEXT REFERENCES brokerages(id) ON DELETE SET NULL,
    provider_account_id TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',  -- active, disabled, error
    status_message TEXT,
    metadata TEXT,  -- JSON blob
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_connections_user ON connections(user_id);

-- Accounts (a portfolio bucket — synced or manual)
CREATE TABLE IF NOT EXISTS accounts (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    connection_id TEXT REFERENCES connections(id) ON DELETE SET NULL,
    name TEXT NOT NULL,
    account_type TEXT,  -- 'brokerage', 'retirement', 'crypto', 'real_estate', etc. Just a label.
    currency TEXT DEFAULT 'USD',
    is_manual INTEGER DEFAULT 0,
    holdings_synced INTEGER DEFAULT 0,
    transactions_synced INTEGER DEFAULT 0,
    last_sync_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_accounts_user ON accounts(user_id);

-- Holdings (current positions — positive or negative values)
CREATE TABLE IF NOT EXISTS holdings (
    id TEXT PRIMARY KEY,
    account_id TEXT NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    symbol TEXT NOT NULL,
    name TEXT,
    quantity REAL NOT NULL,
    average_cost REAL,
    current_price REAL,
    market_value REAL,
    currency TEXT DEFAULT 'USD',
    asset_type TEXT,  -- 'equity', 'etf', 'option', 'cash', 'real_estate', 'liability', etc.
    metadata TEXT,  -- JSON blob for extra fields
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_holdings_account ON holdings(account_id);
CREATE INDEX IF NOT EXISTS idx_holdings_symbol ON holdings(symbol);

-- Transactions
CREATE TABLE IF NOT EXISTS transactions (
    id TEXT PRIMARY KEY,
    account_id TEXT NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    symbol TEXT NOT NULL,
    name TEXT,
    date DATE NOT NULL,
    transaction_type TEXT NOT NULL,  -- 'buy', 'sell', 'dividend', 'fee', etc.
    quantity REAL,
    price REAL,
    fees REAL DEFAULT 0,
    currency TEXT DEFAULT 'USD',
    source TEXT NOT NULL DEFAULT 'manual',  -- 'manual', 'snaptrade', 'import'
    external_id TEXT,  -- dedup key for SnapTrade
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_transactions_account ON transactions(account_id);
CREATE INDEX IF NOT EXISTS idx_transactions_symbol ON transactions(symbol);
CREATE INDEX IF NOT EXISTS idx_transactions_date ON transactions(date);

-- Classifications (custom categories for tickers)
CREATE TABLE IF NOT EXISTS classifications (
    symbol TEXT PRIMARY KEY,
    display_name TEXT,
    category TEXT,
    source TEXT DEFAULT 'manual',  -- 'manual', 'perplexity', 'financedb'
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Watchlists
CREATE TABLE IF NOT EXISTS watchlists (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS watchlist_tickers (
    watchlist_id TEXT NOT NULL REFERENCES watchlists(id) ON DELETE CASCADE,
    symbol TEXT NOT NULL,
    added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (watchlist_id, symbol)
);

-- Dashboards (saved views per user)
CREATE TABLE IF NOT EXISTS dashboards (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    description TEXT,
    is_default INTEGER DEFAULT 0,
    layout TEXT DEFAULT 'grid',  -- 'grid' or 'stack'
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_dashboards_user ON dashboards(user_id);

-- Dashboard Widgets (items on a dashboard)
CREATE TABLE IF NOT EXISTS dashboard_widgets (
    id TEXT PRIMARY KEY,
    dashboard_id TEXT NOT NULL REFERENCES dashboards(id) ON DELETE CASCADE,
    widget_type TEXT NOT NULL,  -- 'stock_chart', 'portfolio_pie', 'portfolio_treemap', 'analysis_table', 'correlation_heatmap', 'holdings_list', 'performance_chart'
    title TEXT,
    config TEXT NOT NULL DEFAULT '{}',  -- JSON: tickers, period, indicators, account_id, etc.
    position INTEGER DEFAULT 0,  -- ordering
    width INTEGER DEFAULT 1,  -- grid columns (1-4 on desktop, always full width on mobile)
    height INTEGER DEFAULT 1,  -- grid rows
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_widgets_dashboard ON dashboard_widgets(dashboard_id);

-- Schema version tracking
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER PRIMARY KEY,
    applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
