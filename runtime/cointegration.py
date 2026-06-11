"""
cointegration — 协整 / spread 研究引擎（Phase 3f：第一个「真实模型」）
============================================================================
定位（对齐 PRD 第十一节第一优先级 + §9 跨市场关联发现 + §10「模型是研究工具」）
----------------------------------------------------------------------------
这是系统第一个**真实统计模型**，不再是 agent_b 的规则匹配。它对市场价格序列做
**配对协整 / spread 均值回归**分析，产出带**真实 `models_used=["cointegration"]`**
的研究候选信号——从而让 Learning Runtime 的模型标签从「规则名」升级为「真实模型」。

> 关键纪律：本引擎是**研究工具**，产出研究候选写入独立产物 `data/correlation_signals.json`，
> **不接入 live executor / agent_b 信号链路**（同 3e-2 advisory 纪律）。把候选喂进
> 真正的 signals→review→execute 链路是后续 env 门控的独立步骤，需单独评审。

方法（Engle-Granger 轻量版，仅依赖 numpy，避开 statsmodels）
------------------------------------------------------------
对一对市场价格序列 a、b（对齐末 N 点）：
  1. 对冲比 beta：OLS 把 a 回归到 b（a ≈ beta·b + c）。
  2. spread = a − beta·b；记 mean/std；当前点 z = (spread[-1] − mean) / std。
  3. Pearson 相关 corr(a,b)。
  4. AR(1) 系数 phi：spread[t] 回归 spread[t-1]；半衰期 = −ln2 / ln(phi)（0<phi<1 才有意义）。
  5. 平稳/均值回归判据：0<phi<1（spread 收敛）；|corr| 高；|z| 越界 → 配对回归候选。

防伪相关护栏（点少时必须）
--------------------------
点数少（当前每序列仅 ~10 点）极易出现 ±1.0 伪相关。故要求：
  * 两腿都「真的在动」（std>eps）且不同取值数 >= MIN_DISTINCT；
  * 点数 >= MIN_POINTS；corr、z、half_life 全部过阈值。
并对每条候选打 `data_sufficiency`（low / medium），诚实标注当前为低数据候选。

纯确定性、numpy-only、沙箱可单测；加法产物，不改任何交易行为。
"""

from __future__ import annotations

import json
import math
import os
from datetime import datetime, timezone
from itertools import combinations
from pathlib import Path
from typing import Optional

import numpy as np

from runtime import datastore as _ds
from runtime import price_history as _ph

SCHEMA_VERSION = "0.3.14-phase5-explore-tier"  # +entry_price/expected_return(校准) +探索层 tier
MODEL_NAME = "cointegration"
METHOD = "engle_granger_lite"

# 研究层阈值（保守；点少时防伪相关）
MIN_POINTS = 8          # 每序列最少点数
MIN_DISTINCT = 4        # 最少不同取值数（防 2 值序列伪 ±1.0）
EPS = 1e-9
CORR_MIN = 0.80         # 相关下限
Z_MIN = 2.0             # spread 偏离下限（标准差倍数）
HALF_LIFE_MAX = 20.0    # 均值回归半衰期上限（周期）
TOP_K = 20              # 候选上限（按 |z| 排序取头部；可被 PA_COINT_TOP_K 覆盖）


def _top_k(default: int = TOP_K) -> int:
    """候选上限，env PA_COINT_TOP_K 可调（非法值回退默认）。"""
    try:
        v = int(os.environ.get("PA_COINT_TOP_K", "") or default)
        return max(1, v)
    except (TypeError, ValueError):
        return default
DATA_SUFFICIENCY_MEDIUM = 20  # 点数 >= 此值才算 medium，否则 low

# 探索层（PRD §6 paper_probe「弱关联低风险试错」；env 门控 PA_COINT_EXPLORE=1，默认关）。
# 放松 corr/|z| 阈值产出**低置信、tier=exploration** 弱关联候选，喂小额 paper_probe 拿反馈，
# 由 model_effectiveness(by_model) 事后验证/降权。半衰期(平稳性)过滤**仍保留**——只放松相关/偏离，
# 不放松「价差必须均值回归」，避免追非平稳趋势。
EXPLORE_CORR_MIN = 0.50       # 探索相关下限（可被 PA_COINT_EXPLORE_CORR 覆盖）
EXPLORE_Z_MIN = 1.5           # 探索偏离下限（可被 PA_COINT_EXPLORE_Z 覆盖）
EXPLORE_CONF_CAP = 35.0       # 探索候选置信封顶 → Agent M 路由 paper_probe（而非 approve）
EXPLORE_POSITION_SIZE = 0.02  # 探索 probe 仓位（比研究层 0.05 更小）


def _explore_cfg() -> Optional[dict]:
    """读 env → 探索层配置；未开启返回 None（→ 行为与纯研究层一致，零回归）。"""
    if os.environ.get("PA_COINT_EXPLORE", "").lower() not in ("1", "true", "yes"):
        return None

    def _f(name: str, default: float) -> float:
        try:
            return float(os.environ.get(name, ""))
        except (TypeError, ValueError):
            return default
    return {"corr_min": _f("PA_COINT_EXPLORE_CORR", EXPLORE_CORR_MIN),
            "z_min": _f("PA_COINT_EXPLORE_Z", EXPLORE_Z_MIN)}


# ---------------------------------------------------------------------------
# 数值核（numpy）
# ---------------------------------------------------------------------------

def _ols_slope_intercept(x: np.ndarray, y: np.ndarray) -> tuple:
    """OLS 把 y 回归到 x：返回 (slope, intercept)。x 方差为 0 时返回 (0, mean(y))。"""
    if np.std(x) < EPS:
        return 0.0, float(np.mean(y))
    slope, intercept = np.polyfit(x, y, 1)
    return float(slope), float(intercept)


def _pearson(x: np.ndarray, y: np.ndarray) -> Optional[float]:
    if np.std(x) < EPS or np.std(y) < EPS:
        return None
    return float(np.corrcoef(x, y)[0, 1])


def _ar1_phi(spread: np.ndarray) -> Optional[float]:
    if len(spread) < 3:
        return None
    prev, cur = spread[:-1], spread[1:]
    if np.std(prev) < EPS:
        return None
    phi, _ = _ols_slope_intercept(prev, cur)
    return phi


def _half_life(phi: Optional[float]) -> Optional[float]:
    if phi is None or phi <= 0 or phi >= 1:
        return None
    return float(-math.log(2) / math.log(phi))


def _n_distinct(s: np.ndarray) -> int:
    return int(len(np.unique(np.round(s, 6))))


# ---------------------------------------------------------------------------
# 配对分析
# ---------------------------------------------------------------------------

def analyze_pair(a_id: str, sa: list, b_id: str, sb: list) -> Optional[dict]:
    """对一对市场序列做协整/spread 分析。不构成候选时返回 None（带过滤原因可由调用方忽略）。"""
    n = min(len(sa), len(sb))
    if n < MIN_POINTS:
        return None
    a = np.asarray(sa[-n:], dtype=float)
    b = np.asarray(sb[-n:], dtype=float)
    if np.std(a) < EPS or np.std(b) < EPS:
        return None
    if _n_distinct(a) < MIN_DISTINCT or _n_distinct(b) < MIN_DISTINCT:
        return None

    corr = _pearson(a, b)
    if corr is None:
        return None

    beta, intercept = _ols_slope_intercept(b, a)   # a ≈ beta·b + intercept
    spread = a - beta * b
    s_mean = float(np.mean(spread))
    s_std = float(np.std(spread))
    if s_std < EPS:
        return None
    z = float((spread[-1] - s_mean) / s_std)
    phi = _ar1_phi(spread)
    hl = _half_life(phi)

    return {
        "market_a": a_id, "market_b": b_id,
        "beta": round(beta, 6), "intercept": round(intercept, 6),
        "corr": round(corr, 4),
        "spread_mean": round(s_mean, 6), "spread_std": round(s_std, 6),
        "zscore": round(z, 4),
        "ar1_phi": round(phi, 4) if phi is not None else None,
        "half_life": round(hl, 4) if hl is not None else None,
        "n_points": int(n),
        "n_distinct_a": _n_distinct(a), "n_distinct_b": _n_distinct(b),
        # 当前价位（序列末点），供 sizing 把价格单位边校准为无量纲收益率（Phase 5 校准）
        "price_a": round(float(a[-1]), 6), "price_b": round(float(b[-1]), 6),
    }


def _is_candidate(st: dict, corr_min: float = CORR_MIN, z_min: float = Z_MIN) -> bool:
    """是否构成配对回归候选（corr/|z| 过阈值 + 平稳性）。corr_min/z_min 可放松用于探索层；
    半衰期(平稳性)过滤恒定，不随层放松——价差必须均值回归。"""
    if abs(st["corr"]) < corr_min:
        return False
    if abs(st["zscore"]) < z_min:
        return False
    hl = st["half_life"]
    if hl is None or hl <= 0 or hl > HALF_LIFE_MAX:
        return False
    return True


def _confidence(st: dict) -> float:
    """确定性置信：随 |corr| 与 |z| 升高，封顶 90。"""
    base = 40.0
    base += 25.0 * min(abs(st["corr"]), 1.0)
    base += 8.0 * min(abs(st["zscore"]) - Z_MIN, 4.0)
    return round(min(90.0, max(0.0, base)), 1)


def _dimensionless_edge(expected_edge: float, phi: Optional[float],
                        entry_price: Optional[float]) -> Optional[float]:
    """把价格单位边校准为**无量纲每步预期收益率**（Phase 5 边量纲校准）。

    expected_edge=|z|·spread_std 是价差对均值的**总**偏离（价格单位，假设一次性全回归，过于乐观）。
    AR(1) 下一步期望回归比例 = (1−φ)，故每步预期回归 ≈ (1−φ)·偏离；再除入场价化为分数收益率
    （与 to_pipeline_signals 的 expected_return、model_effectiveness.realized_return 同量纲）。
    使 Kelly μ/σ² 在收益率空间一致，避免价格单位 μ 远大于 σ² 导致恒撞 F_MAX。
    """
    if not entry_price or entry_price <= 0:
        return None
    f = 1.0 if phi is None else max(0.0, min(1.0, 1.0 - float(phi)))  # 每步回归比例
    return round(max(0.0, min(1.0, f * float(expected_edge) / float(entry_price))), 6)


def _build_signal(st: dict, tier: str = "research") -> dict:
    """把过关的配对统计组装成结构化研究信号（PRD §8 可解释 schema）。
    tier='exploration' 时为放松阈值的弱关联候选：置信封顶 + 追加弱关联 failure_condition。"""
    z = st["zscore"]
    # spread = a − beta·b。z>0 → spread 偏高 → a 相对 b 偏贵：预期 a 跌 / b 涨（相对回归）。
    if z > 0:
        rich_leg, cheap_leg = st["market_a"], st["market_b"]
        entry_price = st.get("price_a")          # 代表腿=首个可成交腿=rich_leg
    else:
        rich_leg, cheap_leg = st["market_b"], st["market_a"]
        entry_price = st.get("price_b")
    expected_edge = round(abs(z) * st["spread_std"], 6)  # 预期价差压缩（价格单位）
    expected_return = _dimensionless_edge(expected_edge, st.get("ar1_phi"), entry_price)
    sufficiency = "medium" if st["n_points"] >= DATA_SUFFICIENCY_MEDIUM else "low"
    conf = _confidence(st)
    if tier == "exploration":
        conf = round(min(conf, EXPLORE_CONF_CAP), 1)

    signal = {
        "signal_uid": _ds.uid(MODEL_NAME, st["market_a"], st["market_b"]),
        "models_used": [MODEL_NAME],
        "method": METHOD,
        "tier": tier,                  # research（严格）/ exploration（弱关联低置信 probe）
        "pair_type": "pm_pm",          # Polymarket × Polymarket（两腿均可成交）
        "source_markets": [st["market_a"], st["market_b"]],
        "direction": "spread_revert",
        "legs": [
            {"market_id": rich_leg, "expectation": "down", "role": "rich", "tradeable": True},
            {"market_id": cheap_leg, "expectation": "up", "role": "cheap", "tradeable": True},
        ],
        "evidence": {
            "beta": st["beta"], "corr": st["corr"],
            "spread_mean": st["spread_mean"], "spread_std": st["spread_std"],
            "zscore": st["zscore"], "ar1_phi": st["ar1_phi"], "half_life": st["half_life"],
            "n_points": st["n_points"],
            "n_distinct_a": st["n_distinct_a"], "n_distinct_b": st["n_distinct_b"],
        },
        "confidence": conf,
        "expected_edge": expected_edge,             # 价格单位（价差压缩，evidence/traceability）
        "entry_price": entry_price,                 # 代表腿当前价位
        "expected_return": expected_return,         # 无量纲每步预期收益率（sizing 用，Phase 5 校准）
        "failure_conditions": [
            "若价差不回归（结构性变化导致相关性破裂，corr 显著下降）",
            "若 ar1_phi>=1 或半衰期发散（spread 非平稳、趋势性走宽）",
            "若任一腿流动性骤降，无法按对冲比 beta 建/平价差仓位",
            f"若样本不足（当前 n={st['n_points']}，data_sufficiency={sufficiency}）使统计估计不稳健",
        ],
        "data_sufficiency": sufficiency,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    if tier == "exploration":
        signal["failure_conditions"].insert(
            0, f"探索层弱关联候选：corr={st['corr']}/|z|={abs(st['zscore']):.2f} 低于研究阈值"
               f"（{CORR_MIN}/{Z_MIN}），低置信小额 probe，待复盘验证真伪")
    return signal


# ---------------------------------------------------------------------------
# 跨资产协整（Phase 3f-x，PRD §9：一个市场变化 → 去别的市场找信号）
# ---------------------------------------------------------------------------

def _build_cross_asset_signal(st: dict, pm_id: str, asset_symbol: str,
                              asset_kind: Optional[str], tier: str = "research") -> dict:
    """构建 Polymarket × 外部资产 协整候选。
    资产是**外生锚**（本系统不可成交），故只有 Polymarket 腿可成交：
      spread = pm − beta·asset；z>0 → pm 相对资产偏贵 → 预期 pm 跌（NO）；z<0 → YES。
    tier='exploration' 为放松阈值的弱关联候选（置信封顶 + 追加 failure_condition）。
    """
    z = st["zscore"]
    expectation = "down" if z > 0 else "up"
    sufficiency = "medium" if st["n_points"] >= DATA_SUFFICIENCY_MEDIUM else "low"
    expected_edge = round(abs(z) * st["spread_std"], 6)
    entry_price = st.get("price_a")                 # 可成交腿=pm（market_a），资产腿外生不可成交
    expected_return = _dimensionless_edge(expected_edge, st.get("ar1_phi"), entry_price)
    conf = _confidence(st)
    if tier == "exploration":
        conf = round(min(conf, EXPLORE_CONF_CAP), 1)
    sig = {
        "signal_uid": _ds.uid(MODEL_NAME, pm_id, asset_symbol),
        "models_used": [MODEL_NAME],
        "method": METHOD,
        "tier": tier,                  # research（严格）/ exploration（弱关联低置信 probe）
        "pair_type": "pm_asset",
        "anchor_asset": asset_symbol, "anchor_kind": asset_kind,
        "source_markets": [pm_id, asset_symbol],
        "direction": "spread_revert",
        "legs": [
            {"market_id": pm_id, "expectation": expectation, "role": "pm", "tradeable": True},
            {"market_id": asset_symbol, "role": "anchor", "tradeable": False},
        ],
        "evidence": {
            "beta": st["beta"], "corr": st["corr"],
            "spread_mean": st["spread_mean"], "spread_std": st["spread_std"],
            "zscore": st["zscore"], "ar1_phi": st["ar1_phi"], "half_life": st["half_life"],
            "n_points": st["n_points"],
            "n_distinct_a": st["n_distinct_a"], "n_distinct_b": st["n_distinct_b"],
        },
        "confidence": conf,
        "expected_edge": expected_edge,             # 价格单位（traceability）
        "entry_price": entry_price,                 # pm 腿当前价位
        "expected_return": expected_return,         # 无量纲每步预期收益率（sizing 用，Phase 5 校准）
        "failure_conditions": [
            f"若 Polymarket 概率与 {asset_symbol} 的协整关系破裂（corr 显著下降）",
            "若 ar1_phi>=1 或半衰期发散（spread 非平稳、趋势性走宽）",
            f"若 {asset_symbol} 出现结构性跳变（外生冲击），原对冲比 beta 失效",
            f"若样本不足（当前 n={st['n_points']}，data_sufficiency={sufficiency}）使统计估计不稳健",
        ],
        "data_sufficiency": sufficiency,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    if tier == "exploration":
        sig["failure_conditions"].insert(
            0, f"探索层弱关联候选：corr={st['corr']}/|z|={abs(st['zscore']):.2f} 低于研究阈值"
               f"（{CORR_MIN}/{Z_MIN}），低置信小额 probe，待复盘验证真伪")
    return sig


def _classify_tier(st: dict, explore: Optional[dict]) -> Optional[str]:
    """配对归层：过严格阈值→'research'；否则过放松阈值且探索开启→'exploration'；都不过→None。"""
    if _is_candidate(st, CORR_MIN, Z_MIN):
        return "research"
    if explore and _is_candidate(st, explore["corr_min"], explore["z_min"]):
        return "exploration"
    return None


def _tier_sort_key(s: dict):
    """research 优先于 exploration；同层按 |z| 降序。"""
    return (0 if s.get("tier") == "research" else 1, -abs(s["evidence"]["zscore"]))


def find_cross_asset_candidates(base_dir=None, field: str = "yes_price",
                                top_k: Optional[int] = None) -> dict:
    """Polymarket 市场(yes_price) × 外部资产序列 的协整研究。复用 analyze_pair。"""
    if top_k is None:
        top_k = _top_k()
    pm_hist = _ph.load_history(base_dir)
    asset_hist = _ph.load_asset_history(base_dir)

    pm_series = {}
    for mid in pm_hist.keys():
        s = _ph.series_for(pm_hist, mid, field)
        arr = np.asarray(s, dtype=float) if s else np.array([])
        if len(s) >= MIN_POINTS and arr.size and np.std(arr) > EPS and _n_distinct(arr) >= MIN_DISTINCT:
            pm_series[mid] = s

    asset_series, asset_kind = {}, {}
    for sym, pts in asset_hist.items():
        s = _ph.asset_series_for(asset_hist, sym)
        arr = np.asarray(s, dtype=float) if s else np.array([])
        if len(s) >= MIN_POINTS and arr.size and np.std(arr) > EPS and _n_distinct(arr) >= MIN_DISTINCT:
            asset_series[sym] = s
            asset_kind[sym] = (pts[-1].get("kind") if pts else None)

    explore = _explore_cfg()
    pairs_evaluated = 0
    candidates = []
    for pm_id, ps in pm_series.items():
        for sym, asy in asset_series.items():
            st = analyze_pair(pm_id, ps, sym, asy)   # market_a=pm, market_b=asset
            if st is None:
                continue
            pairs_evaluated += 1
            tier = _classify_tier(st, explore)
            if tier:
                candidates.append(
                    _build_cross_asset_signal(st, pm_id, sym, asset_kind.get(sym), tier=tier))

    candidates.sort(key=_tier_sort_key)
    candidates = candidates[:top_k]
    return {
        "n_pm_markets": len(pm_series),
        "n_assets": len(asset_series),
        "n_pairs_evaluated": pairs_evaluated,
        "n_candidates": len(candidates),
        "n_candidates_research": sum(c["tier"] == "research" for c in candidates),
        "n_candidates_exploration": sum(c["tier"] == "exploration" for c in candidates),
        "candidates": candidates,
    }


# ---------------------------------------------------------------------------
# 顶层入口
# ---------------------------------------------------------------------------

def find_candidates(base_dir=None, field: str = "yes_price",
                    top_k: Optional[int] = None) -> dict:
    """加载价格历史 → pairwise 协整/spread 分析 → 过滤排序，返回候选与统计元信息。"""
    if top_k is None:
        top_k = _top_k()
    history = _ph.load_history(base_dir)
    series = {}
    for mid in history.keys():
        s = _ph.series_for(history, mid, field)
        if len(s) >= MIN_POINTS and np.std(np.asarray(s, dtype=float)) > EPS \
                and _n_distinct(np.asarray(s, dtype=float)) >= MIN_DISTINCT:
            series[mid] = s

    explore = _explore_cfg()
    pairs_evaluated = 0
    candidates = []
    ids = list(series.keys())
    for a_id, b_id in combinations(ids, 2):
        st = analyze_pair(a_id, series[a_id], b_id, series[b_id])
        if st is None:
            continue
        pairs_evaluated += 1
        tier = _classify_tier(st, explore)
        if tier:
            candidates.append(_build_signal(st, tier=tier))

    candidates.sort(key=_tier_sort_key)
    candidates = candidates[:top_k]

    # Phase 3f-x：合入跨资产候选（Polymarket × 外部资产）
    cross = find_cross_asset_candidates(base_dir, field=field, top_k=top_k)

    all_cands = candidates + cross["candidates"]
    return {
        "n_markets_total": len(history),
        "n_markets_considered": len(series),
        "n_pairs_evaluated": pairs_evaluated + cross["n_pairs_evaluated"],
        "n_candidates": len(all_cands),
        "n_candidates_pm_pm": len(candidates),
        "n_candidates_pm_asset": cross["n_candidates"],
        "n_candidates_research": sum(c["tier"] == "research" for c in all_cands),
        "n_candidates_exploration": sum(c["tier"] == "exploration" for c in all_cands),
        "explore_enabled": explore is not None,
        "n_assets": cross["n_assets"],
        "candidates": all_cands,
    }


def recent_cointegration_keys(base_dir=None, hours: float = 12.0) -> set:
    """跨周期冷却来源（加固）：读影子 signals 表里近 `hours` 内 source=cointegration 的
    (market_id, direction)，供 to_pipeline_signals 跳过——避免同一配对每周期重复发 probe。

    best-effort：PA_SHADOW_DB 未开/库不可用/出错 → 返回空集（不冷却，退化为旧行为）。
    """
    if hours <= 0:
        return set()
    if os.environ.get("PA_SHADOW_DB", "").lower() not in ("1", "true", "yes"):
        return set()
    try:
        from datetime import timedelta
        from runtime import _shadow
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).strftime("%Y-%m-%dT%H:%M:%SZ")
        rows = _shadow._rows(  # noqa: SLF001
            "SELECT market_id, direction FROM signals "
            "WHERE source='cointegration' AND COALESCE(generated_at,'') >= ?", (cutoff,))
        return {(str(r["market_id"]), str(r["direction"]).upper()) for r in rows}
    except Exception as exc:  # noqa: BLE001
        print(f"[cointegration] recent_keys 读取失败（不冷却）: {exc}", flush=True)
        return set()


def to_pipeline_signals(report: dict, market_meta: Optional[dict] = None,
                        position_size: float = 0.05, recent_keys: Optional[set] = None,
                        skip_degraded: bool = False) -> list:
    """把协整研究候选转成 signals.json 兼容的**方向性 leg 信号**，带真实 `models_used`。

    ⚠ 仅在 env 门控 `PA_COINT_SIGNALS=1` 下由 orchestrator 调用合入信号链路；
    默认**不调用**。每条 leg 信号带 Agent M 审查所需的 data_sources + logic_chain（健全性），
    并以小仓位（probe 量）进入，全程仍受 dry_run 与 Agent M 分级护栏约束。

    market_meta: {market_id: {"name":.., "slug":.., "yes_price":.., "no_price":..}}（可空，缺则降级）。
    一对候选 → 最多 2 条 leg 信号：cheap leg（预期涨→YES）、rich leg（预期跌→NO）。
    加固参数：
      * recent_keys: 近周期已发过的 (market_id, direction)（大写）集合 → 跳过（跨周期冷却）。
      * skip_degraded: True → 无 meta 价格的腿**直接跳过**（不再伪造 0.5 成可成交信号）。
    """
    meta = market_meta or {}
    recent = recent_keys or set()
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    out = []
    for cand in report.get("candidates", []) or []:
        ev = cand.get("evidence", {})
        spread_std = ev.get("spread_std") or 0.0
        zscore = ev.get("zscore") or 0.0
        pair_type = cand.get("pair_type", "pm_pm")
        tier = cand.get("tier", "research")
        # 探索层弱关联候选用更小 probe 仓位（PRD §6 低风险试错）；研究层用传入仓位。
        leg_size = EXPLORE_POSITION_SIZE if tier == "exploration" else position_size
        # 只对可成交腿发信号（跨资产候选的资产腿 tradeable=False，是外生锚，跳过）。
        tradeable = [l for l in cand.get("legs", []) if l.get("tradeable", True)]
        tradeable_ids = [str(l.get("market_id")) for l in tradeable]
        # 配对完整性仅适用 pm_pm（两腿都可成交）；pm_asset 单腿 → 无 pair_id（整完整性 N/A）。
        is_pair = (pair_type == "pm_pm" and len(tradeable) == 2)
        pair_id = cand.get("signal_uid") if is_pair else None
        for i, leg in enumerate(tradeable):
            mid = str(leg.get("market_id"))
            expectation = leg.get("expectation")
            direction = "YES" if expectation == "up" else "NO"
            # 跨周期冷却：近周期已发过同 (market, direction) → 跳过。
            if (mid, direction) in recent:
                continue
            m = meta.get(mid) or meta.get(str(mid)) or {}
            yes_p = m.get("yes_price")
            no_p = m.get("no_price")
            price = (yes_p if direction == "YES" else no_p)
            degraded = price is None
            # 加固：skip_degraded → 无价腿直接跳过，绝不伪造 0.5 成可成交信号。
            if degraded and skip_degraded:
                continue
            if price is None:
                price = 0.5
            # Fix2：expected_value 改为**无量纲预期收益率**——价差预期回归 |z|·spread_std
            # 归到本腿入场价的占比（与 realized_return 同量纲，使 edge_realization 有意义）。
            expected_return = round(min(1.0, abs(zscore) * float(spread_std) / float(price)), 6) \
                if price else None
            partner = tradeable_ids[1 - i] if is_pair else None
            out.append({
                "market_id": mid,
                "market_name": m.get("name") or mid,
                "market": m.get("name") or mid,
                "market_slug": m.get("slug") or "",
                "direction": direction,
                "price": round(float(price), 6),
                "position_size": leg_size,              # 小仓位 probe 量（探索层更小）
                "expected_value": expected_return,       # 无量纲预期收益率
                "confidence": cand.get("confidence"),
                "tier": tier,                            # research / exploration（弱关联 probe）
                "probe": True,
                "research_candidate": tier == "research",
                "source": "cointegration",
                "source_agent": "cointegration",
                "generated_at": now,
                "timestamp": now,
                # 真实模型归因（Phase 3f-loop 闭环关键字段）
                "models_used": [MODEL_NAME],
                "source_markets": cand.get("source_markets"),
                "method": METHOD,
                "pair_type": pair_type,
                "anchor_asset": cand.get("anchor_asset"),   # pm_asset：外生锚资产
                # Fix1：配对原子完整性元信息（pm_pm 两腿必须同进同出；pm_asset 单腿 pair_id=None）
                "pair_id": pair_id,
                "pair_role": leg.get("role"),
                "pair_partner_market": partner,
                "evidence": {**ev, "expected_spread_move": round(abs(zscore) * float(spread_std), 6)},
                # Agent M 健全性所需
                "data_sources": ["data/market_price_history.json", "runtime.cointegration"],
                "logic_chain": [
                    f"model={MODEL_NAME} method={METHOD}",
                    f"pair={cand.get('source_markets')} beta={ev.get('beta')} corr={ev.get('corr')}",
                    f"spread z={ev.get('zscore')} half_life={ev.get('half_life')} ar1_phi={ev.get('ar1_phi')}",
                    f"leg={mid} role={leg.get('role')} expectation={expectation} → direction={direction}",
                    f"tier={tier} probe_size={leg_size}" + (
                        "（探索层弱关联：低置信小额，待复盘验证）" if tier == "exploration" else ""),
                    "spread_revert: 预期价差向均值回归" + ("（价格降级=0.5，无 meta）" if degraded else ""),
                ],
                "risk_notes": (f"correlation_risk: corr={ev.get('corr')}; "
                               f"stationarity: ar1_phi={ev.get('ar1_phi')}, half_life={ev.get('half_life')}; "
                               f"data_sufficiency={cand.get('data_sufficiency')}"),
                "reason": f"协整配对回归：{cand.get('source_markets')} spread z={ev.get('zscore')}",
                "failure_conditions": cand.get("failure_conditions"),
            })
    return out


def enforce_pair_integrity(signals: list) -> tuple:
    """配对原子完整性（Fix1）：协整是价差套利，两腿必须同时在场，否则只剩裸方向单。

    在 Agent M 审查**之后、执行之前**对 approved_signals 调用：
      * 非协整信号（无 pair_id）原样保留。
      * 协整腿按 pair_id 分组；仅当本腿 + 其 pair_partner_market 对应腿都在场，才保留整对；
        任一腿缺失（被 Agent M 拒/降级丢弃）→ 整对丢弃（绝不留裸腿）。
    返回 (kept, dropped)。纯函数，不写盘。
    """
    coint = [s for s in signals if s.get("pair_id")]
    others = [s for s in signals if not s.get("pair_id")]

    # 按 pair_id 聚合在场的腿（用 market_id 标识腿）
    present: dict = {}
    for s in coint:
        present.setdefault(s["pair_id"], {})[str(s.get("market_id"))] = s

    kept_coint, dropped = [], []
    for s in coint:
        legs = present.get(s["pair_id"], {})
        partner = str(s.get("pair_partner_market"))
        if partner and partner in legs:
            kept_coint.append(s)        # 两腿都在 → 保留
        else:
            dropped.append(s)           # 孤腿 → 丢弃
    return others + kept_coint, dropped


def market_meta_from_latest(latest_data: dict) -> dict:
    """从 latest_data.json 构建 {market_id: {name, slug, yes_price, no_price}}，供 bridge 富化价格。"""
    meta = {}
    for m in (latest_data.get("polymarket_markets") or latest_data.get("markets") or []):
        if not isinstance(m, dict):
            continue
        mid = str(m.get("id") or "")
        if not mid:
            continue
        yes_p = no_p = None
        prices = m.get("outcome_prices") or []
        outs = [str(o).lower() for o in (m.get("outcomes") or ["yes", "no"])]
        try:
            yes_p = float(prices[outs.index("yes")])
            no_p = float(prices[outs.index("no")])
        except (ValueError, IndexError, TypeError):
            yes_p = m.get("yes_price")
            no_p = m.get("no_price")
        meta[mid] = {"name": m.get("question") or m.get("slug"), "slug": m.get("slug"),
                     "yes_price": yes_p, "no_price": no_p}
    return meta


def compute(base_dir=None, field: str = "yes_price") -> dict:
    """跑协整研究 → 落盘研究产物 `data/correlation_signals.json` + 影子表。

    返回报告 dict。best-effort：研究产物，失败不应中断主流程。
    """
    res = find_candidates(base_dir, field=field)
    report = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "model": MODEL_NAME, "method": METHOD, "field": field,
        "enforced": False,   # 研究产物，未接入 live 交易链路
        "params": {"min_points": MIN_POINTS, "corr_min": CORR_MIN, "z_min": Z_MIN,
                   "half_life_max": HALF_LIFE_MAX, "top_k": TOP_K},
        **res,
    }
    _ds.write_correlation_signals(report, base_dir=base_dir)
    return report


def main():
    rep = compute()
    print(json.dumps({
        "model": rep["model"], "method": rep["method"], "enforced": rep["enforced"],
        "n_markets_considered": rep["n_markets_considered"],
        "n_pairs_evaluated": rep["n_pairs_evaluated"],
        "n_candidates": rep["n_candidates"],
        "top": [(c["source_markets"], c["evidence"]["zscore"], c["evidence"]["corr"],
                 c["confidence"], c["data_sufficiency"]) for c in rep["candidates"][:5]],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
