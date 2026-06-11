"""Phase 3d observation backfill tests — read-only sources, no trading writes."""

import json
import shutil
import time
from pathlib import Path

import pytest

from runtime.observation_backfill import (
    collect_funding_observations,
    collect_pm_crypto_live_tape,
    ensure_dxy_template,
    load_dxy_daily,
    run_phase3d,
    write_funding_rates_jsonl,
    write_pm_crypto_price_tape_jsonl,
)
from runtime.observation_catalog import CatalogError, ObservationCatalog

ROOT = Path(__file__).resolve().parent.parent


def _seed_funding_sources(tmp_path: Path) -> None:
    hist = tmp_path / "data" / "historical"
    hist.mkdir(parents=True)
    for name in (
        "okx_BTC_USDT_SWAP_funding_rate_march_2026.json",
        "okx_ETH_USDT_SWAP_funding_rate_march_2026.json",
    ):
        src = ROOT / "data" / "historical" / name
        if src.exists():
            shutil.copy(src, hist / name)


def test_funding_backfill_readonly_sources(tmp_path):
    _seed_funding_sources(tmp_path)
    src = tmp_path / "data" / "historical" / "okx_BTC_USDT_SWAP_funding_rate_march_2026.json"
    before = src.stat().st_mtime
    time.sleep(0.01)
    stats = write_funding_rates_jsonl(tmp_path)
    assert src.stat().st_mtime == before
    out = tmp_path / "data" / "historical" / "funding_rates.jsonl"
    assert out.exists()
    rows = [json.loads(l) for l in out.read_text().strip().splitlines()]
    assert rows
    assert all(r["observation_only"] is True for r in rows)
    assert all("timestamp" in r and "funding_rate" in r for r in rows)


def test_sol_missing_not_fabricated(tmp_path):
    _seed_funding_sources(tmp_path)
    _, stats = collect_funding_observations(tmp_path)
    missing = [m["symbol"] for m in stats.get("missing_symbols", [])]
    assert "SOL" in missing
    assert stats["symbols"]["SOL"]["status"] == "missing"
    out_stats = write_funding_rates_jsonl(tmp_path)
    assert "SOL" in [m["symbol"] for m in out_stats.get("missing_symbols", [])]
    symbols = {json.loads(l)["symbol"] for l in (tmp_path / "data/historical/funding_rates.jsonl").read_text().strip().splitlines()}
    assert "SOL" not in symbols


def test_pm_live_tape_excludes_sim_data(tmp_path):
    data = tmp_path / "data"
    hist = data / "historical"
    hist.mkdir(parents=True)
    # sim file must not appear in live tape
    sim = hist / "polymarket_extended_march_april_2026.json"
    sim.write_text(json.dumps([{"id": "btc_100k_april", "price_history": [{"yes_price": 0.5}]}]))
    mph = {
        "540844": [
            {"ts": "2026-06-03T08:00:00", "yes_price": 0.49, "no_price": 0.51, "liquidity": 1000},
            {"ts": "2026-06-04T08:00:00", "yes_price": 0.50, "no_price": 0.50, "liquidity": 1100},
        ],
    }
    (data / "market_price_history.json").write_text(json.dumps(mph))
    import sqlite3

    db = data / "runtime.db"
    conn = sqlite3.connect(db)
    conn.execute(
        "CREATE TABLE market_prices (market_id TEXT, slug TEXT, ts TEXT, yes_price REAL, no_price REAL, liquidity REAL)"
    )
    conn.execute(
        "INSERT INTO market_prices VALUES ('540844','will-bitcoin-hit-1m-before-gta-vi','2026-06-03',0.49,0.51,1000)"
    )
    conn.commit()
    conn.close()

    stats = write_pm_crypto_price_tape_jsonl(tmp_path)
    rows = [json.loads(l) for l in (hist / "pm_crypto_price_tape.jsonl").read_text().strip().splitlines()]
    assert len(rows) == 2
    assert all(r["live"] is True for r in rows)
    assert all(r["observation_only"] is True for r in rows)
    assert all("btc_100k_april" not in r.get("market_id", "") for r in rows)


def test_flat_price_marked_low_information(tmp_path):
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
        "INSERT INTO market_prices VALUES ('540844','will-bitcoin-hit-1m-before-gta-vi','2026-06-03',0.4925,0.5075,1000)"
    )
    conn.commit()
    conn.close()

    _, stats = collect_pm_crypto_live_tape(tmp_path)
    assert stats["markets"][0]["low_information"] is True
    write_pm_crypto_price_tape_jsonl(tmp_path)
    row = json.loads((hist / "pm_crypto_price_tape.jsonl").read_text().strip().splitlines()[0])
    assert row["low_information"] is True


def test_dxy_missing_insufficient_data(tmp_path):
    rep = ensure_dxy_template(tmp_path)
    assert rep["status"] == "insufficient_data"
    assert rep["live_exists"] is False
    assert (tmp_path / "data/historical/dxy_daily.jsonl.example").exists()
    assert (tmp_path / "research/dxy_manual_input_spec.md").exists()
    assert load_dxy_daily(tmp_path) == []


def test_phase3d_no_trading_writes(tmp_path):
    _seed_funding_sources(tmp_path)
    (tmp_path / "data").mkdir(exist_ok=True)
    signals = tmp_path / "data" / "signals.json"
    review = tmp_path / "data" / "review_results.json"
    signals.write_text("[]")
    review.write_text("{}")
    sig_m = signals.stat().st_mtime
    rev_m = review.stat().st_mtime
    run_phase3d(base_dir=tmp_path)
    assert signals.stat().st_mtime == sig_m
    assert review.stat().st_mtime == rev_m


def test_catalog_validates_funding_unified():
    from runtime.observation_catalog import validate_row

    row = {
        "timestamp": "2026-03-01T00:00:00",
        "exchange": "okx",
        "symbol": "BTC",
        "funding_rate": 0.0001,
        "source_file": "/tmp/okx_BTC.json",
        "observation_only": True,
    }
    validate_row("pm.local.funding.unified", row, None)
    # 按 resolve_paths 的**实存**判定（stat['exists'] 仅表示路径已解析），缺数据环境下不读：
    cat = ObservationCatalog()
    fpaths = cat.get_entry("pm.local.funding.unified").resolve_paths()
    if fpaths and any(p.exists() for p in fpaths):
        rows = cat.read_jsonl("pm.local.funding.unified", limit=2)
        assert rows[0]["observation_only"] is True


def test_catalog_rejects_sim_in_live_tape(tmp_path):
    cat = ObservationCatalog()
    bad = {
        "timestamp": "2026-06-01",
        "market_id": "btc_100k_april",
        "slug": "sim",
        "asset": "BTC",
        "outcome": "yes",
        "price": 0.5,
        "source": "sim",
        "observation_only": True,
        "live": False,
    }
    with pytest.raises(CatalogError):
        from runtime.observation_catalog import validate_row

        validate_row("pm.local.crypto_price_tape", bad, None)
