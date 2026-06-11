"""Phase 3h — garch GARCH(1,1) 波动率研究引擎单测（确定性，numpy-only，不触 DB/网络）。

用合成数据验证：方差目标化网格 MLE 恢复波动聚集、平稳约束、风险状态/趋势判定、
vol_spike、伪护栏剔除、信号 schema、compute 落盘、确定性可复现。
"""

import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from runtime import garch


def _garch_series(seed=0, n=60, omega=1e-5, alpha=0.2, beta=0.7):
    """按真实 GARCH(1,1) 过程生成价格序列（用于验证拟合能识别聚集）。"""
    rng = np.random.default_rng(seed)
    sigma2 = omega / max(1 - alpha - beta, 1e-3)
    r = np.zeros(n)
    for t in range(1, n):
        sigma2 = omega + alpha * r[t - 1] ** 2 + beta * sigma2
        r[t] = rng.normal(0, np.sqrt(sigma2))
    return list(0.5 + np.cumsum(r))


def test_fit_recovers_persistence():
    s = _garch_series(seed=1, alpha=0.15, beta=0.8)   # 高 persistence ~0.95
    st = garch.analyze_series("mA", s)
    assert st is not None
    assert 0 <= st["persistence"] <= garch.MAX_PERSIST
    assert st["clustering"] is True            # 高持续性应判定聚集
    assert st["alpha"] + st["beta"] == st["persistence"]


def test_stationarity_constraint_respected():
    s = _garch_series(seed=2)
    st = garch.analyze_series("mB", s)
    assert st["persistence"] <= garch.MAX_PERSIST + 1e-9


def test_flat_and_short_series_rejected():
    assert garch.analyze_series("flat", [0.5] * 40) is None
    assert garch.analyze_series("twoval", [0.4, 0.6] * 20) is None
    assert garch.analyze_series("short", [0.5, 0.51, 0.49]) is None


def test_vol_spike_flag_on_terminal_jump():
    s = _garch_series(seed=3, alpha=0.1, beta=0.5)
    s = s[:-1] + [s[-1] + 0.4]    # 末点制造远超长期波动的跳变
    st = garch.analyze_series("mC", s)
    assert st["vol_spike"] is True


def test_signal_schema_fields():
    s = _garch_series(seed=4)
    sig = garch._build_signal(garch.analyze_series("mD", s), kind="crypto")
    assert sig["models_used"] == ["garch"]
    assert sig["series_kind"] == "crypto"
    assert sig["risk_state"] in ("elevated", "normal", "calm")
    assert sig["vol_trend"] in ("rising", "falling", "stable")
    assert "persistence" in sig["evidence"]
    assert "forecast_vol" in sig["evidence"]
    assert len(sig["failure_conditions"]) >= 3
    assert 0 <= sig["confidence"] <= 90


def test_determinism():
    s = _garch_series(seed=5)
    a = garch.analyze_series("mE", s)
    b = garch.analyze_series("mE", s)
    assert (a["alpha"], a["beta"], a["loglik"]) == (b["alpha"], b["beta"], b["loglik"])


def test_compute_writes_research_artifact(tmp_path, monkeypatch):
    monkeypatch.delenv("PA_SHADOW_DB", raising=False)
    data = tmp_path / "data"
    data.mkdir()
    s = _garch_series(seed=6)

    def _series(arr):
        return [{"ts": f"2026-06-0{1+i%9}T00:00:00", "yes_price": float(v),
                 "no_price": float(1 - v), "liquidity": 10000.0} for i, v in enumerate(arr)]

    hist = {"mA": _series(s), "flat": _series([0.5] * 60)}
    (data / "market_price_history.json").write_text(json.dumps(hist), encoding="utf-8")

    rep = garch.compute(base_dir=tmp_path)
    assert rep["enforced"] is False
    assert rep["model"] == "garch"
    assert rep["n_series_considered"] == 1          # flat 被护栏剔除
    assert (data / "volatility_states.json").exists()
    saved = json.loads((data / "volatility_states.json").read_text(encoding="utf-8"))
    assert saved["schema_version"] == garch.SCHEMA_VERSION
    assert saved["states"][0]["models_used"] == ["garch"]
