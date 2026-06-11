"""Phase 3i — position_sizing Kelly+Markowitz 仓位建议单测（确定性，numpy-only）。

验证：Kelly 分数（封顶/负边归零/regime 缩放）、Markowitz 权重（归一/long-only/方差反比）、
suggest 串联三模型、compute 读 cointegration×GARCH×regime 落盘、enforced=False。
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from runtime import position_sizing as ps


def test_kelly_caps_and_zeroes():
    # 大正边 → 被 F_MAX 封顶
    k = ps.kelly_fraction(mu=1.0, var=0.001)
    assert k["kelly_fraction"] == ps.F_MAX
    # 负边 → 0（不下注）
    assert ps.kelly_fraction(mu=-0.5, var=0.01)["kelly_fraction"] == 0.0
    # 小正边 → 介于 0 和 F_MAX
    k2 = ps.kelly_fraction(mu=0.001, var=0.01)
    assert 0 < k2["kelly_fraction"] <= ps.F_MAX


def test_kelly_regime_scaler():
    base = ps.kelly_fraction(mu=0.05, var=0.01, regime="calm")
    turb = ps.kelly_fraction(mu=0.05, var=0.01, regime="turbulent")
    assert turb["sized_fraction"] <= base["sized_fraction"]
    assert turb["regime_scaler"] == ps.REGIME_SCALER["turbulent"]


def test_markowitz_weights_normalized_and_long_only():
    w = ps.markowitz_weights([0.1, 0.2, -0.1], [0.01, 0.01, 0.01])
    assert abs(sum(w) - 1.0) < 1e-6
    assert all(x >= 0 for x in w)
    assert w[2] == 0.0                       # 负边权重归零
    # 同边时低方差应获更高权重
    w2 = ps.markowitz_weights([0.1, 0.1], [0.01, 0.04])
    assert w2[0] > w2[1]


def test_markowitz_all_nonpositive_returns_zeros():
    w = ps.markowitz_weights([-0.1, 0.0], [0.01, 0.01])
    assert w == [0.0, 0.0]


def test_suggest_links_three_models():
    candidates = [
        {"signal_uid": "c1", "models_used": ["cointegration"],
         "source_markets": ["100", "200"], "expected_edge": 0.05, "confidence": 70,
         "legs": [{"market_id": "100", "tradeable": True}, {"market_id": "200", "tradeable": True}]},
    ]
    var_map = {"100": 0.0009}        # forecast_vol=0.03 → var
    regime_map = {"100": "turbulent"}
    out = ps.suggest(candidates, var_map, regime_map)
    assert len(out) == 1
    s = out[0]
    assert s["market_id"] == "100"
    assert s["variance_source"] == "garch"
    assert s["regime"] == "turbulent"
    assert "kelly" in s["models_used"] and "markowitz" in s["models_used"]
    assert s["regime_scaler"] == ps.REGIME_SCALER["turbulent"]
    assert 0 <= s["sized_fraction"] <= ps.F_MAX


def test_suggest_default_variance_when_no_garch():
    candidates = [{"signal_uid": "c1", "source_markets": ["999"], "expected_edge": 0.05,
                   "legs": [{"market_id": "999", "tradeable": True}]}]
    out = ps.suggest(candidates, {}, {})
    assert out[0]["variance_source"] == "default"
    assert out[0]["regime"] == "unknown"


def test_compute_writes_artifact(tmp_path, monkeypatch):
    monkeypatch.delenv("PA_SHADOW_DB", raising=False)
    data = tmp_path / "data"
    data.mkdir()
    coint = {"candidates": [
        {"signal_uid": "c1", "models_used": ["cointegration"], "source_markets": ["100", "200"],
         "expected_edge": 0.04, "confidence": 65,
         "legs": [{"market_id": "100", "tradeable": True}, {"market_id": "200", "tradeable": True}]},
    ]}
    vol = {"states": [{"series_id": "100", "evidence": {"forecast_vol": 0.03}}]}
    regimes = {"regimes": [{"series_id": "100", "current_regime": "calm"}]}
    (data / "correlation_signals.json").write_text(json.dumps(coint), encoding="utf-8")
    (data / "volatility_states.json").write_text(json.dumps(vol), encoding="utf-8")
    (data / "regime_states.json").write_text(json.dumps(regimes), encoding="utf-8")

    rep = ps.compute(base_dir=tmp_path)
    assert rep["enforced"] is False
    assert rep["n_suggestions"] == 1
    assert rep["n_var_from_garch"] == 1
    saved = json.loads((data / "sizing_suggestions.json").read_text(encoding="utf-8"))
    assert saved["schema_version"] == ps.SCHEMA_VERSION
    assert saved["suggestions"][0]["regime"] == "calm"


def test_empty_candidates(tmp_path, monkeypatch):
    monkeypatch.delenv("PA_SHADOW_DB", raising=False)
    (tmp_path / "data").mkdir()
    rep = ps.compute(base_dir=tmp_path)
    assert rep["n_suggestions"] == 0
    assert rep["suggestions"] == []


# --- Phase 5 边量纲校准 -------------------------------------------------------

def test_dimensionless_edge_calibration():
    from runtime import cointegration as coint
    # μ = (1−φ)·expected_edge/price
    assert coint._dimensionless_edge(0.04, 0.8, 0.5) == round(0.2 * 0.04 / 0.5, 6)   # 0.016
    # 慢回归(φ小) → 更大每步边；快回归(φ大) → 更小
    assert coint._dimensionless_edge(0.04, 0.5, 0.5) > coint._dimensionless_edge(0.04, 0.95, 0.5)
    # 无入场价 → None（sizing 端走退化）；钳到 [0,1]
    assert coint._dimensionless_edge(0.04, 0.8, None) is None
    assert coint._dimensionless_edge(10.0, 0.0, 0.5) == 1.0


def test_suggest_uses_return_space_when_calibrated():
    # 带 entry_price + expected_return 的候选 → μ 用 expected_return，σ² 归一为 (vol/price)²
    cand = {"signal_uid": "c1", "models_used": ["cointegration"],
            "source_markets": ["100", "200"], "expected_edge": 0.04,
            "expected_return": 0.016, "entry_price": 0.5, "confidence": 70,
            "legs": [{"market_id": "100", "tradeable": True}]}
    var_map = {"100": 0.08 ** 2}                 # 价格单位方差
    out = ps.suggest([cand], var_map, {"100": "calm"})[0]
    assert out["expected_return"] == 0.016
    assert out["expected_edge"] == 0.04          # 价格单位保留 traceability
    assert out["variance"] == round((0.08 / 0.5) ** 2, 8)   # 收益率空间方差
    assert out["variance_price"] == round(0.08 ** 2, 8)
    # 高 vol 下不再恒撞 F_MAX
    assert out["kelly_fraction"] < ps.F_MAX


def test_suggest_backward_compat_no_entry_price():
    # 旧候选（无 entry_price/expected_return）→ μ 退化为 expected_edge，σ² 保持价格单位
    cand = {"signal_uid": "c1", "source_markets": ["100"], "expected_edge": 0.05,
            "legs": [{"market_id": "100", "tradeable": True}]}
    out = ps.suggest([cand], {"100": 0.03 ** 2}, {})[0]
    assert out["expected_return"] == 0.05        # 退化等于价格单位边
    assert out["variance"] == round(0.03 ** 2, 8)
    assert out["entry_price"] is None
