"""
position_sizing — Kelly + Markowitz 仓位 sizing 建议（Phase 3i：PRD §11 优先级 4/5）
============================================================================
定位（对齐 PRD §11 优先级 4「Markowitz：多信号组合」+ 5「Kelly：仓位 sizing/风险控制」
       + §10「模型是研究工具」）
----------------------------------------------------------------------------
把前面三个真实模型的产物拼成**仓位建议**：
  * 边（expected return）来自 cointegration 研究候选（Phase 3f）；
  * 方差来自 GARCH 预测波动（Phase 3h，forecast_vol²）；
  * regime 来自 HMM（Phase 3g）做风险缩放（turbulent → 收缩）。
输出：
  * **Kelly 分数**（每信号绝对仓位占比）：分数 Kelly κ·μ/σ²，封顶 F_MAX、负边归零、long-only；
  * **Markowitz 权重**（多信号相对配置）：w ∝ Σ⁻¹μ，long-only 截断后归一。

> 关键纪律：**建议产物**，写 `data/sizing_suggestions.json` + 影子表 `sizing_suggestions`，
> `enforced=False`，**不接入 agent_m / executor / paper_probe 仓位**。当前 paper_probe 仍用固定
> ×0.25；把本建议接成真正 sizing = 后续 env 门控独立步骤（Phase 5，需评审）。

边量纲校准（Phase 5）：μ 与 σ² 统一在**无量纲收益率空间**——μ 用 cointegration 候选预算的
`expected_return`（=(1−φ)·|z|·spread_std/入场价，每步预期回归收益率，与 realized_return 同量纲），
价格单位 GARCH 方差 forecast_vol² 经入场价归一为 (vol/price)²。这样 Kelly μ/σ² 量纲一致，不再因
价格单位 μ 远大于 σ² 而恒撞 F_MAX。旧候选无 `expected_return` 时退化为 expected_edge/入场价（向后兼容）。

纯确定性、numpy-only、沙箱可单测；加法产物，不改任何交易行为。
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import numpy as np

from runtime import datastore as _ds

SCHEMA_VERSION = "0.3.13-phase5-edge-calib"  # 收益率空间 Kelly（μ=expected_return, σ²=收益率方差）

KELLY_KAPPA = 0.25      # 分数 Kelly（保守，避免全 Kelly 过度下注）
F_MAX = 0.25            # 单信号绝对仓位上限（占 bankroll）
VAR_FLOOR = 1e-6        # 方差地板，防除零放大
DEFAULT_VOL = 0.05      # 无 GARCH 方差时的兜底每步波动
REGIME_SCALER = {"turbulent": 0.5, "normal": 0.75, "calm": 1.0}  # 风险缩放（未知 →1.0）


# ---------------------------------------------------------------------------
# 核心 sizing（纯函数）
# ---------------------------------------------------------------------------

def kelly_fraction(mu: float, var: float, regime: Optional[str] = None) -> dict:
    """分数 Kelly：f = clamp(κ·μ/σ², 0, F_MAX) × regime 缩放。负边 → 0（不下注）。"""
    var = max(float(var), VAR_FLOOR)
    raw = float(mu) / var
    f = KELLY_KAPPA * raw
    f = max(0.0, min(F_MAX, f))
    scaler = REGIME_SCALER.get(regime, 1.0)
    return {"kelly_raw": round(raw, 6), "kelly_fraction": round(f, 6),
            "regime_scaler": scaler, "sized_fraction": round(f * scaler, 6)}


def markowitz_weights(mus: list, variances: list,
                      corr: Optional[list] = None) -> list:
    """均值-方差最优权重 w ∝ Σ⁻¹μ，long-only 截断后归一（和为 1；全非正边 → 全 0）。

    Σ 由 variances 对角 + 可选相关矩阵 corr 构成；corr 缺省视为独立（对角 Σ）。
    用 pinv 兜底奇异矩阵。权重对 μ 同比缩放不变（量纲鲁棒）。
    """
    n = len(mus)
    if n == 0:
        return []
    mu = np.asarray(mus, dtype=float)
    var = np.maximum(np.asarray(variances, dtype=float), VAR_FLOOR)
    std = np.sqrt(var)
    if corr is not None:
        C = np.asarray(corr, dtype=float)
        Sigma = C * np.outer(std, std)
    else:
        Sigma = np.diag(var)
    try:
        raw = np.linalg.pinv(Sigma) @ mu
    except Exception:
        raw = mu / var
    raw = np.clip(raw, 0.0, None)
    tot = float(raw.sum())
    if tot <= 0:
        return [0.0] * n
    return list(np.round(raw / tot, 6))


# ---------------------------------------------------------------------------
# 装载模型产物
# ---------------------------------------------------------------------------

def _load_json(base_dir: Optional[Path], name: str) -> dict:
    base = Path(base_dir) if base_dir else _ds.get_base_dir()
    p = base / "data" / name
    if not p.exists():
        return {}
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def _variance_map(vol_report: dict) -> dict:
    """{series_id: forecast_var} from GARCH volatility_states。"""
    out = {}
    for s in vol_report.get("states", []) or []:
        sid = str(s.get("series_id") or "")
        fv = (s.get("evidence", {}) or {}).get("forecast_vol")
        if sid and fv is not None:
            try:
                out[sid] = float(fv) ** 2
            except (TypeError, ValueError):
                continue
    return out


def _regime_map(regime_report: dict) -> dict:
    out = {}
    for r in regime_report.get("regimes", []) or []:
        sid = str(r.get("series_id") or "")
        if sid:
            out[sid] = r.get("current_regime") or "unknown"
    return out


def _candidate_market(cand: dict) -> str:
    """取候选的代表市场（首个可成交腿/源市场）用于查方差与 regime。"""
    for leg in cand.get("legs", []) or []:
        if leg.get("tradeable", True) and leg.get("market_id") is not None:
            return str(leg.get("market_id"))
    sm = cand.get("source_markets") or []
    return str(sm[0]) if sm else ""


# ---------------------------------------------------------------------------
# 顶层入口
# ---------------------------------------------------------------------------

def _edge_return(c: dict, entry_price: Optional[float]) -> float:
    """无量纲每步预期收益率 μ（Phase 5 边量纲校准）。

    优先用 cointegration 候选预先算好的 `expected_return`（与 realized_return 同量纲）；
    缺则退化：价格单位 `expected_edge`/入场价；再缺用 `expected_value`；最后裸 `expected_edge`。
    """
    er = c.get("expected_return")
    if er is not None:
        return float(er)
    edge = c.get("expected_edge")
    if edge is not None and entry_price and entry_price > 0:
        return min(1.0, float(edge) / float(entry_price))
    ev = c.get("expected_value")
    if ev is not None:
        return float(ev)
    return float(edge) if edge is not None else 0.0


def suggest(candidates: list, variance_map: dict, regime_map: dict) -> list:
    """对一批候选给 Kelly + Markowitz sizing 建议（纯函数，可单测）。

    Phase 5 校准：μ 与 σ² 统一在**无量纲收益率空间**——μ 用候选 `expected_return`，
    价格单位的 GARCH 方差 forecast_vol² 经入场价归一为收益率方差 (vol/price)²。
    """
    if not candidates:
        return []
    mus, variances, mkts, regimes = [], [], [], []
    var_prices, prices = [], []
    for c in candidates:
        mid = _candidate_market(c)
        entry_price = c.get("entry_price")
        mu = _edge_return(c, entry_price)
        var_price = float(variance_map.get(mid, DEFAULT_VOL ** 2))   # 价格单位方差
        # 收益率空间方差：(σ_price / price)² ；无 entry_price 时退化为价格单位（向后兼容）
        if entry_price and float(entry_price) > 0:
            var = var_price / (float(entry_price) ** 2)
        else:
            var = var_price
        reg = regime_map.get(mid, "unknown")
        mus.append(float(mu)); variances.append(float(var)); mkts.append(mid); regimes.append(reg)
        var_prices.append(var_price); prices.append(entry_price)

    weights = markowitz_weights(mus, variances)
    out = []
    for i, c in enumerate(candidates):
        kelly = kelly_fraction(mus[i], variances[i], regimes[i])
        out.append({
            "signal_uid": c.get("signal_uid"),
            "models_used": sorted(set((c.get("models_used") or []) + ["kelly", "markowitz"])),
            "market_id": mkts[i],
            "source_markets": c.get("source_markets"),
            "expected_edge": round(float(c.get("expected_edge") or 0.0), 6),  # 价格单位（traceability）
            "expected_return": round(mus[i], 6),       # 无量纲 μ（实际喂 Kelly 的边，Phase 5 校准）
            "entry_price": prices[i],
            "variance": round(variances[i], 8),         # 收益率空间方差（实际喂 Kelly）
            "variance_price": round(var_prices[i], 8),  # 原价格单位方差（traceability）
            "variance_source": "garch" if mkts[i] in variance_map else "default",
            "regime": regimes[i],
            "kelly_raw": kelly["kelly_raw"],
            "kelly_fraction": kelly["kelly_fraction"],
            "regime_scaler": kelly["regime_scaler"],
            "sized_fraction": kelly["sized_fraction"],     # Kelly × regime（绝对仓位建议）
            "markowitz_weight": weights[i],                # 多信号相对配置
            "confidence": c.get("confidence"),
            "rationale": (f"kelly=κ·μ/σ²(收益率空间) 封顶{F_MAX} ×regime({regimes[i]}={kelly['regime_scaler']}); "
                          f"μ={round(mus[i],6)} σ²={round(variances[i],8)}; markowitz w∝Σ⁻¹μ 归一; "
                          f"var_source={'garch' if mkts[i] in variance_map else 'default'}"),
            "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        })
    return out


def compute(base_dir=None) -> dict:
    """读 cointegration 候选 × GARCH 方差 × HMM regime → sizing 建议并落盘。"""
    coint = _load_json(base_dir, "correlation_signals.json")
    vol = _load_json(base_dir, "volatility_states.json")
    regimes = _load_json(base_dir, "regime_states.json")

    candidates = coint.get("candidates", []) or []
    suggestions = suggest(candidates, _variance_map(vol), _regime_map(regimes))

    report = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "model": "kelly_markowitz", "enforced": False,
        "params": {"kelly_kappa": KELLY_KAPPA, "f_max": F_MAX,
                   "regime_scaler": REGIME_SCALER},
        "n_candidates": len(candidates),
        "n_suggestions": len(suggestions),
        "n_var_from_garch": sum(1 for s in suggestions if s["variance_source"] == "garch"),
        "suggestions": suggestions,
    }
    _ds.write_sizing_suggestions(report, base_dir=base_dir)
    return report


def main():
    rep = compute()
    print(json.dumps({
        "model": rep["model"], "enforced": rep["enforced"],
        "n_candidates": rep["n_candidates"], "n_suggestions": rep["n_suggestions"],
        "n_var_from_garch": rep["n_var_from_garch"],
        "top": [(s["market_id"], s["sized_fraction"], s["markowitz_weight"], s["regime"])
                for s in rep["suggestions"][:5]],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
