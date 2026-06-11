"""Phase 3f-x — 跨资产协整单测（Polymarket × 外部资产）。

验证：外部资产价格历史 roundtrip、跨资产配对（复用 analyze_pair）、
pm_asset 候选只发可成交 PM 腿（资产为外生锚）、单腿无 pair_id 且过完整性门。
"""

import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from runtime import cointegration as ci
from runtime import datastore as ds
from runtime import price_history as ph


def _coint_pm_btc():
    """构造真协整对：BTC 走 sin，pm 线性依赖 BTC + 白噪声 → spread 平稳(AR1 φ<1)；末点拉偏制造 |z|>2。"""
    rng = np.random.default_rng(3)
    btc = 67000 + 800 * np.sin(np.linspace(0, 6, 24)) + rng.normal(0, 5, 24)
    pm = 0.5 + 0.08 * ((btc - 67000) / 800.0) + rng.normal(0, 2e-3, 24)  # pm 线性于 BTC + 白噪声
    pm = pm.copy()
    pm[-1] += 0.03   # 末点把 spread 拉到 >2σ（白噪声 spread → 平稳）
    return pm, btc


def test_asset_history_roundtrip(tmp_path):
    (tmp_path / "data").mkdir()
    pts = [{"symbol": "BTC", "ts": "2026-06-01T00:00:00", "price": 67000.0, "kind": "crypto"},
           {"symbol": "BTC", "ts": "2026-06-01T01:00:00", "price": 67100.0, "kind": "crypto"}]
    ds.record_asset_prices(pts, base_dir=tmp_path)
    hist = ph.load_asset_history(tmp_path)
    assert "BTC" in hist
    assert ph.asset_series_for(hist, "BTC") == [67000.0, 67100.0]


def test_cross_asset_candidate_found(tmp_path):
    data = tmp_path / "data"
    data.mkdir()
    pm, btc = _coint_pm_btc()        # pm in [0,1]，BTC ~6.7万（量纲差异由 beta 吸收）

    def pm_series(arr):
        return [{"ts": f"2026-06-0{1+i%9}T00:00:00", "yes_price": float(v),
                 "no_price": float(round(1 - v, 6)), "liquidity": 50000.0} for i, v in enumerate(arr)]

    json.dump({"540817": pm_series(pm)}, open(data / "market_price_history.json", "w"))
    ds.record_asset_prices(
        [{"symbol": "BTC", "ts": f"2026-06-0{1+i%9}T00:00:00", "price": float(v), "kind": "crypto"}
         for i, v in enumerate(btc)], base_dir=tmp_path)

    res = ci.find_cross_asset_candidates(tmp_path)
    assert res["n_pm_markets"] == 1 and res["n_assets"] == 1
    assert res["n_candidates"] >= 1
    c = res["candidates"][0]
    assert c["pair_type"] == "pm_asset"
    assert c["anchor_asset"] == "BTC"
    assert c["source_markets"] == ["540817", "BTC"]
    # 两腿：pm 可成交、资产不可成交
    roles = {l["role"]: l.get("tradeable", True) for l in c["legs"]}
    assert roles["pm"] is True and roles["anchor"] is False


def test_cross_asset_bridge_emits_only_pm_leg(tmp_path):
    pm, btc = _coint_pm_btc()
    st = ci.analyze_pair("540817", list(pm), "BTC", list(btc))
    assert st is not None
    cand = ci._build_cross_asset_signal(st, "540817", "BTC", "crypto")
    report = {"candidates": [cand]}
    meta = {"540817": {"name": "M", "slug": "m", "yes_price": 0.58, "no_price": 0.42}}

    sigs = ci.to_pipeline_signals(report, meta)
    assert len(sigs) == 1                       # 只发 PM 腿，资产锚不发
    s = sigs[0]
    assert s["market_id"] == "540817"
    assert s["models_used"] == ["cointegration"]
    assert s["pair_type"] == "pm_asset"
    assert s["anchor_asset"] == "BTC"
    assert s["pair_id"] is None                 # 单腿无配对完整性约束
    assert "BTC" in s["source_markets"]

    # 单腿 pm_asset 信号应原样通过配对完整性门（无 pair_id → others）
    kept, dropped = ci.enforce_pair_integrity(sigs)
    assert kept == sigs and dropped == []
