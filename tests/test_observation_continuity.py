"""Phase 3e observation continuity — incremental export and gate tests."""

import json
import os
import shutil
import time
from pathlib import Path

import pytest

from runtime.observation_backfill_gate import is_enabled, maybe_run
from runtime.observation_continuity import (
    DxyValidationError,
    export_funding_incremental,
    export_pm_crypto_tape_incremental,
    load_and_validate_dxy,
    run_phase3e,
    validate_dxy_row,
    _tape_dedup_key,
)

ROOT = Path(__file__).resolve().parent.parent


def _seed_pm_fixtures(tmp_path: Path) -> None:
    data = tmp_path / "data"
    hist = data / "historical"
    hist.mkdir(parents=True)
    mph = {
        "540844": [
            {"ts": "2026-06-03T08:00:00", "yes_price": 0.49, "no_price": 0.51, "liquidity": 1000},
            {"ts": "2026-06-04T08:00:00", "yes_price": 0.50, "no_price": 0.50, "liquidity": 1100},
        ],
    }
    (data / "market_price_history.json").write_text(json.dumps(mph))
    import sqlite3

    conn = sqlite3.connect(data / "runtime.db")
    conn.execute(
        "CREATE TABLE market_prices (market_id TEXT, slug TEXT, ts TEXT, yes_price REAL, no_price REAL, liquidity REAL)"
    )
    conn.execute(
        "INSERT INTO market_prices VALUES ('540844','will-bitcoin-hit-1m-before-gta-vi','2026-06-03T08:00:00',0.49,0.51,1000)"
    )
    conn.execute(
        "INSERT INTO market_prices VALUES ('540844','will-bitcoin-hit-1m-before-gta-vi','2026-06-04T08:00:00',0.50,0.50,1100)"
    )
    conn.commit()
    conn.close()


def test_gate_disabled_by_default(monkeypatch):
    monkeypatch.delenv("PA_OBSERVATION_BACKFILL", raising=False)
    assert is_enabled() is False
    result = maybe_run(base_dir=ROOT)
    assert result["skipped"] is True


def test_gate_disabled_does_not_write_observation_files(tmp_path, monkeypatch):
    monkeypatch.delenv("PA_OBSERVATION_BACKFILL", raising=False)
    _seed_pm_fixtures(tmp_path)
    out = tmp_path / "data" / "historical" / "pm_crypto_price_tape.jsonl"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text('{"existing": true}\n')
    before = out.stat().st_mtime
    time.sleep(0.01)
    maybe_run(base_dir=tmp_path)
    assert out.stat().st_mtime == before


def test_pm_tape_incremental_dedup(tmp_path):
    _seed_pm_fixtures(tmp_path)
    s1 = export_pm_crypto_tape_incremental(tmp_path)
    assert s1["appended_rows"] == 2
    s2 = export_pm_crypto_tape_incremental(tmp_path)
    assert s2["appended_rows"] == 0
    assert s2["total_rows"] == 2


def test_pm_tape_marks_low_information(tmp_path):
    data = tmp_path / "data"
    hist = data / "historical"
    hist.mkdir(parents=True)
    mph = {
        "540844": [
            {"ts": "2026-06-03T08:00:00", "yes_price": 0.4925, "no_price": 0.5075, "liquidity": 1000},
            {"ts": "2026-06-04T08:00:00", "yes_price": 0.4925, "no_price": 0.5075, "liquidity": 1000},
        ],
    }
    (data / "market_price_history.json").write_text(json.dumps(mph))
    import sqlite3

    conn = sqlite3.connect(data / "runtime.db")
    conn.execute(
        "CREATE TABLE market_prices (market_id TEXT, slug TEXT, ts TEXT, yes_price REAL, no_price REAL, liquidity REAL)"
    )
    conn.execute(
        "INSERT INTO market_prices VALUES ('540844','will-bitcoin-hit-1m-before-gta-vi','2026-06-03T08:00:00',0.4925,0.5075,1000)"
    )
    conn.commit()
    conn.close()
    export_pm_crypto_tape_incremental(tmp_path)
    row = json.loads((hist / "pm_crypto_price_tape.jsonl").read_text().strip().splitlines()[0])
    assert row["low_information"] is True
    assert row["live"] is True
    assert row["observation_only"] is True


def test_funding_sol_missing_not_fabricated(tmp_path):
    hist = tmp_path / "data" / "historical"
    hist.mkdir(parents=True)
    for name in (
        "okx_BTC_USDT_SWAP_funding_rate_march_2026.json",
        "okx_ETH_USDT_SWAP_funding_rate_march_2026.json",
    ):
        src = ROOT / "data" / "historical" / name
        if src.exists():
            shutil.copy(src, hist / name)
    stats = export_funding_incremental(tmp_path)
    assert any(m.get("symbol") == "SOL" for m in stats.get("missing_symbols", []))
    symbols = set()
    out = hist / "funding_rates.jsonl"
    if out.exists():
        for line in out.read_text().strip().splitlines():
            symbols.add(json.loads(line)["symbol"])
    assert "SOL" not in symbols


def test_funding_live_rollup(tmp_path):
    data = tmp_path / "data"
    hist = data / "historical"
    hist.mkdir(parents=True)
    src = ROOT / "data" / "historical" / "okx_BTC_USDT_SWAP_funding_rate_march_2026.json"
    if src.exists():
        shutil.copy(src, hist / src.name)
    (data / "asset_price_history.json").write_text(json.dumps({
        "BTC_FUNDING": [
            {"ts": "2026-06-07T12:00:00", "price": 0.0001, "kind": "macro"},
        ],
    }))
    s1 = export_funding_incremental(tmp_path)
    s2 = export_funding_incremental(tmp_path)
    assert s2["appended_rows"] == 0


def test_dxy_missing_graceful(tmp_path):
    _, stats = load_and_validate_dxy(tmp_path)
    assert stats["status"] == "insufficient_data"


def test_dxy_validator_requires_source():
    with pytest.raises(DxyValidationError):
        validate_dxy_row({"date": "2026-01-01", "close": 100.0, "observation_only": True})
    validate_dxy_row({
        "date": "2026-01-01",
        "close": 100.0,
        "source": "manual",
        "observation_only": True,
    })


def test_phase3e_no_trading_writes(tmp_path, monkeypatch):
    monkeypatch.setenv("PA_OBSERVATION_BACKFILL", "1")
    _seed_pm_fixtures(tmp_path)
    signals = tmp_path / "data" / "signals.json"
    review = tmp_path / "data" / "review_results.json"
    execution = tmp_path / "data" / "execution_results.json"
    signals.write_text("[]")
    review.write_text("{}")
    execution.write_text("{}")
    sig_m = signals.stat().st_mtime
    rev_m = review.stat().st_mtime
    ex_m = execution.stat().st_mtime
    maybe_run(base_dir=tmp_path)
    assert signals.stat().st_mtime == sig_m
    assert review.stat().st_mtime == rev_m
    assert execution.stat().st_mtime == ex_m


def test_host_loop_has_observation_gate_comment():
    script = (ROOT / "scripts" / "run_host_loop.sh").read_text()
    assert "PA_OBSERVATION_BACKFILL" in script
    assert "# export PA_OBSERVATION_BACKFILL=1" in script
