"""Phase 3b model sandbox — read-only research tests."""

import json
import shutil
import time
from pathlib import Path

import pytest

from runtime.model_sandbox import (
    compute,
    load_crypto_series,
    run_cointegration_research,
    run_garch_research,
    run_regime_research,
)
from runtime.observation_catalog import CatalogError, ObservationCatalog

ROOT = Path(__file__).resolve().parent.parent


def _seed_sandbox_fixtures(tmp_path: Path) -> None:
    data = tmp_path / "data"
    data.mkdir(parents=True, exist_ok=True)
    hist = data / "historical"
    hist.mkdir(parents=True, exist_ok=True)
    research = tmp_path / "research"
    research.mkdir(parents=True, exist_ok=True)

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

    for name in ("okx_observation_summary.json", "us_etf_observation_summary.json"):
        src = ROOT / "research" / name
        if src.exists():
            shutil.copy(src, research / name)

    if (ROOT / "data" / "runtime.db").exists():
        shutil.copy(ROOT / "data" / "runtime.db", data / "runtime.db")


def test_compute_writes_only_research_model_sandbox(tmp_path):
    _seed_sandbox_fixtures(tmp_path)
    signals = tmp_path / "data" / "signals.json"
    review = tmp_path / "data" / "review_results.json"
    corr = tmp_path / "data" / "correlation_signals.json"
    signals.write_text("[]")
    review.write_text("{}")
    corr.write_text("{}")
    sig_mtime = signals.stat().st_mtime
    rev_mtime = review.stat().st_mtime
    corr_mtime = corr.stat().st_mtime

    result = compute(base_dir=tmp_path)
    out = tmp_path / "research" / "model_sandbox"

    assert (out / "garch_volatility_report.json").exists()
    assert (out / "garch_volatility_report.md").exists()
    assert (out / "regime_hmm_report.json").exists()
    assert (out / "regime_hmm_report.md").exists()
    assert (out / "cointegration_report.json").exists()
    assert (out / "cointegration_report.md").exists()
    assert signals.stat().st_mtime == sig_mtime
    assert review.stat().st_mtime == rev_mtime
    assert corr.stat().st_mtime == corr_mtime
    assert result["summary"]["forbidden"]["write_signals"] is True
    assert result["summary"]["forbidden"]["write_review_results"] is True


def test_insufficient_data_when_no_price_series(tmp_path, monkeypatch):
    research = tmp_path / "research"
    data = tmp_path / "data"
    research.mkdir(parents=True, exist_ok=True)
    data.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(
        "runtime.model_sandbox.HISTORY_MARKETS",
        tmp_path / "nonexistent_markets",
    )

    garch = run_garch_research(tmp_path)
    assert garch["n_insufficient"] == 3
    assert all(s["status"] == "insufficient_data" for s in garch["series"])

    regime = run_regime_research(tmp_path)
    assert regime["n_insufficient"] == 3

    coint = run_cointegration_research(tmp_path)
    assert coint["btc_eth_spread"]["status"] == "insufficient_data"


def test_garch_report_has_volatility_state_and_clustering_window(tmp_path):
    _seed_sandbox_fixtures(tmp_path)
    garch = run_garch_research(tmp_path)
    ok = [s for s in garch["series"] if s.get("status") == "ok"]
    if not ok:
        pytest.skip("no OKX klines fixture")
    row = ok[0]
    assert "volatility_state" in row
    assert "clustering_window_periods" in row
    assert "confidence" in row
    assert "sample_size" in row


def test_regime_report_has_four_regime_labels(tmp_path):
    _seed_sandbox_fixtures(tmp_path)
    regime = run_regime_research(tmp_path)
    assert regime["regime_labels"] == ["calm", "trend", "turbulent", "illiquid"]
    ok = [s for s in regime["series"] if s.get("status") == "ok"]
    if ok:
        assert ok[0]["current_regime"] in regime["regime_labels"]


def test_cointegration_no_trading_signal_flag(tmp_path):
    _seed_sandbox_fixtures(tmp_path)
    coint = run_cointegration_research(tmp_path)
    spread = coint["btc_eth_spread"]
    if spread.get("status") == "ok":
        assert spread.get("trading_signal") is False
        assert spread.get("note", "").startswith("observation_only")
    assert coint["forbidden"]["write_correlation_signals"] is True
    assert "funding_lag_by_symbol" in coint
    assert "funding_sample_sizes" in coint


def test_pca_deferred_without_etf_indicators(tmp_path):
    _seed_sandbox_fixtures(tmp_path)
    result = compute(base_dir=tmp_path)
    assert result["summary"]["models"]["pca"]["status"] == "deferred"


def test_denylist_experience_not_readable():
    cat = ObservationCatalog()
    with pytest.raises(CatalogError):
        cat.get_entry("okx.experience.review")


def test_load_crypto_series_readonly_no_mutation(tmp_path):
    _seed_sandbox_fixtures(tmp_path)
    okx = tmp_path / "data" / "historical" / "okx_klines_march_april_may_2026.json"
    if not okx.exists():
        pytest.skip("no okx fixture")
    before = okx.stat().st_mtime
    time.sleep(0.01)
    loaded = load_crypto_series(tmp_path, "BTC")
    assert loaded.get("sample_size", 0) > 0
    assert okx.stat().st_mtime == before


def test_sandbox_output_forbids_signal_fields():
    out = ROOT / "research" / "model_sandbox" / "garch_volatility_report.json"
    if not out.exists():
        compute(base_dir=ROOT)
    text = out.read_text()
    assert "boost_rule" not in text
    assert "learned_rules" not in text
    data = json.loads(text)
    assert data["forbidden"]["write_signals"] is True
