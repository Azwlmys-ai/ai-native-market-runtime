"""Phase 3f-loop — 受控端到端验证（真实 orchestrator 汇总 + 真实 executor dry_run）。

非破坏：全程隔离 base_dir + 隔离影子库；不触真实 data/、不联网、不下单。
证明：
  1. PA_COINT_SIGNALS=1 时，真实 Orchestrator._consolidate_signals_for_review() 把协整候选
     作为带 models_used 的 probe 信号合入真实 signals.json（并落影子 signals.models_used）。
  2. 门控关（默认）时，同一路径不注入任何协整信号——信号链路零变化。
  3. 真实 SignalExecutor 在 EXECUTOR_DRY_RUN=1 下处理该信号：status=dry_run、success=0（护栏不破）。
"""

import json
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def _seed_isolated(base: Path):
    """造隔离工作目录：合成价格历史(必出协整候选) + latest_data(两腿市场元信息)。"""
    data = base / "data"
    data.mkdir(parents=True, exist_ok=True)
    (base / "logs").mkdir(parents=True, exist_ok=True)

    rng = np.random.default_rng(7)
    b = 0.5 + 0.06 * np.sin(np.linspace(0, 6, 24)) + rng.normal(0, 1e-3, 24)
    a = 1.0 * b + rng.normal(0, 2e-3, 24)
    a[-1] += 0.06   # 末点把 spread 拉到 >2σ

    def series(arr):
        return [{"ts": f"2026-06-0{1 + i % 9}T00:00:00", "yes_price": float(v),
                 "no_price": float(round(1 - v, 6)), "liquidity": 50000.0}
                for i, v in enumerate(arr)]

    hist = {"111": series(a), "222": series(b), "flat": series([0.5] * 24)}
    (data / "market_price_history.json").write_text(json.dumps(hist), encoding="utf-8")

    latest = {"polymarket_markets": [
        {"id": "111", "slug": "market-a", "question": "Market A?",
         "outcomes": ["Yes", "No"], "outcome_prices": [float(a[-1]), float(round(1 - a[-1], 6))],
         "liquidity": 50000.0},
        {"id": "222", "slug": "market-b", "question": "Market B?",
         "outcomes": ["Yes", "No"], "outcome_prices": [float(b[-1]), float(round(1 - b[-1], 6))],
         "liquidity": 50000.0},
    ]}
    (data / "latest_data.json").write_text(json.dumps(latest), encoding="utf-8")
    return data


def _read_signals(data: Path):
    p = data / "signals.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else []


def test_gate_on_injects_models_used_probe_into_real_consolidation(tmp_path, monkeypatch):
    from runtime import _shadow
    import orchestrator as orch_mod

    monkeypatch.setenv("PA_COINT_SIGNALS", "1")
    monkeypatch.setenv("PA_SHADOW_DB", "1")
    monkeypatch.setenv("PA_DB_PATH", str(tmp_path / "runtime.db"))
    monkeypatch.setattr(_shadow, "_CONN", None)

    data = _seed_isolated(tmp_path)
    orch = orch_mod.Orchestrator(base_dir=tmp_path)
    orch._consolidate_signals_for_review()      # 真实方法、真实桥

    sigs = _read_signals(data)
    coint = [s for s in sigs if s.get("source") == "cointegration"]
    assert coint, "门控开时应注入协整 probe 信号"
    for s in coint:
        assert s["models_used"] == ["cointegration"]
        assert s["data_sources"] and s["logic_chain"]     # Agent M 健全性
        assert s["direction"] in ("YES", "NO")
        # 价格已从 latest_data 富化（非降级 0.5 占位）
        assert s["price"] != 0.5 or s["market_slug"] in ("market-a", "market-b")

    # 影子 signals 行带上 models_used
    rows = _shadow._rows(
        "SELECT models_used FROM signals WHERE source='cointegration'")
    assert rows and all("cointegration" in (r["models_used"] or "") for r in rows)


def test_gate_off_injects_nothing(tmp_path, monkeypatch):
    import orchestrator as orch_mod

    monkeypatch.delenv("PA_COINT_SIGNALS", raising=False)   # 默认关
    monkeypatch.delenv("PA_SHADOW_DB", raising=False)
    data = _seed_isolated(tmp_path)
    orch = orch_mod.Orchestrator(base_dir=tmp_path)
    orch._consolidate_signals_for_review()

    sigs = _read_signals(data)
    assert [s for s in sigs if s.get("source") == "cointegration"] == []


def test_real_executor_dry_run_keeps_success_zero(tmp_path, monkeypatch):
    """真实 executor 处理协整 probe 信号：dry_run、success=0。"""
    from executors.signal_executor import SignalExecutor
    from runtime import cointegration as ci

    monkeypatch.setenv("EXECUTOR_DRY_RUN", "1")
    monkeypatch.delenv("PA_SHADOW_DB", raising=False)
    data = tmp_path / "data"
    data.mkdir(parents=True, exist_ok=True)

    # 直接造一条协整 probe 信号作为 approved_signals
    rng = np.random.default_rng(7)
    b = 0.5 + 0.06 * np.sin(np.linspace(0, 6, 24)) + rng.normal(0, 1e-3, 24)
    a = 1.0 * b + rng.normal(0, 2e-3, 24)
    a[-1] += 0.06
    st = ci.analyze_pair("111", list(a), "222", list(b))
    report = {"candidates": [ci._build_signal(st)]}
    meta = {"111": {"name": "Market A", "slug": "market-a", "yes_price": 0.55, "no_price": 0.45},
            "222": {"name": "Market B", "slug": "market-b", "yes_price": 0.50, "no_price": 0.50}}
    sigs = ci.to_pipeline_signals(report, meta)
    assert sigs
    (data / "approved_signals.json").write_text(json.dumps(sigs), encoding="utf-8")

    ex = SignalExecutor(base_dir=str(tmp_path))
    ex.run()

    out = json.loads((data / "execution_results.json").read_text(encoding="utf-8"))
    assert out["success"] == 0, "dry_run 绝不计入 success"
    assert out["dry_run"] >= 1
    assert all(r["status"] == "dry_run" for r in out["results"])
