"""Phase 3g — regime_hmm HMM 市场状态识别单测（确定性，numpy-only，不触 DB/网络）。

用合成两段式（calm→turbulent）价格序列验证：高斯 HMM Baum-Welch 拟合 + Viterbi 解码、
状态按方差贴标签、当前 regime 识别、regime_shift / news_driven、伪 regime 护栏、
信号 schema（models_used/evidence/failure_conditions）、compute 落盘、确定性可复现。
"""

import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from runtime import regime_hmm as hmm


def _two_regime_series(seed=0, n_calm=24, n_turb=24, calm_sd=0.002, turb_sd=0.05,
                       last_jump=None):
    """前段 calm（小波动）+ 后段 turbulent（大波动）拼接的价格序列。"""
    rng = np.random.default_rng(seed)
    calm = rng.normal(0.0, calm_sd, n_calm)
    turb = rng.normal(0.0, turb_sd, n_turb)
    o = np.concatenate([calm, turb])
    if last_jump is not None:
        o[-1] = last_jump
    return list(0.5 + np.cumsum(o))


def test_hmm_separates_two_volatility_regimes():
    s = _two_regime_series(seed=1)
    st = hmm.analyze_series("mA", s)
    assert st is not None
    # 末段是 turbulent → 当前 regime 应为 turbulent
    assert st["current_regime"] == "turbulent"
    # 方差分离应明显（turbulent_std >> calm_std）
    assert st["separation"] >= hmm.SEPARATION_MIN
    # 两态 std 升序对应 calm < turbulent
    stds = [x["std_change"] for x in sorted(st["states"], key=lambda r: r["std_change"])]
    assert stds[0] < stds[-1]


def test_flat_and_low_distinct_series_rejected():
    assert hmm.analyze_series("flat", [0.5] * 40) is None          # 不动
    assert hmm.analyze_series("twoval", [0.4, 0.6] * 20) is None    # 仅 2 取值
    assert hmm.analyze_series("short", [0.5, 0.51, 0.49]) is None   # 点数不足


def test_news_driven_flag_on_terminal_jump():
    # 末点制造远超 turbulent 波动的跳变 → news_driven
    s = _two_regime_series(seed=2, last_jump=0.25)
    sig = hmm._build_regime_signal(hmm.analyze_series("mB", s))
    assert sig["current_regime"] == "turbulent"
    assert sig["news_driven"] is True


def test_signal_schema_fields():
    s = _two_regime_series(seed=3)
    sig = hmm._build_regime_signal(hmm.analyze_series("mC", s), kind="pm_market")
    assert sig["models_used"] == ["hmm"]
    assert sig["series_id"] == "mC"
    assert sig["series_kind"] == "pm_market"
    assert "transition_matrix" in sig["evidence"]
    assert "separation" in sig["evidence"]
    assert len(sig["failure_conditions"]) >= 3
    assert sig["data_sufficiency"] in ("low", "medium")
    assert 0 <= sig["confidence"] <= 90
    assert set(sig["regime_posterior"].keys()) <= {"calm", "turbulent", "normal"}


def test_determinism_same_input_same_output():
    s = _two_regime_series(seed=4)
    a = hmm.analyze_series("mD", s)
    b = hmm.analyze_series("mD", s)
    assert a["current_regime"] == b["current_regime"]
    assert a["transition_matrix"] == b["transition_matrix"]
    assert a["loglik"] == b["loglik"]


def test_low_separation_marked_not_confident():
    # 全程同方差（无 regime 结构）→ 方差分离不足 → regime_confident=False
    rng = np.random.default_rng(5)
    s = list(0.5 + np.cumsum(rng.normal(0, 0.01, 48)))
    st = hmm.analyze_series("uniform", s)
    if st is not None:
        sig = hmm._build_regime_signal(st)
        # 无明显双态结构时不应自信判定（separation 接近 1）
        if st["separation"] < hmm.SEPARATION_MIN:
            assert sig["regime_confident"] is False


def test_compute_writes_research_artifact(tmp_path, monkeypatch):
    monkeypatch.delenv("PA_SHADOW_DB", raising=False)
    data = tmp_path / "data"
    data.mkdir()
    s = _two_regime_series(seed=6)

    def _series(arr):
        return [{"ts": f"2026-06-0{1+i%9}T00:00:00", "yes_price": float(v),
                 "no_price": float(1 - v), "liquidity": 10000.0} for i, v in enumerate(arr)]

    hist = {"mA": _series(s), "flat": _series([0.5] * 48)}
    (data / "market_price_history.json").write_text(json.dumps(hist), encoding="utf-8")

    rep = hmm.compute(base_dir=tmp_path)
    assert rep["enforced"] is False
    assert rep["model"] == "hmm"
    assert rep["n_series_considered"] == 1            # flat 被护栏剔除
    assert (data / "regime_states.json").exists()
    saved = json.loads((data / "regime_states.json").read_text(encoding="utf-8"))
    assert saved["schema_version"] == hmm.SCHEMA_VERSION
    assert saved["regimes"][0]["models_used"] == ["hmm"]
