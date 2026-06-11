"""Phase 3f — cointegration 协整/spread 研究引擎单测（确定性，numpy-only，不触 DB/网络）。

用合成数据验证：对冲比/相关/z-score 计算、均值回归半衰期、伪相关护栏、
候选阈值过滤、信号 schema（models_used/evidence/failure_conditions）、compute 落盘。
"""

import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from runtime import cointegration as ci


def test_ols_recovers_hedge_ratio():
    rng = np.random.default_rng(0)
    b = np.linspace(0.3, 0.7, 30)
    a = 0.5 * b + 0.1 + rng.normal(0, 1e-3, size=30)  # a ≈ 0.5b + 0.1
    slope, intercept = ci._ols_slope_intercept(b, a)
    assert abs(slope - 0.5) < 0.05
    assert abs(intercept - 0.1) < 0.05


def test_half_life_monotonic_in_phi():
    # phi 越接近 1，半衰期越长；phi>=1 无意义返回 None
    assert ci._half_life(0.5) < ci._half_life(0.9)
    assert ci._half_life(1.0) is None
    assert ci._half_life(-0.2) is None


def test_flat_or_low_distinct_series_rejected():
    flat = [0.5] * 12
    assert ci.analyze_pair("a", flat, "b", list(np.linspace(0.3, 0.7, 12))) is None
    two_val = [0.4, 0.6] * 6  # 仅 2 个取值 → 伪相关护栏拦截
    assert ci.analyze_pair("a", two_val, "b", two_val) is None


def test_cointegrated_pair_with_deviation_becomes_candidate():
    # 构造强相关、均值回归的 spread，末点人为拉偏 → 应过阈值成候选
    rng = np.random.default_rng(1)
    b = 0.5 + 0.05 * np.sin(np.linspace(0, 6, 24)) + rng.normal(0, 1e-3, 24)
    a = 1.0 * b + rng.normal(0, 2e-3, 24)   # a≈b，高相关，spread 平稳
    a = a.copy()
    a[-1] += 0.05                            # 末点把 spread 拉到 >2σ
    st = ci.analyze_pair("mA", list(a), "mB", list(b))
    assert st is not None
    assert abs(st["corr"]) >= ci.CORR_MIN
    assert abs(st["zscore"]) >= ci.Z_MIN
    if ci._is_candidate(st):
        sig = ci._build_signal(st)
        assert sig["models_used"] == ["cointegration"]
        assert sig["source_markets"] == ["mA", "mB"]
        assert "zscore" in sig["evidence"]
        assert len(sig["failure_conditions"]) >= 3
        assert sig["data_sufficiency"] in ("low", "medium")
        assert 0 <= sig["confidence"] <= 90


def test_compute_writes_research_artifact(tmp_path, monkeypatch):
    monkeypatch.delenv("PA_SHADOW_DB", raising=False)
    data = tmp_path / "data"
    data.mkdir()
    rng = np.random.default_rng(2)
    b = (0.5 + 0.06 * np.sin(np.linspace(0, 6, 24)) + rng.normal(0, 1e-3, 24))
    a = (1.0 * b + rng.normal(0, 2e-3, 24))
    a[-1] += 0.06

    def _series(arr):
        return [{"ts": f"2026-06-0{1+i%9}T00:00:00", "yes_price": float(v),
                 "no_price": float(1 - v), "liquidity": 10000.0} for i, v in enumerate(arr)]

    hist = {"mA": _series(a), "mB": _series(b), "flat": _series([0.5] * 24)}
    (data / "market_price_history.json").write_text(json.dumps(hist), encoding="utf-8")

    rep = ci.compute(base_dir=tmp_path)
    assert rep["enforced"] is False
    assert rep["model"] == "cointegration"
    assert rep["n_markets_considered"] == 2          # flat 被护栏剔除
    assert (data / "correlation_signals.json").exists()
    saved = json.loads((data / "correlation_signals.json").read_text(encoding="utf-8"))
    assert saved["schema_version"] == ci.SCHEMA_VERSION


# ---------------------------------------------------------------------------
# 探索层（Phase 5 / PRD §6 paper_probe 弱关联低风险试错；env 门控 PA_COINT_EXPLORE）
# ---------------------------------------------------------------------------

def _weak_comoving_pair():
    """确定性弱关联共动配对：corr∈[0.5,0.8)（低于研究阈值）、末点偏离 |z|≥1.5、价差均值回归。
    与 bootstrap --demo 同构（stdlib random seed=42）。返回 (series_a, series_b)。"""
    import random
    rnd = random.Random(42)
    f = 0.0
    a, b = [], []
    for _ in range(60):
        f = 0.85 * f + rnd.gauss(0, 1)
        a.append(0.50 + 0.030 * f + rnd.gauss(0, 0.026))
        b.append(0.50 + 0.024 * f + rnd.gauss(0, 0.026))
    a[-1] += 0.10
    clamp = lambda x: max(0.02, min(0.98, x))
    return [clamp(v) for v in a], [clamp(v) for v in b]


def _write_pair(data_dir, a, b):
    def _s(arr):
        return [{"ts": f"2026-05-{1+i//24:02d}T{i%24:02d}:00:00", "yes_price": float(v),
                 "no_price": float(1 - v), "liquidity": 5000.0} for i, v in enumerate(arr)]
    (data_dir / "market_price_history.json").write_text(
        json.dumps({"WA": _s(a), "WB": _s(b)}), encoding="utf-8")


def test_weak_pair_is_exploration_only_not_research():
    a, b = _weak_comoving_pair()
    st = ci.analyze_pair("WA", a, "WB", b)
    assert st is not None
    assert ci.EXPLORE_CORR_MIN <= abs(st["corr"]) < ci.CORR_MIN   # 落在探索带，研究阈值不过
    assert abs(st["zscore"]) >= ci.EXPLORE_Z_MIN
    assert ci._is_candidate(st) is False                          # 研究层（严格）拒
    assert ci._is_candidate(st, ci.EXPLORE_CORR_MIN, ci.EXPLORE_Z_MIN) is True  # 探索层收


def test_explore_gate_default_off_zero_regression(tmp_path, monkeypatch):
    monkeypatch.delenv("PA_COINT_EXPLORE", raising=False)
    monkeypatch.delenv("PA_SHADOW_DB", raising=False)
    data = tmp_path / "data"; data.mkdir()
    _write_pair(data, *_weak_comoving_pair())
    rep = ci.find_candidates(base_dir=tmp_path)
    assert rep["explore_enabled"] is False
    assert rep["n_candidates"] == 0                  # 弱关联在门控关时不出候选
    assert rep["n_candidates_exploration"] == 0


def test_explore_gate_on_emits_low_confidence_exploration_probe(tmp_path, monkeypatch):
    monkeypatch.setenv("PA_COINT_EXPLORE", "1")
    monkeypatch.delenv("PA_SHADOW_DB", raising=False)
    data = tmp_path / "data"; data.mkdir()
    _write_pair(data, *_weak_comoving_pair())
    rep = ci.find_candidates(base_dir=tmp_path)
    assert rep["explore_enabled"] is True
    assert rep["n_candidates_exploration"] >= 1
    assert rep["n_candidates_research"] == 0
    cand = rep["candidates"][0]
    assert cand["tier"] == "exploration"
    assert cand["confidence"] <= ci.EXPLORE_CONF_CAP          # 低置信 → Agent M 路由 paper_probe
    assert any("探索层弱关联" in fc for fc in cand["failure_conditions"])
    assert cand["models_used"] == ["cointegration"]


def test_explore_still_filters_nonstationary():
    # 平稳性(半衰期)过滤与层无关：corr/z 即便过放松阈值，价差非平稳仍拒。
    st = {"corr": 0.62, "zscore": 2.0, "half_life": None}
    assert ci._is_candidate(st, ci.EXPLORE_CORR_MIN, ci.EXPLORE_Z_MIN) is False
    st_ok = {"corr": 0.62, "zscore": 2.0, "half_life": 5.0}
    assert ci._is_candidate(st_ok, ci.EXPLORE_CORR_MIN, ci.EXPLORE_Z_MIN) is True


def test_to_pipeline_signals_exploration_smaller_size_and_tier():
    a, b = _weak_comoving_pair()
    st = ci.analyze_pair("WA", a, "WB", b)
    sig = ci._build_signal(st, tier="exploration")
    out = ci.to_pipeline_signals({"candidates": [sig]})
    assert len(out) == 2                                    # pm_pm 两腿
    for s in out:
        assert s["tier"] == "exploration"
        assert s["position_size"] == ci.EXPLORE_POSITION_SIZE  # 探索更小 probe 仓位
        assert s["models_used"] == ["cointegration"]
        assert s["confidence"] <= ci.EXPLORE_CONF_CAP
