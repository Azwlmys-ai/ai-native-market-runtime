"""
ingest — 影子库回填 / 对账（Phase 1）
============================================================================
从现有 data/*.json(l) 把存量数据回填进 SQLite 影子库 data/runtime.db。

特性：
* **只读** live json/jsonl；唯一写入对象是 runtime.db。对线上流水线零风险。
* 强制开启 shadow（内部设 PA_SHADOW_DB=1）后调用 _shadow 的 upsert。
* 处理真实 schema 漂移：positions.json / paper_portfolio.json / closed_registry
  三个“持仓类”文件字段名不同，这里各自归一到 canonical 持仓 dict。
* 幂等：重复跑不产生重复行（全部 *_uid UPSERT）。

用法：
    python3 -m runtime.ingest            # 回填 + 打印对账
    python3 -m runtime.ingest --reconcile-only
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

os.environ.setdefault("PA_SHADOW_DB", "1")  # ingest 必须开 shadow

from _paths import get_base_dir
from runtime import _shadow


def _data() -> Path:
    return get_base_dir() / "data"


def _load_json(name: str, default):
    p = _data() / name
    if not p.exists():
        return default
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        print(f"[ingest] 跳过不可读 {name}: {exc}")
        return default


def _iter_jsonl(name: str):
    p = _data() / name
    if not p.exists():
        return
    with open(p, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except Exception:
                continue


# 注：三套持仓 schema 的字段归一已集中在 runtime/_shadow.py 的 _canon_pos()，
# ingest 直接传原始 dict 即可（raw_json 保留真正的原始记录）。

# ---------------------------------------------------------------------------
# 回填
# ---------------------------------------------------------------------------

def backfill() -> dict:
    from runtime import market_identity as _mi
    stats: dict[str, int] = {}

    # Phase 2a：先播种 markets 交叉表（latest_data 权威 + signals/portfolio 中带 id 的记录），
    # 让后续只有 slug 的 positions/registry 能解析到 canonical id。
    c = _shadow._conn()
    signals = _load_json("signals.json", [])
    portfolio = _load_json("paper_portfolio.json", [])
    # 先 harvest 业务记录（次级映射），再用权威 latest_data 播种（last_seen 最新 → resolve 优先取它）
    with c:
        for rec in (signals if isinstance(signals, list) else []):
            _mi.harvest(c, rec)
        for rec in (portfolio if isinstance(portfolio, list) else []):
            _mi.harvest(c, rec)
    with c:
        n_seed = _mi.seed_from_latest_data(c, _load_json("latest_data.json", {}) or {})
    stats["markets(seed latest_data)"] = n_seed

    if isinstance(signals, list) and signals:
        _shadow.upsert_signals("ingest", signals)
    stats["signals(json)"] = len(signals) if isinstance(signals, list) else 0

    review = _load_json("review_results.json", {})
    if isinstance(review, dict) and review:
        _shadow.upsert_reviews(review.get("timestamp") or "ingest", review)
    stats["reviews(json approved+rejected)"] = (
        len(review.get("approved_signals", []) or []) + len(review.get("rejected_signals", []) or [])
        if isinstance(review, dict) else 0
    )

    # 持仓：三源字段名不同，但 _shadow._canon_pos 已统一归一，这里直接传原始 dict
    # （raw_json 因此保留真正的原始记录）。先 open 视图后 closed，让生命周期护栏保住已平仓。
    portfolio = _load_json("paper_portfolio.json", [])
    if isinstance(portfolio, list):
        _shadow.upsert_portfolio([p for p in portfolio if isinstance(p, dict)])
    stats["paper_portfolio(json)"] = len(portfolio) if isinstance(portfolio, list) else 0

    positions = _load_json("positions.json", [])
    if isinstance(positions, list):
        _shadow.upsert_positions_open([p for p in positions if isinstance(p, dict)])
    stats["positions(json)"] = len(positions) if isinstance(positions, list) else 0

    registry = _load_json("positions_closed_registry.json", [])
    if isinstance(registry, list):
        _shadow.upsert_positions_closed([p for p in registry if isinstance(p, dict)])
    stats["closed_registry(json)"] = len(registry) if isinstance(registry, list) else 0

    # 成交流水
    n_tr = 0
    for tr in _iter_jsonl("paper_trades.jsonl"):
        _shadow.insert_trade(tr)
        n_tr += 1
    stats["paper_trades(jsonl)"] = n_tr

    # 事件
    n_ev = 0
    for ev in _iter_jsonl("events/runtime_events.jsonl"):
        _shadow.insert_event(ev.get("cycle_id"), ev.get("type"), ev.get("agent"),
                             ev.get("payload"), ev.get("trace_id"))
        n_ev += 1
    stats["runtime_events(jsonl)"] = n_ev

    # 研究假设（Phase 3c-2）：回填 hypotheses 表，保证「删库重建」后失败条件对照仍可用。
    # 不回填 postmortems：让复盘引擎在重建后重跑（postmortems 表空 → 全量重生），
    # 这样存量已平仓持仓也能带上 hypothesis_verdict（失败条件对照）。
    n_hyp = 0
    for hyp in _iter_jsonl("hypotheses.jsonl"):
        if isinstance(hyp, dict) and hyp.get("hypothesis_uid"):
            _shadow.upsert_hypothesis(hyp)
            n_hyp += 1
    stats["hypotheses(jsonl)"] = n_hyp

    # 临时键 reconcile 自动化（2026-06-04）：markets 维表此时已播种，把临时键/裸 slug
    # 持仓升级合并到权威数字 canonical id。放在最后（依赖 markets + positions 都已就位）。
    # 幂等、best-effort：失败不影响回填。覆盖 orchestrator 周期末 + standalone 重建两条路径。
    try:
        stats["positions_reconciled"] = _shadow.upgrade_provisional_positions()
    except Exception as exc:  # noqa: BLE001
        print(f"[ingest] 临时键 reconcile 跳过（非致命）: {exc}", flush=True)
        stats["positions_reconciled"] = 0

    return stats


def reconcile() -> None:
    c = _shadow._conn()
    print("\n=== 对账：DB 表行数 ===")
    for t in ["signals", "reviews", "paper_orders", "paper_positions", "paper_trades", "runtime_events"]:
        n = c.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
        print(f"  {t:18s} {n}")
    print("\n=== markets 维表 ===")
    mk = c.execute("SELECT COUNT(*) FROM markets").fetchone()[0]
    print(f"  markets 行数 {mk}")

    print("\n=== paper_positions 状态归一 ===")
    for row in c.execute("SELECT status, COUNT(*) FROM paper_positions GROUP BY status"):
        print(f"  status={row[0]!r:10s} {row[1]}")
    print("  canonical 解析分布：")
    real = c.execute("SELECT COUNT(*) FROM paper_positions WHERE canonical_market_id NOT LIKE 'slug:%' AND canonical_market_id NOT LIKE 'q:%' AND canonical_market_id<>'unknown'").fetchone()[0]
    prov = c.execute("SELECT COUNT(*) FROM paper_positions WHERE canonical_market_id LIKE 'slug:%' OR canonical_market_id LIKE 'q:%'").fetchone()[0]
    tot = c.execute("SELECT COUNT(*) FROM paper_positions").fetchone()[0]
    print(f"    权威 id={real}  临时键(slug:/q:)={prov}  合计={tot}")
    print("\n=== runtime_events 按类型 ===")
    for row in c.execute("SELECT type, COUNT(*) FROM runtime_events GROUP BY type ORDER BY 2 DESC"):
        print(f"  {row[1]:7d}  {row[0]}")


def main() -> None:
    if "--reconcile-only" not in sys.argv:
        print("=== 回填 (read-only on json, writes runtime.db) ===")
        stats = backfill()
        for k, v in stats.items():
            print(f"  {k:34s} {v}")
    reconcile()
    print(f"\nDB: {_shadow._db_path()}")


if __name__ == "__main__":
    main()
