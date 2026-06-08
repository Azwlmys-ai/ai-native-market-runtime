"""Phase 3c model sandbox snapshot gate tests."""

import json
import os
import shutil
import time
from pathlib import Path

import pytest

from runtime.model_sandbox_snapshot import is_enabled, maybe_refresh

ROOT = Path(__file__).resolve().parent.parent


def test_snapshot_disabled_by_default(monkeypatch):
    monkeypatch.delenv("PA_MODEL_SANDBOX_SNAPSHOT", raising=False)
    assert is_enabled() is False
    result = maybe_refresh(base_dir=ROOT)
    assert result["skipped"] is True
    assert result["enabled"] is False


def test_snapshot_enabled_writes_only_research(tmp_path, monkeypatch):
    monkeypatch.setenv("PA_MODEL_SANDBOX_SNAPSHOT", "1")
    data = tmp_path / "data"
    hist = data / "historical"
    hist.mkdir(parents=True)
    research = tmp_path / "research"
    research.mkdir(parents=True)

    okx_src = ROOT / "data" / "historical" / "okx_klines_march_april_may_2026.json"
    if okx_src.exists():
        shutil.copy(okx_src, hist / okx_src.name)
    for name in (
        "okx_BTC_USDT_SWAP_funding_rate_march_2026.json",
        "okx_BTC_USDT_SWAP_funding_rate_april_2026.json",
    ):
        src = ROOT / "data" / "historical" / name
        if src.exists():
            shutil.copy(src, hist / name)

    signals = data / "signals.json"
    review = data / "review_results.json"
    signals.write_text("[]")
    review.write_text("{}")
    sig_mtime = signals.stat().st_mtime
    rev_mtime = review.stat().st_mtime

    result = maybe_refresh(base_dir=tmp_path)
    assert result["enabled"] is True
    assert result.get("ok") is True
    assert (tmp_path / "research" / "model_sandbox" / "garch_volatility_report.json").exists()
    assert signals.stat().st_mtime == sig_mtime
    assert review.stat().st_mtime == rev_mtime


def test_snapshot_failure_non_fatal(tmp_path, monkeypatch):
    monkeypatch.setenv("PA_MODEL_SANDBOX_SNAPSHOT", "1")

    def _boom(**_kwargs):
        raise RuntimeError("sandbox boom")

    monkeypatch.setattr("runtime.model_sandbox.compute", _boom)
    result = maybe_refresh(base_dir=tmp_path)
    assert result["enabled"] is True
    assert result.get("ok") is False
    assert "boom" in result.get("error", "")


def test_host_loop_env_default_off():
    script = (ROOT / "scripts" / "run_host_loop.sh").read_text()
    assert "PA_MODEL_SANDBOX_SNAPSHOT" in script
    assert "# export PA_MODEL_SANDBOX_SNAPSHOT=1" in script
    assert 'export PA_MODEL_SANDBOX_SNAPSHOT="${PA_MODEL_SANDBOX_SNAPSHOT:-1}"' not in script


def test_gap_reports_written(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "runtime.observation_gaps.HISTORY_MARKETS",
        tmp_path / "markets",
    )
    monkeypatch.setattr(
        "runtime.observation_gaps.REPLAY_PATH",
        tmp_path / "replay.jsonl",
    )
    from runtime.observation_gaps import build_gap_reports

    (tmp_path / "data" / "historical").mkdir(parents=True)
    (tmp_path / "research").mkdir(parents=True)
    rep = build_gap_reports(base_dir=tmp_path, date_suffix="test")
    assert Path(rep["output_paths"]["funding_md"]).exists()
    assert Path(rep["output_paths"]["pm_md"]).exists()
    assert Path(rep["output_paths"]["dxy_md"]).exists()
