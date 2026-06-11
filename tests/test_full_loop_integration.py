"""全环路集成验收（固化版）。

复刻 orchestrator 周期末的真实研究/学习链路（同顺序、同 compute/generate 入口），
在隔离 base_dir + 隔离影子库 + 合成数据上跑一遍，断言：
  * 9 步全部无异常执行；
  * 7 个研究/学习 fact-source json 全部落盘 + 影子表可查；
  * model_effectiveness.by_model 含真实模型 cointegration（闭环归因）；
  * 跨模型依赖成立（cointegration→position_sizing、postmortem→regime/有效性）；
  * 全部产物 enforced=False、互不干扰。

非破坏：不触真实 data/、不联网、不下单。numpy-only。
"""

import json
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def _pm_series(arr):
    return [{"ts": f"2026-06-{1 + i // 24:02d}T{i % 24:02d}:00:00",
             "yes_price": float(min(0.98, max(0.02, v))),
             "no_price": float(min(0.98, max(0.02, 1 - v))), "liquidity": 50000.0}
            for i, v in enumerate(arr)]


def _seed(base, ds):
    """合成数据：触发协整(含跨资产)/regime/garch/sizing + 复盘喂 effectiveness。"""
    data = base / "data"
    data.mkdir(parents=True, exist_ok=True)
    (base / "logs").mkdir(parents=True, exist_ok=True)

    rng = np.random.default_rng(11)
    N = 40
    btc = 67000 + 900 * np.sin(np.linspace(0, 7, N)) + rng.normal(0, 8, N)
    pm_coint = 0.5 + 0.08 * ((btc - 67000) / 900.0) + rng.normal(0, 2e-3, N)
    pm_coint[-1] += 0.04
    pm_regime = np.concatenate([0.5 + rng.normal(0, 0.004, N // 2),
                                0.5 + rng.normal(0, 0.05, N - N // 2)])
    pm_partner = 1.0 * pm_coint + rng.normal(0, 2e-3, N)

    json.dump({"540817": _pm_series(pm_coint), "540818": _pm_series(pm_partner),
               "553829": _pm_series(pm_regime)},
              open(data / "market_price_history.json", "w"))
    ds.record_asset_prices(
        [{"symbol": "BTC", "ts": f"2026-06-{1 + i // 24:02d}T{i % 24:02d}:00:00",
          "price": float(v), "kind": "crypto"} for i, v in enumerate(btc)], base_dir=base)

    sigs = [{"market_id": "540817", "direction": "NO", "source": "cointegration",
             "generated_at": "2026-06-09T00:00:00Z", "price": 0.55, "confidence": 80,
             "expected_value": 0.07, "models_used": ["cointegration"],
             "learned_rule_match": "mid_range_BTC", "data_sources": ["x"], "logic_chain": ["y"]},
            {"market_id": "553829", "direction": "YES", "source": "agent_b",
             "generated_at": "2026-06-09T00:00:00Z", "price": 0.50, "confidence": 75,
             "expected_value": 0.05, "models_used": [],
             "learned_rule_match": "mid_range_NHL", "data_sources": ["x"], "logic_chain": ["y"]}]
    ds.put_signals("cycleV", sigs, base_dir=base)

    for s, (en, ex, pnl, oc) in zip(sigs, [(0.55, 0.45, 120.0, "win"), (0.50, 0.58, -40.0, "loss")]):
        su = ds.uid(s["market_id"], s["direction"], s["generated_at"], s["source"])
        ds.append_postmortem({
            "postmortem_uid": ds.uid("pos", s["market_id"]), "position_uid": "pos_" + s["market_id"],
            "canonical_market_id": s["market_id"], "market_name": s["market_id"],
            "direction": s["direction"], "signal_uid": su, "hypothesis": "h",
            "expected_edge": s["expected_value"], "confidence": s["confidence"],
            "entry_price": en, "exit_price": ex, "realized_pnl": pnl, "outcome": oc,
            "failure_reason": "-", "liquidity_issue": False, "timing_issue": False,
            "model_issue": False, "hypothesis_verdict": "confirmed" if oc == "win" else "refuted",
            "source": "deterministic", "closed_at": "2026-06-10T00:00:00Z"}, base_dir=base)


def test_full_cycle_end_chain_runs_and_produces_all_artifacts(tmp_path, monkeypatch):
    monkeypatch.setenv("PA_SHADOW_DB", "1")
    monkeypatch.setenv("PA_DB_PATH", str(tmp_path / "runtime.db"))
    from runtime import _shadow
    monkeypatch.setattr(_shadow, "_CONN", None)

    from runtime import datastore as ds
    _seed(tmp_path, ds)

    # 真实周期末顺序（= orchestrator 行 259-297）
    from runtime import (postmortem as _pm, model_effectiveness as _me, rule_weights as _rw,
                         cointegration as _coint, regime_hmm as _hmm,
                         regime_effectiveness as _re, garch as _garch, position_sizing as _ps)

    _pm.generate(base_dir=tmp_path)                 # 无新平仓 → generated=0，但必须无异常
    me_rep = _me.compute(base_dir=tmp_path)
    _rw.compute(base_dir=tmp_path)
    co_rep = _coint.compute(base_dir=tmp_path)
    hmm_rep = _hmm.compute(base_dir=tmp_path)
    re_rep = _re.compute(base_dir=tmp_path)
    ga_rep = _garch.compute(base_dir=tmp_path)
    ps_rep = _ps.compute(base_dir=tmp_path)

    data = tmp_path / "data"
    artifacts = ["model_effectiveness.json", "rule_effectiveness.json", "correlation_signals.json",
                 "regime_states.json", "regime_effectiveness.json", "volatility_states.json",
                 "sizing_suggestions.json"]
    # 7 个研究/学习产物全部落盘
    for a in artifacts:
        assert (data / a).exists(), f"missing fact-source artifact: {a}"

    # 影子表全部可查（不抛）
    assert _shadow.query_model_effectiveness() is not None
    assert _shadow.query_correlation_signals() is not None
    assert _shadow.query_regime_states() is not None
    assert _shadow.query_volatility_states() is not None
    assert _shadow.query_sizing_suggestions() is not None

    # 闭环归因：真实模型 cointegration 进 by_model
    by_model = {e["key"] for e in me_rep.get("by_model", [])}
    assert "cointegration" in by_model

    # 协整：含跨资产候选（BTC↔PM），全部 enforced=False
    assert co_rep["enforced"] is False
    assert co_rep["n_candidates"] >= 1
    assert co_rep.get("n_candidates_pm_asset", 0) >= 1

    # regime/garch/sizing 产物结构成立
    assert hmm_rep["enforced"] is False and hmm_rep["n_regimes"] >= 1
    assert re_rep["n_postmortems"] >= 2                      # 两笔复盘进入 regime 有效性
    assert ga_rep["enforced"] is False and ga_rep["n_states"] >= 1
    # 跨模型依赖：sizing 消费协整边×GARCH方差×regime
    assert ps_rep["enforced"] is False and ps_rep["n_suggestions"] >= 1
