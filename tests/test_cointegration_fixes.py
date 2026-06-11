"""Phase 3f-loop 修复项单测：
  Fix1 配对原子完整性（enforce_pair_integrity）
  Fix2 edge 单位校准（expected_value=收益率 + 方向感知 realized_return + 无量纲 edge_realization）
"""

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from runtime import cointegration as ci
from runtime import model_effectiveness as me


def _pair_signals():
    rng = np.random.default_rng(7)
    b = 0.5 + 0.06 * np.sin(np.linspace(0, 6, 24)) + rng.normal(0, 1e-3, 24)
    a = 1.0 * b + rng.normal(0, 2e-3, 24)
    a[-1] += 0.06
    st = ci.analyze_pair("111", list(a), "222", list(b))
    rep = {"candidates": [ci._build_signal(st)]}
    meta = {"111": {"name": "A", "slug": "a", "yes_price": 0.55, "no_price": 0.45},
            "222": {"name": "B", "slug": "b", "yes_price": 0.50, "no_price": 0.50}}
    return ci.to_pipeline_signals(rep, meta)


# ---------- Fix1 ----------

def test_legs_carry_pair_metadata():
    sigs = _pair_signals()
    assert len(sigs) == 2
    a, b = sigs
    assert a["pair_id"] == b["pair_id"]
    assert a["pair_partner_market"] == b["market_id"]
    assert b["pair_partner_market"] == a["market_id"]


def test_full_pair_survives_integrity():
    sigs = _pair_signals()
    kept, dropped = ci.enforce_pair_integrity(sigs)
    assert len(kept) == 2 and dropped == []


def test_orphan_leg_dropped():
    sigs = _pair_signals()
    # 模拟 Agent M 只批准了一腿
    approved_one_leg = [sigs[0]]
    kept, dropped = ci.enforce_pair_integrity(approved_one_leg)
    assert kept == []                 # 裸腿被丢弃
    assert len(dropped) == 1


def test_non_cointegration_signals_pass_through():
    other = {"market_id": "999", "direction": "YES", "source": "agent_b"}  # 无 pair_id
    sigs = _pair_signals() + [other]
    kept, dropped = ci.enforce_pair_integrity(sigs)
    assert other in kept
    assert len([s for s in kept if s.get("source") == "agent_b"]) == 1


# ---------- Fix2 ----------

def test_expected_value_is_return_fraction():
    sigs = _pair_signals()
    for s in sigs:
        ev = s["expected_value"]
        assert ev is not None and 0 <= ev <= 1.0      # 无量纲收益率，封顶 1.0
        assert "expected_spread_move" in s["evidence"]  # 原价差单位保留在 evidence


def test_realized_return_direction_aware():
    # NO 仓位在 yes 价下跌时盈利 → realized_return 取反为正
    no_win = {"direction": "NO", "entry_price": 0.82, "exit_price": 0.69, "realized_pnl": 100.0}
    rr = me._realized_return(no_win)
    assert rr is not None and rr > 0                  # (0.69-0.82)/0.82 = -0.16 → 取反 +0.16
    yes_win = {"direction": "YES", "entry_price": 0.50, "exit_price": 0.60, "realized_pnl": 100.0}
    assert me._realized_return(yes_win) > 0           # (0.60-0.50)/0.50 = +0.20
    assert me._realized_return({"direction": "NO", "entry_price": None, "exit_price": 0.5}) is None


def test_edge_realization_is_dimensionless_ratio():
    # 预期收益率 0.10、实现收益率 0.20 → edge_realization=2.0（同量纲比值）
    recs = [{"outcome": "win", "realized_pnl": 50.0, "expected_edge": 0.10,
             "direction": "YES", "entry_price": 0.50, "exit_price": 0.60,
             "closed_at": "2026-06-01", "hypothesis_verdict": "confirmed"} for _ in range(3)]
    e = me._aggregate_scope(recs, "rule")[0]
    assert e["avg_realized_return"] == 0.2
    assert e["avg_expected_edge"] == 0.1
    assert e["edge_realization"] == 2.0
