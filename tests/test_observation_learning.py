"""Phase 3 observation learning — read-only subscription tests."""

import json
import shutil
import time
from pathlib import Path

import pytest

from runtime.observation_catalog import CatalogError, ObservationCatalog
from runtime.observation_learning import compute, parse_cross_market_report

ROOT = Path(__file__).resolve().parent.parent


def test_parse_cross_market_table():
    md = """
| Pair | n | Pearson (lag=0) | Spearman | Best lag | |r| lag | Confidence |
|------|---|-----------------|----------|----------|---------|------------|
| BTC ↔ ETH | 1617 | 0.84 | 0.82 | 0 | 0.84 | high |
| DXY ↔ BTC | 0 | None | None | None | None | insufficient_data |
"""
    pairs = parse_cross_market_report(md)
    assert len(pairs) == 2
    assert pairs[0]["pair"] == "BTC ↔ ETH"
    assert pairs[0]["sample_size"] == 1617
    assert pairs[1]["confidence"] == "insufficient_data"


def test_compute_writes_only_research_outputs(tmp_path):
    research = tmp_path / "research"
    data = tmp_path / "data"
    research.mkdir()
    data.mkdir()

    shutil.copy(ROOT / "research" / "okx_observation_summary.json", research / "okx_observation_summary.json")
    shutil.copy(ROOT / "research" / "us_etf_observation_summary.json", research / "us_etf_observation_summary.json")
    shutil.copy(ROOT / "research" / "cross_market_discovery_report.md", research / "cross_market_discovery_report.md")
    if (ROOT / "data" / "market_intelligence.json").exists():
        shutil.copy(ROOT / "data" / "market_intelligence.json", data / "market_intelligence.json")
    if (ROOT / "data" / "runtime.db").exists():
        shutil.copy(ROOT / "data" / "runtime.db", data / "runtime.db")

    signals = data / "signals.json"
    review = data / "review_results.json"
    signals.write_text("[]")
    review.write_text("{}")
    sig_mtime = signals.stat().st_mtime
    rev_mtime = review.stat().st_mtime

    snap = compute(base_dir=tmp_path, date_suffix="test")

    assert (research / "observation_learning_snapshot_test.json").exists()
    assert (research / "observation_learning_snapshot_test.md").exists()
    assert signals.stat().st_mtime == sig_mtime
    assert review.stat().st_mtime == rev_mtime
    assert snap.get("forbidden", {}).get("write_signals") is True
    assert "signals" not in str(snap.get("output_paths", {}))


def test_denylist_experience_not_readable_via_catalog():
    cat = ObservationCatalog()
    with pytest.raises(CatalogError):
        cat.get_entry("okx.experience.review")


def test_catalog_does_not_write_source_projects(tmp_path):
    cat = ObservationCatalog()
    entry = cat.get_entry("okx.trades.weekly")
    paths = entry.resolve_paths()
    assert paths
    before = paths[0].stat().st_mtime
    time.sleep(0.01)
    rows = cat.read_jsonl("okx.trades.weekly", limit=1)
    assert rows
    assert paths[0].stat().st_mtime == before


def test_snapshot_forbids_experience_fields_in_output():
    snap_path = ROOT / "research" / "observation_learning_snapshot_20260607.json"
    if not snap_path.exists():
        compute(base_dir=ROOT, date_suffix="20260607")
    snap = json.loads(snap_path.read_text())
    text = json.dumps(snap)
    assert "boost_rule" not in text
    assert "learned_rules" not in text
    assert snap["forbidden"]["experience_import"] is True
