-- Cross Market Research V0 — research-only DB (NOT trading)

CREATE TABLE IF NOT EXISTS series_meta (
    series_key TEXT PRIMARY KEY,
    category TEXT NOT NULL,
    source TEXT,
    start_date TEXT,
    end_date TEXT,
    row_count INTEGER,
    updated_at TEXT
);

CREATE TABLE IF NOT EXISTS daily_returns (
    series_key TEXT NOT NULL,
    trade_date TEXT NOT NULL,
    daily_return REAL,
    PRIMARY KEY (series_key, trade_date)
);

CREATE TABLE IF NOT EXISTS factor_returns (
    factor_id TEXT NOT NULL,
    trade_date TEXT NOT NULL,
    daily_return REAL,
    PRIMARY KEY (factor_id, trade_date)
);

CREATE TABLE IF NOT EXISTS lead_lag_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    driver TEXT NOT NULL,
    target TEXT NOT NULL,
    lag_days INTEGER NOT NULL,
    window_days INTEGER NOT NULL,
    sample_count INTEGER,
    hit_rate REAL,
    avg_return REAL,
    avg_drawdown REAL,
    correlation REAL,
    direction TEXT,
    computed_at TEXT
);

CREATE TABLE IF NOT EXISTS research_questions (
    question_id TEXT PRIMARY KEY,
    question TEXT,
    driver TEXT,
    target TEXT,
    verdict TEXT,
    evidence_json TEXT,
    computed_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_lead_lag_driver ON lead_lag_results(driver, target);
