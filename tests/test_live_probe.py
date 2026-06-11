"""Phase 4 live probe gates — 门控、风控、止损优先。"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from runtime import live_probe as lp


def _probe_signal(**kw):
    base = {
        "market_id": "123",
        "source": "agent_b",
        "grade": "paper_probe",
        "position_size": 0.02,
        "direction": "YES",
    }
    base.update(kw)
    return base


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for k in list(os.environ):
        if k.startswith("PA_LIVE_") or k == "EXECUTOR_DRY_RUN":
            monkeypatch.delenv(k, raising=False)
    monkeypatch.delenv("EXECUTOR_DRY_RUN", raising=False)


def test_live_disabled_by_default():
    assert not lp.live_enabled()
    assert not lp.gates()["live_probe"]


def test_live_requires_probe_flag_and_no_dry_run(monkeypatch):
    assert not lp.live_enabled()
    monkeypatch.setenv("PA_LIVE_PROBE", "1")
    assert lp.live_enabled()
    monkeypatch.setenv("EXECUTOR_DRY_RUN", "1")
    assert not lp.live_enabled()


def test_is_probe_signal_variants():
    assert lp.is_probe_signal(_probe_signal())
    assert lp.is_probe_signal(_probe_signal(grade="approve", probe=True))
    assert lp.is_probe_signal(_probe_signal(grade="approve", tier="exploration"))
    assert lp.is_probe_signal({"source": "cointegration", "position_size": 0.05})
    assert not lp.is_probe_signal(_probe_signal(grade="approve", probe=False, tier="research"))


def test_cap_order_usd(monkeypatch):
    monkeypatch.setenv("PA_LIVE_PROBE_MAX_USD", "25")
    monkeypatch.setenv("PA_LIVE_PROBE_ACCOUNT", "10000")
    cfg = lp.gates()
    sig, usd = lp.cap_signal_amount(_probe_signal(position_size=0.5), cfg)
    assert usd == 25.0
    assert sig["position_size"] == pytest.approx(0.0025)


def test_filter_max_per_cycle(tmp_path, monkeypatch):
    monkeypatch.setenv("PA_LIVE_PROBE", "1")
    monkeypatch.setenv("PA_LIVE_PROBE_MAX_PER_CYCLE", "1")
    monkeypatch.setenv("PA_LIVE_PROBE_MAX_USD", "25")
    monkeypatch.delenv("EXECUTOR_DRY_RUN", raising=False)
    monkeypatch.setenv("PA_LIVE_RISK_ENFORCE", "0")

    signals = [_probe_signal(market_id="1"), _probe_signal(market_id="2")]
    allowed, audit = lp.filter_signals_for_live(signals, base_dir=tmp_path)
    assert len(allowed) == 1
    assert len(audit) == 2
    assert audit[1]["reason"] == "max_per_cycle"


def test_risk_snapshot_blocks(tmp_path, monkeypatch):
    monkeypatch.setenv("PA_LIVE_PROBE", "1")
    monkeypatch.setenv("PA_LIVE_RISK_ENFORCE", "1")
    monkeypatch.delenv("EXECUTOR_DRY_RUN", raising=False)
    (tmp_path / "data").mkdir(parents=True)
    (tmp_path / "data" / "risk_snapshot.json").write_text(
        json.dumps({"exposure": {"violations": [{"type": "total_exposure"}]}}),
        encoding="utf-8",
    )
    ok, reason, _, _ = lp.pre_trade_check(_probe_signal(), base_dir=tmp_path)
    assert not ok
    assert "violations" in reason


def test_daily_loss_writes_stop_trading(tmp_path, monkeypatch):
    monkeypatch.setenv("PA_LIVE_PROBE", "1")
    monkeypatch.setenv("PA_LIVE_PROBE_MAX_DAILY_LOSS_USD", "10")
    (tmp_path / "data").mkdir(parents=True)
    lp.save_state({"day": lp._today_utc(), "daily_realized_pnl": 0}, tmp_path)
    lp.record_live_sell_pnl(-12.0, base_dir=tmp_path)
    assert (tmp_path / "data" / "STOP_TRADING").exists()


def test_stop_loss_sell_allowed_under_stop_trading(monkeypatch):
    monkeypatch.delenv("EXECUTOR_DRY_RUN", raising=False)
    urgent = {"priority": "urgent", "reason": "stop_loss"}
    medium = {"priority": "medium", "reason": "take_profit"}
    assert lp.should_allow_live_sell(urgent, stop_trading_active=True)
    assert not lp.should_allow_live_sell(medium, stop_trading_active=True)


def test_signal_executor_blocks_without_live_gate(tmp_path, monkeypatch):
    from executors.signal_executor import SignalExecutor

    monkeypatch.delenv("EXECUTOR_DRY_RUN", raising=False)
    monkeypatch.delenv("PA_LIVE_PROBE", raising=False)
    (tmp_path / "data").mkdir(parents=True)
    ex = SignalExecutor(base_dir=tmp_path)
    r = ex.execute_trade(_probe_signal())
    assert r["status"] == "blocked_no_live_gate"
