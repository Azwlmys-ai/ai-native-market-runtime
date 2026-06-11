"""
DataStore — 唯一写入门面（Phase 0 契约草案）
============================================================================
定位
----
把当前散落在 ~8 个模块里的 live 文件 `open(w)/json.dump` 写入，收口到这一个
模块。Phase 0 内部仍写同样的 json 文件，**行为零变化**；有了这个门面，
Phase 1 的 SQLite 影子写只需在每个函数里加一行 `_shadow.*`，不散落到各 agent。

设计决策（已拍板）
------------------
* 模块函数，不是单例类 —— 直接 `from runtime import datastore as ds; ds.put_signals(...)`
* json 永远先写、写成功即算成功；shadow 写在其后，best-effort，失败只记日志绝不抛
* 没有任何读路径依赖 DB —— dashboard 仍读 json，dry-run 链路完全不经过 DB
* shadow 默认关闭，由环境变量 PA_SHADOW_DB=1 打开（Phase 1 才开）

写入权归属（每个 live 文件 = 一个 owner 函数）
----------------------------------------------
  signals.json                     -> put_signals()
  review_results.json/approved      -> put_review()
  execution_results.json            -> record_executions(side="BUY")
  sell_execution_results.json       -> record_executions(side="SELL")
  sell_signals.json                 -> put_sell_signals()   （“已处理”不再回写文件，见 mark_orders_processed）
  positions.json                    -> set_positions()
  positions_closed_registry.json    -> upsert_closed_positions()
  paper_portfolio.json              -> save_portfolio()
  paper_trades.jsonl                -> append_paper_trade()
  orchestrator_status.json          -> write_status()
  runtime_events.jsonl              -> emit_event()  （委托现有 event_logger，append 不变）

⚠ 本文件是 Phase 0 契约草案：json 写入已是可直接采用的真实实现（纯重构、零行为变化）；
   shadow 写入经 `runtime._shadow`，默认 no-op/关闭，Phase 1 再落库。
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any, Iterable, Optional

from _paths import get_base_dir

try:
    from event_logger import write_event as _write_event
except Exception:  # event_logger 不可用时降级，绝不阻断
    _write_event = None

try:
    from runtime import _shadow
except Exception:  # 影子库模块缺失时全程 no-op
    _shadow = None


# ---------------------------------------------------------------------------
# 基础设施
# ---------------------------------------------------------------------------

def _data_dir(base_dir: Optional[Path] = None) -> Path:
    base = Path(base_dir) if base_dir else get_base_dir()
    d = base / "data"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _shadow_enabled() -> bool:
    return os.environ.get("PA_SHADOW_DB", "").lower() in ("1", "true", "yes")


def _atomic_write_json(path: Path, obj: Any) -> None:
    """原子落盘：写临时文件 + os.replace，避免读者读到半截 json。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(obj, f, indent=2, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def _append_jsonl(path: Path, record: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
        f.flush()
        os.fsync(f.fileno())


def _shadow_call(fn_name: str, *args) -> None:
    """统一的 best-effort 影子写：关则跳过，错则吞掉并记日志，绝不影响主流程。"""
    if not _shadow_enabled() or _shadow is None:
        return
    try:
        getattr(_shadow, fn_name)(*args)
    except Exception as exc:  # noqa: BLE001
        print(f"[datastore.shadow] {fn_name} 非致命失败: {exc}", flush=True)


def uid(*parts: Any) -> str:
    """业务幂等键：对入参做稳定 hash。用于 *_uid 列的 upsert。"""
    raw = "|".join("" if p is None else str(p) for p in parts)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


# ---------------------------------------------------------------------------
# 信号 signals.json  (owner: orchestrator 步骤 12.5)
# ---------------------------------------------------------------------------

def put_signals(cycle_id: str, signals: list[dict], base_dir: Optional[Path] = None) -> None:
    """整体替换 data/signals.json（完整替换，不追加旧信号）。

    契约：调用方传入“本轮全部 fresh 信号”，本函数负责落盘 + 影子 upsert。
    """
    _atomic_write_json(_data_dir(base_dir) / "signals.json", signals)
    _shadow_call("upsert_signals", cycle_id, signals)


# ---------------------------------------------------------------------------
# 审查 review_results.json + approved_signals.json  (owner: agent_m)
# ---------------------------------------------------------------------------

def put_review(cycle_id: str, review_result: dict, approved_signals: Optional[list] = None,
               base_dir: Optional[Path] = None) -> None:
    """写 review_results.json 聚合对象，并派生 approved_signals.json。

    review_result 沿用现有结构（含 approved_paper/approved_real/rejected_* 等）。
    approved_signals 显式传入时用它写 approved_signals.json，否则取 review_result["approved_signals"]。
    影子库按 (cycle, signal) 拆成逐条 reviews 行。
    """
    dd = _data_dir(base_dir)
    _atomic_write_json(dd / "review_results.json", review_result)

    approved = approved_signals if approved_signals is not None else (review_result.get("approved_signals", []) or [])
    _atomic_write_json(dd / "approved_signals.json", approved)

    _shadow_call("upsert_reviews", cycle_id, review_result)


# ---------------------------------------------------------------------------
# 执行结果 execution_results.json / sell_execution_results.json
#   (owner: signal_executor / sell_executor；orchestrator 的 skipped 占位也走这里)
# ---------------------------------------------------------------------------

def put_approved_signals(approved_signals: list, base_dir: Optional[Path] = None) -> None:
    """重写 approved_signals.json（执行器输入）。Phase 3f-loop Fix1：配对完整性执行门用。

    这是 Agent M 审查**之后**的执行门，对协整裸腿做剔除；只改执行器输入文件，
    不改 review_results.json（审查决策的审计记录保持原样）。经门面原子落盘。
    """
    _atomic_write_json(_data_dir(base_dir) / "approved_signals.json", approved_signals)


def record_executions(cycle_id: str, results: dict, side: str = "BUY",
                      base_dir: Optional[Path] = None) -> None:
    """写执行结果聚合对象。side=BUY→execution_results.json，SELL→sell_execution_results.json。

    results 沿用现有结构（含 total/success/dry_run/simulated/failed/results[...]）。
    影子库按单 order 拆成 paper_orders 行；status 严格沿用 6 桶，dry_run 不混入 success。
    """
    fname = "execution_results.json" if side.upper() == "BUY" else "sell_execution_results.json"
    _atomic_write_json(_data_dir(base_dir) / fname, results)
    _shadow_call("upsert_orders", cycle_id, results, side.upper())


def mark_orders_processed(order_uids: Iterable[str]) -> None:
    """把已被 executor 处理的卖出意图标记为 processed=1。

    这条替代了旧的“sell_executor 回写清空 sell_signals.json”双写语义：
    不再回写产出文件，processed 状态进 paper_orders.processed。
    """
    _shadow_call("mark_orders_processed", list(order_uids))


# ---------------------------------------------------------------------------
# 卖出信号 sell_signals.json  (owner: agent_p 产出)
# ---------------------------------------------------------------------------

def put_sell_signals(cycle_id: str, sell_signals: list[dict], base_dir: Optional[Path] = None) -> None:
    """agent_p 产出卖出信号 → 整体替换 sell_signals.json（产出归 agent_p 单写）。"""
    _atomic_write_json(_data_dir(base_dir) / "sell_signals.json", sell_signals)
    _shadow_call("upsert_sell_signals", cycle_id, sell_signals)


# ---------------------------------------------------------------------------
# 持仓 positions.json  (owner: agent_p；orchestrator 不再直接写)
# ---------------------------------------------------------------------------

def set_positions(positions: list[dict], base_dir: Optional[Path] = None) -> None:
    """整体替换 data/positions.json，并 upsert 到 paper_positions（status=open）。"""
    _atomic_write_json(_data_dir(base_dir) / "positions.json", positions)
    _shadow_call("upsert_positions_open", positions)


def upsert_closed_positions(registry_records: list[dict], base_dir: Optional[Path] = None) -> None:
    """写 positions_closed_registry.json，并把对应持仓在 paper_positions 标 status=closed。

    这是“状态归一”的接缝：json 侧暂时仍分两个文件，影子库侧已合到一张表的 status 列。
    """
    _atomic_write_json(_data_dir(base_dir) / "positions_closed_registry.json", registry_records)
    _shadow_call("upsert_positions_closed", registry_records)


# ---------------------------------------------------------------------------
# Paper 组合 / 成交  (owner: paper_pnl)
# ---------------------------------------------------------------------------

def save_portfolio(positions: list[dict], base_dir: Optional[Path] = None) -> None:
    """整体替换 data/paper_portfolio.json，并 upsert paper_positions。"""
    _atomic_write_json(_data_dir(base_dir) / "paper_portfolio.json", positions)
    _shadow_call("upsert_portfolio", positions)


def append_paper_trade(trade: dict, base_dir: Optional[Path] = None) -> None:
    """append 一条成交到 data/paper_trades.jsonl，并插入 paper_trades 表。

    收敛点：signal_executor 不再自行 append，统一改调本函数。
    """
    _append_jsonl(_data_dir(base_dir) / "paper_trades.jsonl", trade)
    _shadow_call("insert_trade", trade)


# ---------------------------------------------------------------------------
# 周期状态 orchestrator_status.json  (owner: orchestrator)
# ---------------------------------------------------------------------------

def write_status(payload: dict, base_dir: Optional[Path] = None) -> None:
    _atomic_write_json(_data_dir(base_dir) / "orchestrator_status.json", payload)


# ---------------------------------------------------------------------------
# 复盘 postmortems.jsonl  (owner: Agent G / runtime.postmortem) — Phase 3a
# ---------------------------------------------------------------------------

def append_postmortem(record: dict, base_dir: Optional[Path] = None) -> None:
    """append 一条结构化复盘到 data/postmortems.jsonl（事实源）+ 影子 postmortems 表。"""
    _append_jsonl(_data_dir(base_dir) / "postmortems.jsonl", record)
    _shadow_call("upsert_postmortem", record)


# ---------------------------------------------------------------------------
# 研究假设 hypotheses.jsonl  (owner: Agent B / runtime.hypothesis) — Phase 3c
# ---------------------------------------------------------------------------

def append_hypothesis(record: dict, base_dir: Optional[Path] = None) -> None:
    """append 一条研究假设到 data/hypotheses.jsonl（事实源）+ 影子 hypotheses 表。"""
    _append_jsonl(_data_dir(base_dir) / "hypotheses.jsonl", record)
    _shadow_call("upsert_hypothesis", record)


# ---------------------------------------------------------------------------
# 模型有效性  (owner: runtime.model_effectiveness) — Phase 3e
# ---------------------------------------------------------------------------

def write_model_effectiveness(report: dict, base_dir: Optional[Path] = None) -> None:
    """整体替换 data/model_effectiveness.json（事实源）+ upsert 影子 model_effectiveness 表。

    report 为 model_effectiveness.compute() 产出的聚合报告（by_rule/by_family/by_agent）。
    """
    _atomic_write_json(_data_dir(base_dir) / "model_effectiveness.json", report)
    _shadow_call("upsert_model_effectiveness", report)


def write_rule_weights(report: dict, base_dir: Optional[Path] = None) -> None:
    """整体替换 data/rule_effectiveness.json（建议产物）+ upsert 影子 rule_weights 表。

    report 为 rule_weights.compute() 产出的权重建议（by_rule/by_family + summary）。
    ⚠ 仅建议，enforced=False，不接入 live 交易链路。
    """
    _atomic_write_json(_data_dir(base_dir) / "rule_effectiveness.json", report)
    _shadow_call("upsert_rule_weights", report)


def write_correlation_signals(report: dict, base_dir: Optional[Path] = None) -> None:
    """整体替换 data/correlation_signals.json（研究产物）+ upsert 影子 correlation_signals 表。

    report 为 cointegration.compute() 产出的协整/spread 研究候选（candidates + 元信息）。
    ⚠ 研究产物，enforced=False，不接入 live 交易链路。
    """
    _atomic_write_json(_data_dir(base_dir) / "correlation_signals.json", report)
    _shadow_call("upsert_correlation_signals", report)


def write_regime_states(report: dict, base_dir: Optional[Path] = None) -> None:
    """整体替换 data/regime_states.json（研究产物）+ upsert 影子 regime_states 表。

    report 为 regime_hmm.compute() 产出的 HMM 市场状态识别快照（regimes + 元信息）。
    ⚠ 研究产物，enforced=False，不接入 live 交易链路。
    """
    _atomic_write_json(_data_dir(base_dir) / "regime_states.json", report)
    _shadow_call("upsert_regime_states", report)


def write_regime_effectiveness(report: dict, base_dir: Optional[Path] = None) -> None:
    """整体替换 data/regime_effectiveness.json（学习产物）+ upsert 影子 regime_effectiveness 表。

    report 为 regime_effectiveness.compute() 产出的 regime 有效性聚合（by_regime + 元信息）。
    ⚠ 学习产物，enforced=False，不接入 live 交易链路。
    """
    _atomic_write_json(_data_dir(base_dir) / "regime_effectiveness.json", report)
    _shadow_call("upsert_regime_effectiveness", report)


def write_volatility_states(report: dict, base_dir: Optional[Path] = None) -> None:
    """整体替换 data/volatility_states.json（研究产物）+ upsert 影子 volatility_states 表。

    report 为 garch.compute() 产出的 GARCH(1,1) 波动率/风险状态快照（states + 元信息）。
    ⚠ 研究产物，enforced=False，不接入 live 交易链路。
    """
    _atomic_write_json(_data_dir(base_dir) / "volatility_states.json", report)
    _shadow_call("upsert_volatility_states", report)


def write_sizing_suggestions(report: dict, base_dir: Optional[Path] = None) -> None:
    """整体替换 data/sizing_suggestions.json（建议产物）+ upsert 影子 sizing_suggestions 表。

    report 为 position_sizing.compute() 产出的 Kelly+Markowitz 仓位建议（suggestions + 元信息）。
    ⚠ 建议产物，enforced=False，不接入 agent_m/executor/probe 仓位。
    """
    _atomic_write_json(_data_dir(base_dir) / "sizing_suggestions.json", report)
    _shadow_call("upsert_sizing_suggestions", report)


def write_enforcement_audit(report: dict, base_dir: Optional[Path] = None) -> None:
    """整体替换 data/enforcement_audit.json（纸面强制层审计）+ upsert 影子 enforcement_audit 表。

    report 为 enforcement.enforce_signals() 产出的逐条 position_size 调整审计（adjustments + 门控）。
    ⚠ 仅在 env 门控 PA_ENFORCE_* 开启时由 orchestrator 调用；只改 position_size，不绕过 Agent M/dry-run。
    """
    _atomic_write_json(_data_dir(base_dir) / "enforcement_audit.json", report)
    _shadow_call("upsert_enforcement_audit", report)


# ---------------------------------------------------------------------------
# 市场价格历史  (owner: orchestrator/agent_a) — Phase 3b
# ---------------------------------------------------------------------------

def record_market_prices(points: list[dict], base_dir: Optional[Path] = None, cap: int = 60) -> None:
    """每周期记录每市场价格快照。

    事实源：data/market_price_history.json —— 形如 {market_id: [{ts, yes_price, no_price, liquidity}, ...]}，
    每市场滚动保留最近 cap 个点（agent_p 读这个算波动率/最高水位，体积有界）。
    影子：market_prices 表存全序列（分析/API）。
    points: [{market_id, slug, ts, yes_price, no_price, liquidity}, ...]
    """
    hist_path = _data_dir(base_dir) / "market_price_history.json"
    hist: dict = {}
    if hist_path.exists():
        try:
            hist = json.loads(hist_path.read_text(encoding="utf-8"))
            if not isinstance(hist, dict):
                hist = {}
        except Exception:
            hist = {}
    for p in points:
        mid = str(p.get("market_id") or "")
        if not mid:
            continue
        series = hist.setdefault(mid, [])
        series.append({"ts": p.get("ts"), "yes_price": p.get("yes_price"),
                       "no_price": p.get("no_price"), "liquidity": p.get("liquidity")})
        if len(series) > cap:
            del series[:-cap]
    _atomic_write_json(hist_path, hist)
    _shadow_call("insert_market_prices", points)


# ---------------------------------------------------------------------------
# 外部资产价格历史  (owner: orchestrator) — Phase 3f-x 跨资产协整
# ---------------------------------------------------------------------------

def record_asset_prices(points: list, base_dir: Optional[Path] = None, cap: int = 60) -> None:
    """记录外部资产（加密/美股/宏观）价格滚动历史，供跨资产协整研究。

    事实源：data/asset_price_history.json —— {symbol: [{ts, price, kind}, ...]}，
    每 symbol 滚动保留最近 cap 个点（与 market_price_history 同构，体积有界）。
    纯 json 事实源（研究输入），不落影子表。points: [{symbol, ts, price, kind}, ...]。
    """
    hist_path = _data_dir(base_dir) / "asset_price_history.json"
    hist: dict = {}
    if hist_path.exists():
        try:
            hist = json.loads(hist_path.read_text(encoding="utf-8"))
            if not isinstance(hist, dict):
                hist = {}
        except Exception:
            hist = {}
    for p in points:
        sym = str(p.get("symbol") or "")
        price = p.get("price")
        if not sym or price is None:
            continue
        series = hist.setdefault(sym, [])
        series.append({"ts": p.get("ts"), "price": price, "kind": p.get("kind")})
        if len(series) > cap:
            del series[:-cap]
    _atomic_write_json(hist_path, hist)


# ---------------------------------------------------------------------------
# 事件 runtime_events.jsonl  (委托 event_logger，append 语义不变)
# ---------------------------------------------------------------------------

def emit_event(
    *,
    cycle_id: str,
    type: str,
    agent: str,
    payload: Optional[dict] = None,
    trace_id: Optional[str] = None,
) -> None:
    """委托现有 event_logger.write_event（crash-safe append），并影子插入 runtime_events。

    不替换 event_logger，只在其上加一层 shadow 落库，jsonl append 完全不动。
    """
    if _write_event is not None:
        _write_event(cycle_id=cycle_id, type=type, agent=agent,
                     payload=payload, trace_id=trace_id)
    _shadow_call("insert_event", cycle_id, type, agent, payload, trace_id)


__all__ = [
    "put_signals", "put_review", "record_executions", "mark_orders_processed",
    "put_sell_signals", "set_positions", "upsert_closed_positions",
    "save_portfolio", "append_paper_trade", "write_status", "emit_event", "uid",
    "append_postmortem", "append_hypothesis", "record_market_prices",
    "write_model_effectiveness", "write_rule_weights", "write_correlation_signals",
    "put_approved_signals", "record_asset_prices", "write_regime_states",
    "write_regime_effectiveness", "write_volatility_states", "write_sizing_suggestions",
]
