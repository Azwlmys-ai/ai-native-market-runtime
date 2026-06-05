"""
_shadow — SQLite 影子库写入实现（Phase 0 草案 / Phase 1 启用）
============================================================================
* 由 datastore 经 best-effort 包装调用；这里任何异常都会被上层吞掉。
* 仅当 PA_SHADOW_DB=1 时 datastore 才会调到这里。
* 库文件：data/runtime.db（WAL）。schema 来自同目录 schema.sql。
* 所有写入都用 *_uid 幂等键 + UPSERT，重复周期不产生重复行。

⚠ 草案说明：本实现覆盖 6 表的核心 upsert，足以端到端验证；字段映射贴合
   现有 json 真实键。Phase 1 接入 agent/executor 时再按需补字段。
"""

from __future__ import annotations

import json
import os
import sqlite3
import threading
from pathlib import Path
from typing import Any, Optional

from _paths import get_base_dir
from runtime import datastore as _ds  # 复用 uid()

_LOCK = threading.Lock()
_CONN: Optional[sqlite3.Connection] = None


def _db_path() -> Path:
    # PA_DB_PATH 覆盖：用于落库位置与 json 解耦（如某些挂载/容器路径不支持 SQLite WAL）
    env = os.environ.get("PA_DB_PATH")
    if env:
        return Path(env)
    return get_base_dir() / "data" / "runtime.db"


def _schema_path() -> Path:
    return Path(__file__).resolve().parent / "schema.sql"


def _conn() -> sqlite3.Connection:
    global _CONN
    if _CONN is None:
        with _LOCK:
            if _CONN is None:
                c = sqlite3.connect(str(_db_path()), check_same_thread=False)
                c.row_factory = sqlite3.Row
                # busy_timeout：API 进程与 orchestrator 进程会并发开同一 runtime.db，
                # WAL 下并发写需等待而非立刻 "database is locked"。
                c.execute("PRAGMA busy_timeout=5000")
                _migrate(c)
                _seed_markets_best_effort(c)
                _CONN = c
    return _CONN


# 期望的"后加列"清单（版本演进时往这里加，_migrate 用 ALTER 幂等补齐）。
# 不能靠 CREATE TABLE IF NOT EXISTS —— 它对已存在的旧表是 no-op，不会加列。
_EXPECTED_COLUMNS = {
    "paper_positions": {"canonical_market_id": "TEXT"},  # Phase 2a
    "postmortems": {"hypothesis_verdict": "TEXT"},        # Phase 3c-2
}


def _ensure_columns(c: sqlite3.Connection, table: str, cols: dict) -> None:
    existing = {row[1] for row in c.execute(f"PRAGMA table_info({table})")}
    if not existing:
        return  # 表还不存在（全新库 executescript 会建带列的版本），无需补
    for col, decl in cols.items():
        if col not in existing:
            c.execute(f"ALTER TABLE {table} ADD COLUMN {col} {decl}")


def _migrate(c: sqlite3.Connection) -> None:
    """轻量自迁移（无 Alembic）：建缺失表 → 给旧表补后加列 → 建依赖新列的索引。
    幂等：全新库与旧库都能跑到目标 schema。"""
    # 1. 建缺失的表/基础索引（对已存在表是 no-op）
    c.executescript(_schema_path().read_text(encoding="utf-8"))
    # 2. 给旧表补后加列（ALTER ADD COLUMN，缺则补）
    for table, cols in _EXPECTED_COLUMNS.items():
        _ensure_columns(c, table, cols)
    # 3. 建依赖新列的索引（补列之后才能建）
    c.execute("CREATE INDEX IF NOT EXISTS idx_pos_canon ON paper_positions(canonical_market_id)")
    c.commit()


def _seed_markets_best_effort(c: sqlite3.Connection) -> None:
    """连接初始化时从 latest_data.json 播种 markets 交叉表（best-effort，失败不阻断）。"""
    try:
        from runtime import market_identity as _mi
        p = get_base_dir() / "data" / "latest_data.json"
        if p.exists():
            ld = json.loads(p.read_text(encoding="utf-8"))
            with c:
                _mi.seed_from_latest_data(c, ld)
    except Exception as exc:  # noqa: BLE001
        print(f"[_shadow] markets 播种跳过（非致命）: {exc}", flush=True)


def _j(v: Any) -> str:
    return json.dumps(v, ensure_ascii=False)


def _f(v: Any) -> Optional[float]:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _txt(v: Any) -> Any:
    """防漂移：标量原样绑定；list/dict 等复杂类型转 json 文本，避免 SQLite 绑定报错。"""
    if v is None or isinstance(v, (str, int, float)):
        return v
    return _j(v)


# ---------------------------------------------------------------------------
# signals
# ---------------------------------------------------------------------------

def upsert_signals(cycle_id: str, signals: list[dict]) -> None:
    c = _conn()
    with c:
        for s in signals:
            su = _ds.uid(s.get("market_id"), s.get("direction"),
                         s.get("generated_at") or s.get("timestamp"), s.get("source"))
            c.execute(
                """INSERT INTO signals
                   (signal_uid, cycle_id, market_id, market_slug, market_name, direction,
                    price, confidence, expected_value, position_size, source, reason,
                    logic_chain, risk_notes, learned_rule_match, data_sources, generated_at, raw_json)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(signal_uid) DO UPDATE SET
                     cycle_id=excluded.cycle_id, price=excluded.price,
                     confidence=excluded.confidence, raw_json=excluded.raw_json""",
                (su, cycle_id, str(s.get("market_id") or ""), s.get("market_slug"),
                 s.get("market_name"), s.get("direction"), _f(s.get("price")),
                 _f(s.get("confidence")), _f(s.get("expected_value")), _f(s.get("position_size")),
                 s.get("source"), _txt(s.get("reason")), _j(s.get("logic_chain")), _txt(s.get("risk_notes")),
                 _j(s.get("learned_rule_match")), _j(s.get("data_sources")),
                 s.get("generated_at") or s.get("timestamp"), _j(s)),
            )


# ---------------------------------------------------------------------------
# reviews —— 把聚合对象拆成逐条决策
# ---------------------------------------------------------------------------

def upsert_reviews(cycle_id: str, review_result: dict) -> None:
    """真实结构：approved_signals/rejected_signals 是列表，每项形如
       {market_id, market_name, decision, signal:{...}, review:{...}}。
       approved_paper/rejected_real 等是计数(int)，不在这里用。"""
    c = _conn()
    rows: list[tuple[str, dict]] = []
    for item in review_result.get("approved_signals", []) or []:
        rows.append(("APPROVE", item))
    for item in review_result.get("probe_signals", []) or []:   # Phase 3d 三级
        rows.append(("PAPER_PROBE", item))
    for item in review_result.get("rejected_signals", []) or []:
        rows.append(("REJECT", item))

    with c:
        for default_decision, item in rows:
            sig = item.get("signal") or item
            rv = item.get("review") or item.get("review_result") or {}
            decision = (item.get("decision") or (rv.get("decision") if isinstance(rv, dict) else None)
                        or default_decision)
            mid = str(item.get("market_id") or sig.get("market_id") or "")
            su = _ds.uid(mid, sig.get("direction"),
                         sig.get("generated_at") or sig.get("timestamp"), sig.get("source"))
            ru = _ds.uid(cycle_id, su, decision)
            c.execute(
                """INSERT INTO reviews
                   (review_uid, cycle_id, signal_uid, market_id, market_name, direction,
                    decision, lane, failure_probability, explanation, risk_points, reviewed_at, raw_json)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(review_uid) DO UPDATE SET
                     decision=excluded.decision, raw_json=excluded.raw_json""",
                (ru, cycle_id, su, mid, item.get("market_name") or sig.get("market_name"),
                 sig.get("direction"), decision, None,
                 rv.get("failure_probability") if isinstance(rv, dict) else None,
                 rv.get("explanation") if isinstance(rv, dict) else None,
                 _j(rv.get("risk_points")) if isinstance(rv, dict) else None,
                 review_result.get("timestamp"), _j(item)),
            )


# ---------------------------------------------------------------------------
# paper_orders
# ---------------------------------------------------------------------------

def upsert_orders(cycle_id: str, results: dict, side: str) -> None:
    c = _conn()
    with c:
        for r in results.get("results", []) or []:
            mid = str(r.get("market_id") or "")
            su = _ds.uid(mid, r.get("direction"), r.get("generated_at") or r.get("timestamp"), r.get("source"))
            ou = _ds.uid(cycle_id, su, side)
            c.execute(
                """INSERT INTO paper_orders
                   (order_uid, cycle_id, signal_uid, market_id, market_slug, side,
                    size, notional_usd, entry_price, status, source, ts, raw_json)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(order_uid) DO UPDATE SET
                     status=excluded.status, raw_json=excluded.raw_json""",
                (ou, cycle_id, su, mid, r.get("market_slug"), side,
                 _f(r.get("size") or r.get("position_size")), _f(r.get("notional_usd")),
                 _f(r.get("price") or r.get("entry_price")), r.get("status"),
                 r.get("source"), r.get("ts") or results.get("timestamp"), _j(r)),
            )


def mark_orders_processed(order_uids: list[str]) -> None:
    c = _conn()
    with c:
        c.executemany("UPDATE paper_orders SET processed=1 WHERE order_uid=?",
                      [(u,) for u in order_uids])


def upsert_sell_signals(cycle_id: str, sell_signals: list[dict]) -> None:
    # 卖出信号本质是 SELL 意图，登记为 paper_orders(side=SELL, status=pending 由 raw 决定)
    c = _conn()
    with c:
        for s in sell_signals:
            mid = str(s.get("market_id") or "")
            su = _ds.uid(mid or s.get("market_slug"), s.get("outcome") or s.get("direction"))
            ou = _ds.uid(cycle_id, su, "SELL")
            c.execute(
                """INSERT INTO paper_orders
                   (order_uid, cycle_id, signal_uid, market_id, market_slug, side, status, source, ts, raw_json)
                   VALUES (?,?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(order_uid) DO UPDATE SET raw_json=excluded.raw_json""",
                (ou, cycle_id, su, mid, s.get("market_slug"), "SELL",
                 s.get("status") or "pending", s.get("source"), s.get("timestamp"), _j(s)),
            )


# ---------------------------------------------------------------------------
# paper_positions —— 状态归一
# ---------------------------------------------------------------------------

def _first(p: dict, *keys):
    """取第一个非 None 的字段值，兼容多套 schema 的不同字段名。"""
    for k in keys:
        v = p.get(k)
        if v is not None:
            return v
    return None


def _canon_pos(p: dict) -> dict:
    """把三套持仓 schema 归一到 canonical，保证跨来源 position_uid 与字段一致：
       paper_portfolio.json：direction/entry_price/position_size/realized_pnl/market_name
       positions.json：      outcome/avg_entry_price/shares/unrealized_pnl/market_question（无 market_id）
       closed_registry：     outcome/exit_price/pnl/close_reason
    """
    direction = _first(p, "direction", "outcome")
    direction = str(direction).upper() if direction else None
    return {
        "market_id": str(_first(p, "market_id") or ""),
        "market_slug": _first(p, "market_slug"),
        "market_name": _first(p, "market_name", "question", "market_question"),
        "direction": direction,
        "entry_price": _f(_first(p, "entry_price", "avg_entry_price")),
        "exit_price": _f(_first(p, "exit_price")),
        "position_size": _f(_first(p, "position_size", "shares")),
        "notional_usd": _f(_first(p, "notional_usd", "total_cost")),
        "realized_pnl": _f(_first(p, "realized_pnl", "pnl", "unrealized_pnl")),
        "price_source": _first(p, "price_source"),
        "close_reason": _first(p, "close_reason"),
        "close_source": _first(p, "close_source"),
        "dry_run": 1 if p.get("dry_run", True) else 0,
        "synthetic": 1 if p.get("synthetic") else 0,
        "opened_at": _first(p, "opened_at"),
        "closed_at": _first(p, "closed_at"),
    }


def _upsert_position(c: sqlite3.Connection, p: dict, status: str) -> None:
    from runtime import market_identity as _mi
    cp = _canon_pos(p)
    # Phase 2a：canonical market identity —— position_uid 从权威市场主键计算，跨文件/跨 schema 一致
    canonical = _mi.resolve(c, p)
    pu = _ds.uid(canonical, cp["direction"])
    c.execute(
        """INSERT INTO paper_positions
           (position_uid, canonical_market_id, market_id, market_slug, market_name, direction, status,
            entry_price, exit_price, position_size, notional_usd, realized_pnl,
            price_source, close_reason, close_source, dry_run, synthetic,
            opened_at, closed_at, raw_json, updated_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?, strftime('%Y-%m-%dT%H:%M:%fZ','now'))
           ON CONFLICT(position_uid) DO UPDATE SET
             -- 生命周期护栏：closed 不可被 open 覆盖回去（对齐 5/29 registry 教训）
             status=CASE WHEN paper_positions.status='closed' THEN 'closed' ELSE excluded.status END,
             -- close 相关字段用 COALESCE 保留已有非空值，避免 open 刷新清掉平仓数据
             exit_price=COALESCE(excluded.exit_price, paper_positions.exit_price),
             realized_pnl=COALESCE(excluded.realized_pnl, paper_positions.realized_pnl),
             close_reason=COALESCE(excluded.close_reason, paper_positions.close_reason),
             close_source=COALESCE(excluded.close_source, paper_positions.close_source),
             closed_at=COALESCE(excluded.closed_at, paper_positions.closed_at),
             raw_json=excluded.raw_json, updated_at=strftime('%Y-%m-%dT%H:%M:%fZ','now')""",
        (pu, canonical, cp["market_id"], cp["market_slug"], cp["market_name"],
         cp["direction"], status, cp["entry_price"], cp["exit_price"],
         cp["position_size"], cp["notional_usd"], cp["realized_pnl"],
         cp["price_source"], cp["close_reason"], cp["close_source"],
         cp["dry_run"], cp["synthetic"],
         cp["opened_at"], cp["closed_at"], _j(p)),
    )


def upsert_positions_open(positions: list[dict]) -> None:
    c = _conn()
    with c:
        for p in positions:
            _upsert_position(c, p, p.get("status") or "open")


def upsert_positions_closed(registry_records: list[dict]) -> None:
    c = _conn()
    with c:
        for p in registry_records:
            _upsert_position(c, p, "closed")


def upsert_portfolio(positions: list[dict]) -> None:
    c = _conn()
    with c:
        for p in positions:
            st = p.get("status") or ("closed" if p.get("closed_at") else "open")
            _upsert_position(c, p, st)


# ---------------------------------------------------------------------------
# paper_trades
# ---------------------------------------------------------------------------

def insert_trade(trade: dict) -> None:
    c = _conn()
    tu = _ds.uid(trade.get("market_id"), trade.get("type") or trade.get("side"), trade.get("ts"))
    with c:
        c.execute(
            """INSERT OR IGNORE INTO paper_trades
               (trade_uid, position_uid, market_id, type, side, size, entry_price, exit_price,
                notional_usd, realized_pnl, close_reason, market_name, source, ts, raw_json)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (tu, None, str(trade.get("market_id") or ""),
             trade.get("type"), trade.get("side"), _f(trade.get("size")),
             _f(trade.get("entry_price")), _f(trade.get("exit_price")),
             _f(trade.get("notional_usd")), _f(trade.get("realized_pnl")),
             trade.get("close_reason"), trade.get("market_name"),
             trade.get("source"), trade.get("ts"), _j(trade)),
        )


# ---------------------------------------------------------------------------
# runtime_events
# ---------------------------------------------------------------------------

def insert_market_prices(points: list[dict]) -> None:
    """append 价格快照到 market_prices 表（按 market_id+ts 去重）。"""
    c = _conn()
    with c:
        for p in points:
            c.execute(
                """INSERT OR IGNORE INTO market_prices (market_id, slug, ts, yes_price, no_price, liquidity)
                   VALUES (?,?,?,?,?,?)""",
                (str(p.get("market_id") or ""), p.get("slug"), p.get("ts"),
                 _f(p.get("yes_price")), _f(p.get("no_price")), _f(p.get("liquidity"))),
            )


def insert_event(cycle_id: str, type_: str, agent: str,
                 payload: Optional[dict], trace_id: Optional[str]) -> None:
    c = _conn()
    with c:
        c.execute(
            """INSERT OR IGNORE INTO runtime_events
               (event_uid, ts, cycle_id, type, agent, trace_id, payload)
               VALUES (?, strftime('%Y-%m-%dT%H:%M:%fZ','now'), ?, ?, ?, ?, ?)""",
            (trace_id, cycle_id, type_, agent, trace_id, _j(payload or {})),
        )


# ---------------------------------------------------------------------------
# 只读查询（Phase 2b：供 FastAPI GET 用）
# ---------------------------------------------------------------------------

def _rows(sql: str, params: tuple = ()) -> list[dict]:
    c = _conn()
    return [dict(r) for r in c.execute(sql, params).fetchall()]


def query_positions(status: Optional[str] = None, limit: int = 500) -> list[dict]:
    if status:
        return _rows(
            "SELECT * FROM paper_positions WHERE status=? ORDER BY updated_at DESC LIMIT ?",
            (status, limit))
    return _rows("SELECT * FROM paper_positions ORDER BY updated_at DESC LIMIT ?", (limit,))


def query_trades(limit: int = 200) -> list[dict]:
    return _rows("SELECT * FROM paper_trades ORDER BY id DESC LIMIT ?", (limit,))


def query_signals(limit: int = 200) -> list[dict]:
    return _rows("SELECT * FROM signals ORDER BY id DESC LIMIT ?", (limit,))


def query_reviews(limit: int = 200) -> list[dict]:
    return _rows("SELECT * FROM reviews ORDER BY id DESC LIMIT ?", (limit,))


def query_markets(limit: int = 500) -> list[dict]:
    return _rows("SELECT * FROM markets ORDER BY last_seen DESC LIMIT ?", (limit,))


def query_postmortems(outcome: Optional[str] = None, limit: int = 200) -> list[dict]:
    if outcome:
        return _rows("SELECT * FROM postmortems WHERE outcome=? ORDER BY id DESC LIMIT ?",
                     (outcome, limit))
    return _rows("SELECT * FROM postmortems ORDER BY id DESC LIMIT ?", (limit,))


def closed_positions_without_postmortem() -> list[dict]:
    """已平仓但还没复盘的持仓（供 postmortem 引擎逐笔生成）。"""
    return _rows(
        """SELECT p.* FROM paper_positions p
           LEFT JOIN postmortems m ON m.position_uid = p.position_uid
           WHERE p.status='closed' AND m.id IS NULL""")


def latest_signal_for(canonical_market_id: str, direction: Optional[str]) -> Optional[dict]:
    """按 canonical id（= signals.market_id）+ 方向找最近的原始信号，供复盘取 hypothesis/expected_edge。"""
    if not canonical_market_id:
        return None
    if direction:
        rows = _rows(
            "SELECT * FROM signals WHERE market_id=? AND UPPER(COALESCE(direction,''))=? ORDER BY id DESC LIMIT 1",
            (canonical_market_id, direction.upper()))
    else:
        rows = _rows("SELECT * FROM signals WHERE market_id=? ORDER BY id DESC LIMIT 1",
                     (canonical_market_id,))
    return rows[0] if rows else None


def query_hypotheses(limit: int = 200) -> list[dict]:
    return _rows("SELECT * FROM hypotheses ORDER BY id DESC LIMIT ?", (limit,))


def hypothesis_for_signal(signal_uid: Optional[str]) -> Optional[dict]:
    """按 signal_uid 找最近的研究假设（Phase 3c-2：供复盘对照失败条件）。"""
    if not signal_uid:
        return None
    rows = _rows("SELECT * FROM hypotheses WHERE signal_uid=? ORDER BY id DESC LIMIT 1",
                 (signal_uid,))
    return rows[0] if rows else None


def upsert_hypothesis(rec: dict) -> None:
    c = _conn()
    with c:
        c.execute(
            """INSERT INTO hypotheses
               (hypothesis_uid, signal_uid, canonical_market_id, market_name, direction,
                confidence, expected_edge, holding_horizon_days, thesis, risk_summary,
                failure_conditions, source, cycle_id, raw_json)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(hypothesis_uid) DO UPDATE SET
                 confidence=excluded.confidence, expected_edge=excluded.expected_edge,
                 holding_horizon_days=excluded.holding_horizon_days, thesis=excluded.thesis,
                 risk_summary=excluded.risk_summary, failure_conditions=excluded.failure_conditions,
                 source=excluded.source, raw_json=excluded.raw_json""",
            (rec.get("hypothesis_uid"), rec.get("signal_uid"), rec.get("canonical_market_id"),
             rec.get("market_name"), rec.get("direction"), _f(rec.get("confidence")),
             _f(rec.get("expected_edge")), _f(rec.get("holding_horizon_days")),
             _txt(rec.get("thesis")), _txt(rec.get("risk_summary")),
             _txt(rec.get("failure_conditions")), rec.get("source"), rec.get("cycle_id"), _j(rec)),
        )


def upsert_postmortem(rec: dict) -> None:
    c = _conn()
    with c:
        c.execute(
            """INSERT INTO postmortems
               (postmortem_uid, position_uid, canonical_market_id, market_name, direction,
                signal_uid, hypothesis, expected_edge, confidence, entry_price, exit_price,
                realized_pnl, outcome, failure_reason, liquidity_issue, timing_issue, model_issue,
                hypothesis_verdict, source, closed_at, raw_json)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(postmortem_uid) DO UPDATE SET
                 failure_reason=excluded.failure_reason, source=excluded.source,
                 liquidity_issue=excluded.liquidity_issue, timing_issue=excluded.timing_issue,
                 model_issue=excluded.model_issue, hypothesis_verdict=excluded.hypothesis_verdict,
                 raw_json=excluded.raw_json""",
            (rec.get("postmortem_uid"), rec.get("position_uid"), rec.get("canonical_market_id"),
             rec.get("market_name"), rec.get("direction"), rec.get("signal_uid"),
             _txt(rec.get("hypothesis")), _f(rec.get("expected_edge")), _f(rec.get("confidence")),
             _f(rec.get("entry_price")), _f(rec.get("exit_price")), _f(rec.get("realized_pnl")),
             rec.get("outcome"), _txt(rec.get("failure_reason")),
             1 if rec.get("liquidity_issue") else 0, 1 if rec.get("timing_issue") else 0,
             1 if rec.get("model_issue") else 0, rec.get("hypothesis_verdict"),
             rec.get("source"), rec.get("closed_at"), _j(rec)),
        )


def positions_summary() -> dict:
    c = _conn()
    row = c.execute(
        """SELECT
             COUNT(*) AS total,
             SUM(CASE WHEN status='open' THEN 1 ELSE 0 END) AS open,
             SUM(CASE WHEN status='closed' THEN 1 ELSE 0 END) AS closed,
             COALESCE(SUM(CASE WHEN status='closed' THEN realized_pnl ELSE 0 END),0) AS realized_pnl
           FROM paper_positions"""
    ).fetchone()
    return dict(row) if row else {}


# ---------------------------------------------------------------------------
# 临时键 reconcile（Phase 2a 尾巴；自动化 2026-06-04）：把 canonical 不是权威
# 数字 id 的历史持仓（slug:<x> 临时键 + 裸 slug + q:），在 markets 出现 slug/question→id
# 映射后，重 key 到权威数字 id（合并进已有 id 行）。
# ---------------------------------------------------------------------------

def _numeric_market_id_for(c: sqlite3.Connection, slugs: list, question: Optional[str]) -> Optional[str]:
    """按候选 slug（精确）→ question（精确）在 markets 找**纯数字** market_id。
    只认数字 id，真·slug-only 市场（markets.market_id=slug 本身）返回 None，不会被误升级。"""
    for s in slugs:
        if not s:
            continue
        m = c.execute(
            "SELECT market_id FROM markets WHERE slug=? AND market_id GLOB '[0-9]*' "
            "ORDER BY last_seen DESC LIMIT 1", (s,)).fetchone()
        if m and m[0] and str(m[0]).isdigit():
            return str(m[0])
    if question:
        m = c.execute(
            "SELECT market_id FROM markets WHERE question=? AND market_id GLOB '[0-9]*' "
            "ORDER BY last_seen DESC LIMIT 1", (question,)).fetchone()
        if m and m[0] and str(m[0]).isdigit():
            return str(m[0])
    return None


def upgrade_provisional_positions() -> int:
    """把临时键/裸 slug 持仓升级合并到权威数字 canonical id 行。返回成功升级的行数。

    匹配顺序：market_slug / 去 'slug:' 前缀的 canonical / canonical 本身 → markets 数字 id；
    退回 market_name(question) 精确匹配。**仅当解析到纯数字 id 才升级**，真·slug-only 市场不动。
    幂等：没有可升级的（含已是数字 canonical）就返回 0。
    """
    c = _conn()
    upgraded = 0
    with c:
        # 非纯数字 canonical = 待 reconcile（slug:、裸 slug、q:、unknown）
        rows = c.execute(
            "SELECT position_uid, canonical_market_id, market_slug, market_name, direction, raw_json "
            "FROM paper_positions WHERE canonical_market_id NOT GLOB '[0-9]*'"
        ).fetchall()
        for r in rows:
            cid = r["canonical_market_id"] or ""
            cand_slugs = []
            if r["market_slug"]:
                cand_slugs.append(r["market_slug"])
            if cid.startswith("slug:"):
                cand_slugs.append(cid[5:])
            elif cid and not cid.startswith(("q:", "unknown")):
                cand_slugs.append(cid)  # 裸 slug 本身
            numeric_id = _numeric_market_id_for(c, cand_slugs, r["market_name"])
            if not numeric_id:
                continue
            try:
                raw = json.loads(r["raw_json"]) if r["raw_json"] else {}
            except Exception:
                raw = {}
            raw["market_id"] = numeric_id          # 注入权威数字 id
            target_uid = _ds.uid(numeric_id, _canon_pos(raw).get("direction"))
            tgt = c.execute(
                "SELECT status FROM paper_positions WHERE position_uid=?", (target_uid,)).fetchone()
            if tgt is not None and (tgt[0] == "closed"):
                # 权威数字行已存在且已平仓 → provisional 是重复，直接删；
                # 不 upsert 它（避免 incoming 的 0/空值经 COALESCE 覆盖权威平仓 pnl/exit）。
                c.execute("DELETE FROM paper_positions WHERE position_uid=?", (r["position_uid"],))
            else:
                # 权威行不存在 或 仍 open（此时让 provisional 的平仓数据可上位）→ re-key 合并
                status = "closed" if raw.get("closed_at") else (raw.get("status") or "open")
                _upsert_position(c, raw, status)
                if target_uid != r["position_uid"]:
                    c.execute("DELETE FROM paper_positions WHERE position_uid=?", (r["position_uid"],))
            upgraded += 1
    return upgraded
