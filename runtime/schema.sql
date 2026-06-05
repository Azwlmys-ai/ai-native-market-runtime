-- ============================================================================
-- Polymarket Arbitrage — SQLite 影子库 schema 草案 (Phase 0 / Phase 1)
-- ----------------------------------------------------------------------------
-- 定位：影子库 (shadow)。json 文件仍是唯一事实源 (source of truth)。
-- 本库只做旁路记录 + 状态归一验证，不参与任何执行/审批/dry-run 判断。
--
-- 本轮只建 live 链路 6 张表：
--   signals / reviews / paper_orders / paper_positions / paper_trades / runtime_events
-- 暂不建：hypotheses / postmortems（等 Phase 3 Agent 研究闭环再加）。
--
-- 设计约定：
--   * 每表都保留 raw_json 列：原始记录整体存档，避免 schema 漂移时丢字段。
--   * *_uid 列为业务幂等键，配 UNIQUE，供 upsert 用，避免重复行。
--   * 所有时间列存 ISO8601 文本（与现有 json 一致），created_at 为入库时刻。
--   * status 沿用现有 6 桶约定，dry_run 永不与 success 混算。
-- ============================================================================

PRAGMA journal_mode = WAL;      -- 单写者 + 读并发
PRAGMA foreign_keys = ON;
PRAGMA synchronous = NORMAL;    -- WAL 下足够安全且更快

-- ----------------------------------------------------------------------------
-- 1. signals — 候选信号（对应 data/signals.json，orchestrator 步骤 12.5 汇总）
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS signals (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    signal_uid      TEXT    NOT NULL UNIQUE,   -- 幂等键: hash(market_id|direction|generated_at|source)
    cycle_id        TEXT,                      -- 产生该信号的周期
    market_id       TEXT,
    market_slug     TEXT,
    market_name     TEXT,
    direction       TEXT,                      -- YES / NO
    price           REAL,
    confidence      REAL,
    expected_value  REAL,
    position_size   REAL,
    source          TEXT,                      -- agent_b / agent_k_v2 / ...
    reason          TEXT,
    logic_chain     TEXT,                      -- 原 list/obj → json 文本
    risk_notes      TEXT,
    learned_rule_match TEXT,
    data_sources    TEXT,                      -- 原 list → json 文本
    generated_at    TEXT,
    raw_json        TEXT    NOT NULL,
    created_at      TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);
CREATE INDEX IF NOT EXISTS idx_signals_cycle   ON signals(cycle_id);
CREATE INDEX IF NOT EXISTS idx_signals_market  ON signals(market_id);

-- ----------------------------------------------------------------------------
-- 2. reviews — 风控审查结果（对应 agent_m 写的 review_results.json）
--    粒度：每个 (cycle, signal) 一行决策。
--    现状 review_results.json 已有 paper/real 分流 → lane 列承接，
--    并为 PRD 未来 risk grading (approve / paper_probe / reject) 预留。
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS reviews (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    review_uid      TEXT    NOT NULL UNIQUE,   -- hash(cycle_id|signal_uid)
    cycle_id        TEXT,
    signal_uid      TEXT,                      -- 关联 signals.signal_uid（软关联，不强制外键以容忍乱序入库）
    market_id       TEXT,
    market_name     TEXT,
    direction       TEXT,
    decision        TEXT,                      -- APPROVE / REJECT (/ PAPER_PROBE 预留)
    lane            TEXT,                      -- paper / real
    failure_probability INTEGER,
    explanation     TEXT,
    risk_points     TEXT,                      -- 原 list → json 文本
    reviewed_at     TEXT,
    raw_json        TEXT    NOT NULL,
    created_at      TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);
CREATE INDEX IF NOT EXISTS idx_reviews_cycle    ON reviews(cycle_id);
CREATE INDEX IF NOT EXISTS idx_reviews_signal   ON reviews(signal_uid);
CREATE INDEX IF NOT EXISTS idx_reviews_decision ON reviews(decision);

-- ----------------------------------------------------------------------------
-- 3. paper_orders — 下单意图/结果（买侧 execution_results.json + 卖侧 sell_execution_results.json）
--    processed 列承接被收敛掉的 sell_signals.json 回写语义（不再回写文件）。
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS paper_orders (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    order_uid       TEXT    NOT NULL UNIQUE,   -- hash(cycle_id|signal_uid|side)
    cycle_id        TEXT,
    signal_uid      TEXT,
    market_id       TEXT,
    market_slug     TEXT,
    side            TEXT,                      -- BUY / SELL
    size            REAL,
    notional_usd    REAL,
    entry_price     REAL,
    status          TEXT,                      -- success/dry_run/simulated/failed/timeout/error
    processed       INTEGER NOT NULL DEFAULT 0,-- 0/1，替代 sell_signals 回写清空
    source          TEXT,
    ts              TEXT,
    raw_json        TEXT    NOT NULL,
    created_at      TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);
CREATE INDEX IF NOT EXISTS idx_orders_cycle   ON paper_orders(cycle_id);
CREATE INDEX IF NOT EXISTS idx_orders_status  ON paper_orders(status);
CREATE INDEX IF NOT EXISTS idx_orders_market  ON paper_orders(market_id);

-- ----------------------------------------------------------------------------
-- 4. paper_positions — 持仓【状态归一表，本次最大收益】
--    把分裂的 paper_portfolio.json (open) + positions_closed_registry.json (closed)
--    合并成一张表，单一 status 列。彻底消灭 status=None 的漂移。
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS paper_positions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    position_uid    TEXT    NOT NULL UNIQUE,   -- hash(canonical_market_id|direction)
    canonical_market_id TEXT,                  -- Phase 2a：解析出的权威市场主键（id 或 slug:<slug> 临时键）
    market_id       TEXT,
    market_slug     TEXT,
    market_name     TEXT,
    direction       TEXT,
    status          TEXT    NOT NULL DEFAULT 'open',  -- open / closed
    entry_price     REAL,
    exit_price      REAL,
    position_size   REAL,
    notional_usd    REAL,
    realized_pnl    REAL,
    price_source    TEXT,
    close_reason    TEXT,
    close_source    TEXT,
    dry_run         INTEGER NOT NULL DEFAULT 1,
    synthetic       INTEGER NOT NULL DEFAULT 0,
    opened_at       TEXT,
    closed_at       TEXT,
    raw_json        TEXT    NOT NULL,
    updated_at      TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    created_at      TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);
CREATE INDEX IF NOT EXISTS idx_pos_status ON paper_positions(status);
CREATE INDEX IF NOT EXISTS idx_pos_market ON paper_positions(market_id);
CREATE INDEX IF NOT EXISTS idx_pos_slug   ON paper_positions(market_slug);
-- 注：idx_pos_canon（依赖 canonical_market_id 列）由 _shadow._migrate() 在补列后创建，
-- 不放这里——否则旧库 executescript 跑到这行会因缺列报错中止。

-- ----------------------------------------------------------------------------
-- 5. paper_trades — 成交流水（对应 data/paper_trades.jsonl，append-only 语义）
--    type=OPEN/CLOSE；CLOSE 行带 exit_price / realized_pnl / close_reason。
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS paper_trades (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    trade_uid       TEXT    UNIQUE,            -- hash(market_id|type|ts)；允许 NULL 兼容历史
    position_uid    TEXT,
    market_id       TEXT,
    type            TEXT,                      -- OPEN / CLOSE
    side            TEXT,                      -- BUY / SELL
    size            REAL,
    entry_price     REAL,
    exit_price      REAL,
    notional_usd    REAL,
    realized_pnl    REAL,
    close_reason    TEXT,
    market_name     TEXT,
    source          TEXT,
    ts              TEXT,
    raw_json        TEXT    NOT NULL,
    created_at      TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);
CREATE INDEX IF NOT EXISTS idx_trades_market ON paper_trades(market_id);
CREATE INDEX IF NOT EXISTS idx_trades_type   ON paper_trades(type);
CREATE INDEX IF NOT EXISTS idx_trades_pos    ON paper_trades(position_uid);

-- ----------------------------------------------------------------------------
-- 7. markets — 市场身份维表（Phase 2a：canonical market identity）
--    累积权威 id↔slug↔question 映射。来源：每周期 latest_data.polymarket_markets
--    + 任何同时含 id 与 slug/question 的记录。一旦见过即记住，解决历史 slug 无 id。
--    canonical key = Polymarket 数字 id（market_id）。
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS markets (
    market_id   TEXT PRIMARY KEY,            -- Polymarket 数字 id，canonical key
    slug        TEXT,
    question    TEXT,
    first_seen  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    last_seen   TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    raw_json    TEXT
);
-- slug 非唯一：真实数据存在同一 slug 被不同 market_id 引用的脏映射；
-- resolve 时按 last_seen DESC 取最新（权威 latest_data 最后播种、必然最新而胜出）。
CREATE INDEX IF NOT EXISTS idx_markets_slug     ON markets(slug);
CREATE INDEX IF NOT EXISTS idx_markets_question ON markets(question);

-- ----------------------------------------------------------------------------
-- 6. runtime_events — 系统事件（对应 data/events/runtime_events.jsonl）
--    Phase 1 由 ingest 脚本灌入；jsonl 的 append 原样保留（crash-safe）。
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS runtime_events (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    event_uid       TEXT    UNIQUE,            -- trace_id（已天然唯一）
    ts              TEXT,
    cycle_id        TEXT,
    type            TEXT,                      -- signal.generated / risk.rejected / execution.dry_run / ...
    agent           TEXT,
    trace_id        TEXT,
    payload         TEXT,                      -- json 文本
    created_at      TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);
CREATE INDEX IF NOT EXISTS idx_events_cycle ON runtime_events(cycle_id);
CREATE INDEX IF NOT EXISTS idx_events_type  ON runtime_events(type);
CREATE INDEX IF NOT EXISTS idx_events_agent ON runtime_events(agent);
CREATE INDEX IF NOT EXISTS idx_events_ts    ON runtime_events(ts);

-- ----------------------------------------------------------------------------
-- 8. postmortems — 逐笔复盘（Phase 3a：Agent G → Postmortem Engine）
--    每个已平仓持仓一条结构化复盘，关联原始信号(hypothesis/expected_edge)与实际结果。
--    PRD 字段：hypothesis / expected_edge / actual_result / failure_reason /
--             liquidity_issue / timing_issue / model_issue。
--    source=deterministic（规则 fallback，沙箱可验）或 llm（叙述增强，主机）。
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS postmortems (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    postmortem_uid      TEXT NOT NULL UNIQUE,   -- hash(position_uid)
    position_uid        TEXT,                   -- 关联 paper_positions
    canonical_market_id TEXT,
    market_name         TEXT,
    direction           TEXT,
    signal_uid          TEXT,                   -- 关联原始 signals（可空）
    hypothesis          TEXT,                   -- 原始假设（来自信号 reason/logic_chain）
    expected_edge       REAL,                   -- 预期边（signal.expected_value）
    confidence          REAL,                   -- 原始置信度
    entry_price         REAL,
    exit_price          REAL,
    realized_pnl        REAL,
    outcome             TEXT,                   -- win / loss / flat
    failure_reason      TEXT,
    liquidity_issue     INTEGER DEFAULT 0,
    timing_issue        INTEGER DEFAULT 0,
    model_issue         INTEGER DEFAULT 0,
    hypothesis_verdict  TEXT,                   -- Phase 3c-2：失败条件对照裁定
                                                -- confirmed/refuted/loss_unexplained/no_prediction/inconclusive
    source              TEXT,                   -- deterministic / llm
    closed_at           TEXT,
    raw_json            TEXT NOT NULL,
    created_at          TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);
CREATE INDEX IF NOT EXISTS idx_pm_canon   ON postmortems(canonical_market_id);
CREATE INDEX IF NOT EXISTS idx_pm_outcome ON postmortems(outcome);

-- ----------------------------------------------------------------------------
-- 9. market_prices — 每市场价格时间序列（Phase 3b：Agent P 波动退出）
--    每周期 append 一条 latest_data.polymarket_markets 的 yes/no 价格快照。
--    供波动率/最高水位计算（agent_p 实际读 data/market_price_history.json 事实源；
--    本表是全序列旁路，供分析/API）。
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS market_prices (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    market_id   TEXT,
    slug        TEXT,
    ts          TEXT,
    yes_price   REAL,
    no_price    REAL,
    liquidity   REAL,
    UNIQUE(market_id, ts)
);
CREATE INDEX IF NOT EXISTS idx_mp_market ON market_prices(market_id);
CREATE INDEX IF NOT EXISTS idx_mp_ts     ON market_prices(ts);

-- ----------------------------------------------------------------------------
-- 10. hypotheses — Agent B 研究假设（Phase 3c）
--    每个信号一条结构化假设：方向/置信/预期边/持仓时长/失败条件。
--    与 signals、postmortems 经 signal_uid 关联，形成 假设→结果→复盘 闭环。
--    source=derived（从信号字段确定性派生，3c-1）或 agent_b（B prompt 原生输出，3c-2）。
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS hypotheses (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    hypothesis_uid      TEXT NOT NULL UNIQUE,   -- hash(signal_uid)
    signal_uid          TEXT,
    canonical_market_id TEXT,
    market_name         TEXT,
    direction           TEXT,
    confidence          REAL,
    expected_edge       REAL,
    holding_horizon_days REAL,                  -- 持仓时长（派生自 end_date 或 B 原生）
    thesis              TEXT,                   -- 核心论点（reason/logic_chain）
    risk_summary        TEXT,
    failure_conditions  TEXT,                   -- 失败条件（派生自 risk_notes 或 B 原生）
    source              TEXT,                   -- derived / agent_b
    cycle_id            TEXT,
    created_at          TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    raw_json            TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_hyp_signal ON hypotheses(signal_uid);
CREATE INDEX IF NOT EXISTS idx_hyp_canon  ON hypotheses(canonical_market_id);

-- ----------------------------------------------------------------------------
-- schema 版本（手工迁移用；本轮不引入 Alembic，留一张元表足够）
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS schema_meta (
    key   TEXT PRIMARY KEY,
    value TEXT
);
INSERT OR REPLACE INTO schema_meta(key, value) VALUES ('schema_version', '0.3.3-phase3c2');
