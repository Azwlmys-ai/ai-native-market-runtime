"""
garch — GARCH(1,1) 波动率聚集研究引擎（Phase 3h：第三个「真实模型」）
============================================================================
定位（对齐 PRD 第十一节第三优先级「GARCH」+ §10「模型是研究工具」）
----------------------------------------------------------------------------
继协整（3f）、HMM regime（3g）之后的**第三个真实统计模型**。对价格变动序列拟合
**GARCH(1,1)** 条件方差模型，刻画**波动率聚集**与**风险状态变化**，产出带
**真实 `models_used=["garch"]`** 的结构化研究产物。用途：

  * 波动率聚集（高波动跟随高波动）—— persistence = alpha+beta
  * 风险状态变化（当前/预测波动 vs 长期波动）—— risk_state: elevated/normal/calm
  * 喂 HMM regime（互补：regime 给离散状态、GARCH 给连续波动幅度预测）
  * 喂 Kelly/Markowitz sizing（用预测方差做仓位风险标定，Phase 3i）

> 关键纪律：研究工具，产物写 `data/volatility_states.json` + 影子表 `volatility_states`，
> `enforced=False`，**不接入 live executor / agent_b**。喂 sizing/风控 = 后续 env 门控独立步骤。

方法（方差目标化 GARCH(1,1) + 网格 MLE，仅依赖 numpy，避开 arch/scipy）
----------------------------------------------------------------------
对一条价格序列 p：观测 = 去均值一阶差分收益 r[t] = (p[t]−p[t−1]) − mean。
条件方差递归：sigma2[t] = omega + alpha·r[t−1]² + beta·sigma2[t−1]。
**方差目标化**：令长期方差 = 样本方差 V → omega = V·(1−alpha−beta)，把 3 参降为
(alpha, beta) 二维。在 alpha+beta<1（平稳）网格上最大化高斯对数似然 → 确定性 argmax
（无随机、无迭代优化器，短序列稳健）。

防伪护栏（点少必须）
--------------------
序列真在动（std>eps）+ 不同取值数 >= MIN_DISTINCT + 观测数 >= MIN_OBS；
alpha+beta≈0 视为无 ARCH 效应（无聚集）。每条打 data_sufficiency。

纯确定性、numpy-only、沙箱可单测；加法产物，不改任何交易行为。
"""

from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import numpy as np

from runtime import datastore as _ds
from runtime import price_history as _ph

SCHEMA_VERSION = "0.3.10-phase3h-garch"
MODEL_NAME = "garch"
METHOD = "garch11_variance_targeted_grid_mle"

MIN_OBS = 10            # 最少收益观测数 → 序列长度需 >= MIN_OBS+1
MIN_DISTINCT = 4
EPS = 1e-12
# (alpha, beta) 网格（平稳约束 alpha+beta <= MAX_PERSIST）
ALPHA_GRID = np.round(np.arange(0.0, 0.61, 0.05), 4)
BETA_GRID = np.round(np.arange(0.0, 0.96, 0.05), 4)
MAX_PERSIST = 0.985
CLUSTER_PERSIST = 0.50  # persistence >= 此值且 alpha>0 → 判定存在波动聚集
ELEVATED_RATIO = 1.25   # 预测波动 / 长期波动 >= 此值 → risk_state=elevated
CALM_RATIO = 0.80       # <= 此值 → calm
SPIKE_SIGMA = 2.0       # 末点 |r| >= 长期波动·此倍数 → vol_spike
DATA_SUFFICIENCY_MEDIUM = 25


def _n_distinct(s: np.ndarray) -> int:
    return int(len(np.unique(np.round(s, 6))))


def _garch_loglik(r: np.ndarray, omega: float, alpha: float, beta: float,
                  v0: float) -> tuple:
    """给定参数跑条件方差递归，返回 (loglik, sigma2 序列)。数值不稳时 loglik=-inf。"""
    T = len(r)
    sigma2 = np.empty(T)
    sigma2[0] = max(v0, EPS)
    for t in range(1, T):
        sigma2[t] = omega + alpha * r[t - 1] ** 2 + beta * sigma2[t - 1]
        if sigma2[t] <= 0 or not np.isfinite(sigma2[t]):
            return -np.inf, sigma2
    ll = -0.5 * np.sum(np.log(2.0 * math.pi * sigma2) + r ** 2 / sigma2)
    return float(ll), sigma2


def fit_garch(r: np.ndarray) -> dict:
    """方差目标化 GARCH(1,1) 网格 MLE。确定性 argmax。"""
    V = float(np.var(r))
    best = {"alpha": 0.0, "beta": 0.0, "omega": V, "loglik": -np.inf, "sigma2": None}
    for a in ALPHA_GRID:
        for b in BETA_GRID:
            if a + b > MAX_PERSIST:
                continue
            omega = V * (1.0 - a - b)
            if omega <= 0:
                continue
            ll, sigma2 = _garch_loglik(r, omega, float(a), float(b), V)
            if ll > best["loglik"]:
                best = {"alpha": float(a), "beta": float(b), "omega": float(omega),
                        "loglik": ll, "sigma2": sigma2}
    best["long_run_var"] = V
    return best


def analyze_series(series_id: str, series: list) -> Optional[dict]:
    """对一条价格序列拟合 GARCH(1,1) 并刻画当前/预测波动与风险状态。"""
    n = len(series)
    if n < MIN_OBS + 1:
        return None
    p = np.asarray(series[-(min(n, 80)):], dtype=float)
    if np.std(p) < math.sqrt(EPS) or _n_distinct(p) < MIN_DISTINCT:
        return None
    r = np.diff(p)
    r = r - float(np.mean(r))
    if len(r) < MIN_OBS or np.var(r) < EPS:
        return None

    fit = fit_garch(r)
    alpha, beta, omega = fit["alpha"], fit["beta"], fit["omega"]
    sigma2 = fit["sigma2"]
    persistence = alpha + beta
    long_run_vol = math.sqrt(max(fit["long_run_var"], EPS))
    current_vol = math.sqrt(max(float(sigma2[-1]), EPS))
    forecast_var = omega + alpha * float(r[-1]) ** 2 + beta * float(sigma2[-1])
    forecast_vol = math.sqrt(max(forecast_var, EPS))

    ratio = forecast_vol / long_run_vol if long_run_vol > 0 else 1.0
    if ratio >= ELEVATED_RATIO:
        risk_state = "elevated"
    elif ratio <= CALM_RATIO:
        risk_state = "calm"
    else:
        risk_state = "normal"

    if forecast_vol > current_vol * 1.05:
        vol_trend = "rising"
    elif forecast_vol < current_vol * 0.95:
        vol_trend = "falling"
    else:
        vol_trend = "stable"

    clustering = bool(persistence >= CLUSTER_PERSIST and alpha > 1e-6)
    vol_spike = bool(abs(float(r[-1])) >= SPIKE_SIGMA * long_run_vol)

    return {
        "series_id": series_id,
        "n_obs": int(len(r)),
        "alpha": round(alpha, 4), "beta": round(beta, 4), "omega": round(omega, 8),
        "persistence": round(persistence, 4),
        "long_run_vol": round(long_run_vol, 6),
        "current_vol": round(current_vol, 6),
        "forecast_vol": round(forecast_vol, 6),
        "vol_ratio": round(ratio, 4),
        "risk_state": risk_state,
        "vol_trend": vol_trend,
        "clustering": clustering,
        "vol_spike": vol_spike,
        "loglik": round(float(fit["loglik"]), 4),
    }


def _confidence(st: dict) -> float:
    """确定性置信：随 persistence（聚集越强越可信）与数据量升高，封顶 90。"""
    base = 35.0
    base += 40.0 * min(st["persistence"], 1.0)
    base += 15.0 * min(st["n_obs"] / DATA_SUFFICIENCY_MEDIUM, 1.0)
    return round(min(90.0, max(0.0, base)), 1)


def _build_signal(st: dict, kind: Optional[str] = None) -> dict:
    sufficiency = "medium" if st["n_obs"] >= DATA_SUFFICIENCY_MEDIUM else "low"
    return {
        "signal_uid": _ds.uid(MODEL_NAME, st["series_id"]),
        "models_used": [MODEL_NAME],
        "method": METHOD,
        "series_id": st["series_id"],
        "series_kind": kind,
        "risk_state": st["risk_state"],
        "vol_trend": st["vol_trend"],
        "clustering": st["clustering"],
        "vol_spike": st["vol_spike"],
        "evidence": {
            "alpha": st["alpha"], "beta": st["beta"], "omega": st["omega"],
            "persistence": st["persistence"],
            "long_run_vol": st["long_run_vol"], "current_vol": st["current_vol"],
            "forecast_vol": st["forecast_vol"], "vol_ratio": st["vol_ratio"],
            "n_obs": st["n_obs"], "loglik": st["loglik"],
        },
        "confidence": _confidence(st),
        # 波动率模型非方向性下注；预测方差供 sizing 标定（Phase 3i），expected_edge 占位 0。
        "expected_edge": 0.0,
        "failure_conditions": [
            "若波动结构突变（如结算临近、新闻冲击）使历史 GARCH 估计失效",
            "若样本不足导致 alpha/beta 估计不稳健（持续性被高估/低估）",
            f"若波动非平稳（persistence={st['persistence']} 接近 1，长期方差不收敛）",
            f"若样本不足（当前 n_obs={st['n_obs']}，data_sufficiency={sufficiency}）",
        ],
        "data_sufficiency": sufficiency,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


def _collect_series(base_dir, field: str) -> list:
    out = []
    pm_hist = _ph.load_history(base_dir)
    for mid in pm_hist.keys():
        s = _ph.series_for(pm_hist, mid, field)
        if len(s) >= MIN_OBS + 1:
            out.append((str(mid), s, "pm_market"))
    asset_hist = _ph.load_asset_history(base_dir)
    for sym, pts in asset_hist.items():
        s = _ph.asset_series_for(asset_hist, sym)
        if len(s) >= MIN_OBS + 1:
            kind = (pts[-1].get("kind") if pts else None) or "asset"
            out.append((str(sym), s, kind))
    return out


def find_volatility_states(base_dir=None, field: str = "yes_price") -> dict:
    series_list = _collect_series(base_dir, field)
    states, n_considered = [], 0
    for sid, s, kind in series_list:
        st = analyze_series(sid, s)
        if st is None:
            continue
        n_considered += 1
        states.append(_build_signal(st, kind=kind))
    # 排序：vol_spike → elevated → clustering → 置信度
    def _rank(x):
        return (x["vol_spike"], x["risk_state"] == "elevated", x["clustering"], x["confidence"])
    states.sort(key=_rank, reverse=True)
    return {
        "n_series_total": len(series_list),
        "n_series_considered": n_considered,
        "n_states": len(states),
        "n_elevated": sum(1 for s in states if s["risk_state"] == "elevated"),
        "n_clustering": sum(1 for s in states if s["clustering"]),
        "n_vol_spike": sum(1 for s in states if s["vol_spike"]),
        "states": states,
    }


def compute(base_dir=None, field: str = "yes_price") -> dict:
    """跑 GARCH 波动率识别 → 落盘研究产物 `data/volatility_states.json` + 影子表。"""
    res = find_volatility_states(base_dir, field=field)
    report = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "model": MODEL_NAME, "method": METHOD, "field": field,
        "enforced": False,
        "params": {"min_obs": MIN_OBS, "max_persist": MAX_PERSIST,
                   "cluster_persist": CLUSTER_PERSIST, "elevated_ratio": ELEVATED_RATIO},
        **res,
    }
    _ds.write_volatility_states(report, base_dir=base_dir)
    return report


def main():
    rep = compute()
    print(json.dumps({
        "model": rep["model"], "enforced": rep["enforced"],
        "n_series_considered": rep["n_series_considered"], "n_states": rep["n_states"],
        "n_elevated": rep["n_elevated"], "n_clustering": rep["n_clustering"],
        "top": [(s["series_id"], s["risk_state"], s["vol_trend"], s["clustering"],
                 s["evidence"]["persistence"], s["confidence"]) for s in rep["states"][:5]],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
