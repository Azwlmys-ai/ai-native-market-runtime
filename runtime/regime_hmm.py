"""
regime_hmm — HMM 市场状态识别研究引擎（Phase 3g：第二个「真实模型」）
============================================================================
定位（对齐 PRD 第十一节第二优先级「HMM」+ §13 regime 学习 + §10「模型是研究工具」）
----------------------------------------------------------------------------
继协整（Phase 3f）之后的**第二个真实统计模型**。对市场/外部资产的价格变动序列做
**高斯隐马尔可夫（Gaussian HMM）状态识别**，把市场切成 calm（低波动）/ turbulent
（高波动，含新闻驱动跳变）等 regime，产出带**真实 `models_used=["hmm"]`** 的
结构化研究产物——用于：

  * market regime（市场状态：平静 / 动荡）
  * 状态识别（当前处于哪个 regime、刚发生 regime 切换否）
  * 新闻驱动检测（turbulent 态 + 末点异常跳变 → news_driven）
  * 风险情绪（regime 的波动幅度 = 风险状态强弱，喂给 sizing / 风控）

> 关键纪律：本引擎是**研究工具**，产出写入独立产物 `data/regime_states.json` +
> 影子表 `regime_states`，`enforced=False`，**不接入 live executor / agent_b 信号链路**
> （同协整 §10 advisory 纪律）。把 regime 喂进交易/sizing 链路是后续 env 门控的
> 独立步骤（regime 学习闭环 + Kelly/Markowitz），需单独评审。

方法（Baum-Welch EM + Viterbi，仅依赖 numpy，避开 hmmlearn/statsmodels）
------------------------------------------------------------------------
对一条价格序列 p（取最近 N 点）：
  1. 观测 = 一阶差分 o[t] = p[t] − p[t−1]（预测市场概率移动幅度；价格在 [0,1]，用绝对变动）。
  2. K 态高斯 HMM：每态 (mu_k, var_k) 高斯发射 + 转移矩阵 A + 初始分布 pi。
  3. 确定性初始化：按观测分位数切 K 组定 mu/var（无随机），EM（带 scaling 的前向后向）
     迭代至对数似然收敛或达上限 → 收敛确定（同输入同输出）。
  4. Viterbi 解码最可能状态序列；当前 regime = 末点状态。
  5. 按方差升序给状态贴标签：方差最小=calm，最大=turbulent（K=3 中间=normal）。

防伪 regime 护栏（点少必须）
--------------------------
点数少（当前每序列仅 ~10 点）极易把噪声当 regime。故要求：
  * 序列真的在动（std>eps）且不同取值数 >= MIN_DISTINCT；
  * 观测数 >= MIN_OBS；
  * 两态方差分离不足（separation < 阈值）→ 标 regime_confident=False，诚实降级。
并对每条打 `data_sufficiency`（low / medium）。

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

SCHEMA_VERSION = "0.3.8-phase3g-hmm-regime"
MODEL_NAME = "hmm"
METHOD = "gaussian_hmm_baum_welch"

# 阈值（保守；点少时防伪 regime）
N_STATES = 2            # 状态数（calm / turbulent）；短序列下 2 态最稳健
MIN_OBS = 10            # 最少观测（差分）数 → 序列长度需 >= MIN_OBS+1
MIN_DISTINCT = 4        # 最少不同取值数（防 2 值序列伪 regime）
EPS = 1e-9
VAR_FLOOR_REL = 1e-3    # 方差地板（相对全局方差），防 EM 方差塌缩
MAX_ITER = 80           # Baum-Welch 上限
TOL = 1e-6              # 对数似然收敛阈值
SEPARATION_MIN = 1.5    # turbulent_std / calm_std 下限；不足则 regime 不显著
NEWS_SIGMA = 2.0        # 末点 |变动| >= turbulent_std·此倍数 → 视为新闻驱动跳变
DATA_SUFFICIENCY_MEDIUM = 25   # 观测数 >= 此值才算 medium，否则 low

_STATE_LABELS = {
    2: ["calm", "turbulent"],            # 按方差升序
    3: ["calm", "normal", "turbulent"],
}


# ---------------------------------------------------------------------------
# 数值工具
# ---------------------------------------------------------------------------

def _n_distinct(s: np.ndarray) -> int:
    return int(len(np.unique(np.round(s, 6))))


def _gaussian_logpdf(o: np.ndarray, mu: float, var: float) -> np.ndarray:
    var = max(var, EPS)
    return -0.5 * (np.log(2.0 * math.pi * var) + (o - mu) ** 2 / var)


# ---------------------------------------------------------------------------
# 高斯 HMM：确定性初始化 + Baum-Welch（带 scaling）+ Viterbi
# ---------------------------------------------------------------------------

def _init_params(o: np.ndarray, k: int) -> tuple:
    """按观测分位数切 k 组，定 (pi, A, mu, var)。完全确定性，无随机。"""
    order = np.argsort(o)
    groups = np.array_split(order, k)
    mu = np.array([float(np.mean(o[g])) for g in groups])
    global_var = float(np.var(o)) + EPS
    var = np.array([max(float(np.var(o[g])), VAR_FLOOR_REL * global_var) for g in groups])
    pi = np.full(k, 1.0 / k)
    # 黏性转移：对角 0.9，其余均分
    A = np.full((k, k), 0.1 / max(k - 1, 1))
    np.fill_diagonal(A, 0.9)
    return pi, A, mu, var


def _forward_backward(o: np.ndarray, pi, A, mu, var) -> tuple:
    """带 scaling 的前向后向。返回 (gamma, xi, loglik)。"""
    T, k = len(o), len(pi)
    # 发射概率 B[t,j]：对数空间减去逐行最大值做数值稳定（避免极小方差时 exp 溢出）。
    # 减去的 rowmax 是逐时刻常数，会在 gamma/xi 归一中抵消（后验不变）；
    # 但 loglik = Σlog(scale) 会因此偏移 −Σrowmax，故末尾加回 rowmax 还原真实对数似然。
    logB = np.stack([_gaussian_logpdf(o, mu[j], var[j]) for j in range(k)], axis=1)
    rowmax = logB.max(axis=1, keepdims=True)
    B = np.exp(logB - rowmax)
    B = np.clip(B, 1e-300, None)

    alpha = np.zeros((T, k))
    scale = np.zeros(T)
    alpha[0] = pi * B[0]
    scale[0] = alpha[0].sum() + EPS
    alpha[0] /= scale[0]
    for t in range(1, T):
        alpha[t] = (alpha[t - 1] @ A) * B[t]
        scale[t] = alpha[t].sum() + EPS
        alpha[t] /= scale[t]

    beta = np.zeros((T, k))
    beta[-1] = 1.0
    for t in range(T - 2, -1, -1):
        beta[t] = (A @ (B[t + 1] * beta[t + 1])) / scale[t + 1]

    gamma = alpha * beta
    gamma /= gamma.sum(axis=1, keepdims=True) + EPS

    xi = np.zeros((T - 1, k, k))
    for t in range(T - 1):
        m = (alpha[t][:, None] * A) * (B[t + 1] * beta[t + 1])[None, :]
        s = m.sum()
        xi[t] = m / (s + EPS)

    loglik = float(np.sum(np.log(scale)) + np.sum(rowmax))   # 加回数值稳定偏移 → 真实对数似然
    return gamma, xi, loglik


def fit_hmm(o: np.ndarray, k: int = N_STATES, max_iter: int = MAX_ITER) -> dict:
    """Baum-Welch EM 拟合高斯 HMM。确定性（固定初始化 + 固定迭代）。"""
    pi, A, mu, var = _init_params(o, k)
    global_var = float(np.var(o)) + EPS
    var_floor = VAR_FLOOR_REL * global_var
    prev_ll = -np.inf
    gamma = None
    for _ in range(max_iter):
        gamma, xi, ll = _forward_backward(o, pi, A, mu, var)
        # M-step
        pi = gamma[0].copy()
        A_num = xi.sum(axis=0)
        A_den = gamma[:-1].sum(axis=0)[:, None] + EPS
        A = A_num / A_den
        A /= A.sum(axis=1, keepdims=True) + EPS
        w = gamma.sum(axis=0) + EPS
        mu = (gamma * o[:, None]).sum(axis=0) / w
        var = (gamma * (o[:, None] - mu[None, :]) ** 2).sum(axis=0) / w
        var = np.maximum(var, var_floor)
        if abs(ll - prev_ll) < TOL:
            prev_ll = ll
            break
        prev_ll = ll
    return {"pi": pi, "A": A, "mu": mu, "var": var, "gamma": gamma, "loglik": prev_ll}


def viterbi(o: np.ndarray, pi, A, mu, var) -> np.ndarray:
    """对数空间 Viterbi，返回最可能状态序列。"""
    T, k = len(o), len(pi)
    logpi = np.log(np.clip(pi, 1e-300, None))
    logA = np.log(np.clip(A, 1e-300, None))
    logB = np.stack([_gaussian_logpdf(o, mu[j], var[j]) for j in range(k)], axis=1)
    delta = np.zeros((T, k))
    psi = np.zeros((T, k), dtype=int)
    delta[0] = logpi + logB[0]
    for t in range(1, T):
        for j in range(k):
            seq = delta[t - 1] + logA[:, j]
            psi[t, j] = int(np.argmax(seq))
            delta[t, j] = seq[psi[t, j]] + logB[t, j]
    path = np.zeros(T, dtype=int)
    path[-1] = int(np.argmax(delta[-1]))
    for t in range(T - 2, -1, -1):
        path[t] = psi[t + 1, path[t + 1]]
    return path


# ---------------------------------------------------------------------------
# 单序列 regime 分析
# ---------------------------------------------------------------------------

def analyze_series(series_id: str, series: list, k: int = N_STATES) -> Optional[dict]:
    """对一条价格序列拟合 HMM 并解码当前 regime。数据不足/不动时返回 None。"""
    n = len(series)
    if n < MIN_OBS + 1:
        return None
    p = np.asarray(series[-(min(n, 80)):], dtype=float)
    if np.std(p) < EPS or _n_distinct(p) < MIN_DISTINCT:
        return None
    o = np.diff(p)
    if len(o) < MIN_OBS or np.std(o) < EPS:
        return None

    fit = fit_hmm(o, k=k)
    pi, A, mu, var = fit["pi"], fit["A"], fit["mu"], fit["var"]
    path = viterbi(o, pi, A, mu, var)

    # 按方差升序贴标签（方差小=calm，大=turbulent）
    order = list(np.argsort(var))
    labels = _STATE_LABELS.get(k, [f"state_{i}" for i in range(k)])
    state_label = {int(state_idx): labels[rank] for rank, state_idx in enumerate(order)}
    calm_idx, turb_idx = int(order[0]), int(order[-1])

    cur_state = int(path[-1])
    prev_state = int(path[-2]) if len(path) >= 2 else cur_state
    gamma_last = fit["gamma"][-1]

    std = np.sqrt(np.maximum(var, EPS))
    separation = float(std[turb_idx] / max(std[calm_idx], EPS))
    last_change = float(o[-1])
    turb_std = float(std[turb_idx])
    news_driven = bool(cur_state == turb_idx and abs(last_change) >= NEWS_SIGMA * max(turb_std, EPS))

    states_meta = []
    for rank, st in enumerate(order):
        st = int(st)
        self_p = float(A[st, st])
        expected_dur = float(1.0 / max(1.0 - self_p, EPS))
        states_meta.append({
            "state": st, "label": labels[rank],
            "mean_change": round(float(mu[st]), 6),
            "std_change": round(float(std[st]), 6),
            "weight": round(float(np.mean(path == st)), 4),
            "self_transition": round(self_p, 4),
            "expected_duration": round(expected_dur, 2),
        })

    return {
        "series_id": series_id,
        "n_states": k,
        "n_obs": int(len(o)),
        "current_state": cur_state,
        "current_regime": state_label[cur_state],
        "prev_regime": state_label[prev_state],
        "regime_shift": bool(cur_state != prev_state),
        "regime_posterior": {state_label[int(j)]: round(float(gamma_last[j]), 4)
                             for j in range(k)},
        "posterior_certainty": round(float(np.max(gamma_last)), 4),
        "separation": round(separation, 4),
        "news_driven": news_driven,
        "last_change": round(last_change, 6),
        "calm_state": calm_idx, "turbulent_state": turb_idx,
        "transition_matrix": np.round(A, 4).tolist(),
        "states": states_meta,
        "loglik": round(float(fit["loglik"]), 4),
    }


def _is_confident(st: dict) -> bool:
    """regime 是否显著：方差分离够 + 末点后验确定 + 数据够。"""
    if st["separation"] < SEPARATION_MIN:
        return False
    if st["posterior_certainty"] < 0.6:
        return False
    return True


def _confidence(st: dict) -> float:
    """确定性置信：随后验确定度与方差分离升高，封顶 90（同协整封顶）。"""
    base = 30.0
    base += 40.0 * min(st["posterior_certainty"], 1.0)
    base += 8.0 * min(st["separation"] - 1.0, 3.0)
    return round(min(90.0, max(0.0, base)), 1)


def _build_regime_signal(st: dict, kind: Optional[str] = None) -> dict:
    """组装成结构化研究产物（PRD §8 可解释 schema）。"""
    sufficiency = "medium" if st["n_obs"] >= DATA_SUFFICIENCY_MEDIUM else "low"
    confident = _is_confident(st)
    turb = next(s for s in st["states"] if s["label"] == "turbulent")
    calm = next(s for s in st["states"] if s["label"] == "calm")
    return {
        "signal_uid": _ds.uid(MODEL_NAME, st["series_id"]),
        "models_used": [MODEL_NAME],
        "method": METHOD,
        "series_id": st["series_id"],
        "series_kind": kind,                 # pm_market / crypto / us_stock / macro
        "current_regime": st["current_regime"],
        "regime_shift": st["regime_shift"],
        "news_driven": st["news_driven"],
        "regime_confident": confident,
        "regime_posterior": st["regime_posterior"],
        "evidence": {
            "n_states": st["n_states"], "n_obs": st["n_obs"],
            "states": st["states"],
            "transition_matrix": st["transition_matrix"],
            "separation": st["separation"],
            "posterior_certainty": st["posterior_certainty"],
            "current_volatility": abs(st["last_change"]),
            "calm_std": calm["std_change"], "turbulent_std": turb["std_change"],
            "expected_duration_current": next(
                s["expected_duration"] for s in st["states"]
                if s["label"] == st["current_regime"]),
            "loglik": st["loglik"],
        },
        "confidence": _confidence(st),
        # regime 是状态描述而非方向性下注；预期边为「当前态相对全局的风险强度」占位，
        # 真正消费（sizing/风控/择时）在后续 env 门控闭环里做。
        "expected_edge": 0.0,
        "failure_conditions": [
            "若结构突变使历史 regime 估计失效（如市场临近结算、规则变更）",
            "若样本不足导致 HMM 把噪声误判为 regime（separation 低、后验不确定）",
            f"若波动状态非平稳，转移矩阵漂移（当前 self_transition={turb['self_transition']}）",
            f"若样本不足（当前 n_obs={st['n_obs']}，data_sufficiency={sufficiency}）使状态估计不稳健",
        ],
        "data_sufficiency": sufficiency,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


# ---------------------------------------------------------------------------
# 顶层入口
# ---------------------------------------------------------------------------

def _collect_series(base_dir, field: str) -> list:
    """收集待分析序列：Polymarket 市场(field) + 外部资产(price)。返回 [(id, series, kind)]。"""
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


def find_regimes(base_dir=None, field: str = "yes_price", k: int = N_STATES) -> dict:
    """加载价格历史 → 逐序列 HMM regime 识别 → 汇总。"""
    series_list = _collect_series(base_dir, field)
    regimes, n_considered = [], 0
    for sid, s, kind in series_list:
        st = analyze_series(sid, s, k=k)
        if st is None:
            continue
        n_considered += 1
        regimes.append(_build_regime_signal(st, kind=kind))

    # 排序：先 regime_shift（刚切换）、再 news_driven、再 turbulent、再置信度
    def _rank(r):
        return (r.get("regime_shift", False), r.get("news_driven", False),
                r.get("current_regime") == "turbulent", r.get("confidence", 0.0))
    regimes.sort(key=_rank, reverse=True)

    n_turbulent = sum(1 for r in regimes if r["current_regime"] == "turbulent")
    n_shift = sum(1 for r in regimes if r["regime_shift"])
    n_news = sum(1 for r in regimes if r["news_driven"])
    n_confident = sum(1 for r in regimes if r["regime_confident"])
    return {
        "n_series_total": len(series_list),
        "n_series_considered": n_considered,
        "n_regimes": len(regimes),
        "n_turbulent": n_turbulent,
        "n_regime_shift": n_shift,
        "n_news_driven": n_news,
        "n_confident": n_confident,
        "regimes": regimes,
    }


def compute(base_dir=None, field: str = "yes_price", k: int = N_STATES) -> dict:
    """跑 HMM regime 识别 → 落盘研究产物 `data/regime_states.json` + 影子表。

    返回报告 dict。best-effort：研究产物，失败不应中断主流程。
    """
    res = find_regimes(base_dir, field=field, k=k)
    report = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "model": MODEL_NAME, "method": METHOD, "field": field,
        "enforced": False,   # 研究产物，未接入 live 交易链路
        "params": {"n_states": k, "min_obs": MIN_OBS, "separation_min": SEPARATION_MIN,
                   "news_sigma": NEWS_SIGMA, "max_iter": MAX_ITER},
        **res,
    }
    _ds.write_regime_states(report, base_dir=base_dir)
    return report


def main():
    rep = compute()
    print(json.dumps({
        "model": rep["model"], "method": rep["method"], "enforced": rep["enforced"],
        "n_series_considered": rep["n_series_considered"],
        "n_regimes": rep["n_regimes"], "n_turbulent": rep["n_turbulent"],
        "n_regime_shift": rep["n_regime_shift"], "n_news_driven": rep["n_news_driven"],
        "top": [(r["series_id"], r["current_regime"], r["regime_shift"],
                 r["news_driven"], r["confidence"], r["data_sufficiency"])
                for r in rep["regimes"][:5]],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
