"""Phase 3f-loop — 协整闭环端到端归因测试（确定性，隔离影子库）。

验证真实模型端到端可学习：
  协整候选 → to_pipeline_signals(带 models_used) → put_signals(影子 signals.models_used)
  → 合成 postmortem(同 signal_uid) → model_effectiveness 在 by_model 下归因 "cointegration"。

不触网络/不跑 orchestrator 真实循环；用隔离 PA_DB_PATH + base_dir。
"""

import json
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from runtime import cointegration as ci
from runtime import datastore as ds
from runtime import model_effectiveness as me


def _synthetic_report():
    """造一个必过阈值的协整候选（含末点偏离），走真实 find_candidates 链路。"""
    rng = np.random.default_rng(7)
    b = 0.5 + 0.06 * np.sin(np.linspace(0, 6, 24)) + rng.normal(0, 1e-3, 24)
    a = 1.0 * b + rng.normal(0, 2e-3, 24)
    a[-1] += 0.06
    st = ci.analyze_pair("111", list(a), "222", list(b))
    assert st is not None and ci._is_candidate(st)
    return {"candidates": [ci._build_signal(st)]}


def test_to_pipeline_signals_carry_models_used():
    rep = _synthetic_report()
    meta = {"111": {"name": "Market A", "slug": "a", "yes_price": 0.52, "no_price": 0.48},
            "222": {"name": "Market B", "slug": "b", "yes_price": 0.50, "no_price": 0.50}}
    sigs = ci.to_pipeline_signals(rep, meta)
    assert len(sigs) == 2
    for s in sigs:
        assert s["models_used"] == ["cointegration"]
        assert s["source"] == "cointegration"
        assert s["data_sources"] and s["logic_chain"]      # Agent M 健全性
        assert s["direction"] in ("YES", "NO")
        assert s["position_size"] == 0.05


def test_end_to_end_attribution_under_by_model(tmp_path, monkeypatch):
    from runtime import _shadow

    # 隔离影子库：独立 db 文件 + 开 shadow + 重置缓存连接
    monkeypatch.setenv("PA_SHADOW_DB", "1")
    monkeypatch.setenv("PA_DB_PATH", str(tmp_path / "runtime.db"))
    monkeypatch.setattr(_shadow, "_CONN", None)
    (tmp_path / "data").mkdir()

    rep = _synthetic_report()
    meta = {"111": {"name": "Market A", "slug": "a", "yes_price": 0.52, "no_price": 0.48},
            "222": {"name": "Market B", "slug": "b", "yes_price": 0.50, "no_price": 0.50}}
    sigs = ci.to_pipeline_signals(rep, meta)

    # 1) 信号入库（经门面 → 影子 signals.models_used）
    ds.put_signals("cycleX", sigs, base_dir=tmp_path)

    # 2) 取一条信号，造它的「已平仓 + 已复盘」：postmortem.signal_uid 必须等于
    #    upsert_signals 计算的 signal_uid = uid(market_id, direction, generated_at, source)
    s0 = sigs[0]
    su = ds.uid(s0["market_id"], s0["direction"], s0.get("generated_at"), s0["source"])
    # 确认影子 signals 行确实带 models_used
    row = _shadow._rows("SELECT models_used FROM signals WHERE signal_uid=?", (su,))
    assert row and "cointegration" in (row[0]["models_used"] or "")

    pm = {
        "postmortem_uid": ds.uid("pos-loop-1"),
        "position_uid": "pos-loop-1",
        "canonical_market_id": s0["market_id"],
        "market_name": s0["market_name"], "direction": s0["direction"],
        "signal_uid": su,
        "hypothesis": "cointegration spread revert",
        "expected_edge": s0.get("expected_value"), "confidence": s0.get("confidence"),
        "entry_price": 0.5, "exit_price": 0.6, "realized_pnl": 100.0,
        "outcome": "win", "failure_reason": "盈利了结",
        "liquidity_issue": False, "timing_issue": False, "model_issue": False,
        "hypothesis_verdict": "confirmed", "source": "deterministic", "closed_at": "2026-06-05T00:00:00Z",
    }
    ds.append_postmortem(pm, base_dir=tmp_path)

    # 3) 聚合 → by_model 必须出现 cointegration，并归因这笔 win
    report = me.compute(base_dir=tmp_path)
    assert report["attribution_source"] == "shadow_join_signals"
    by_model = {e["key"]: e for e in report["by_model"]}
    assert "cointegration" in by_model, f"by_model={list(by_model)}"
    coint = by_model["cointegration"]
    assert coint["n_trades"] >= 1
    assert coint["n_win"] >= 1
