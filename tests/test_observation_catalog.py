"""Tests for runtime.observation_catalog — Phase 2 read-only loader."""

import json
from pathlib import Path

import pytest

from runtime.observation_catalog import (
    CatalogError,
    ObservationCatalog,
    is_experience_path,
    validate_row,
)

ROOT = Path(__file__).resolve().parent.parent


def _skip_if_absent(cat, catalog_id):
    """目录条目数据文件不可见（如外部 shared_intelligence 未挂载/不存在）时 skip，
    而非 FileNotFoundError——使套件在缺数据环境（含沙箱）下仍诚实通过。
    注：stat()['exists'] 仅表示路径已解析、不代表文件真在盘上，故按 resolve_paths 实存判定。"""
    try:
        paths = cat.get_entry(catalog_id).resolve_paths()
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"catalog resolve failed for {catalog_id}: {exc}")
    if not paths or not any(Path(p).exists() for p in paths):
        pytest.skip(f"catalog data absent for {catalog_id}")


def test_catalog_loads_allowlist():
    cat = ObservationCatalog()
    entries = cat.list_allowlist()
    ids = {e.catalog_id for e in entries}
    assert "okx.trades.weekly" in ids
    assert "okx.trade_memory.export" in ids
    assert "etf.trades.weekly" in ids


def test_sentinel_not_in_allowlist_values():
    cat = ObservationCatalog()
    for e in cat.list_allowlist():
        if e.path:
            assert "__SINGLE_PROVIDER_NO_FALLBACK__" not in str(e.path)


def test_denylist_blocks_experience_path():
    assert is_experience_path("/Users/libo/okx_perp_trader/research/lessons/weekly_lessons_2026.json")
    assert not is_experience_path("/Users/libo/shared_intelligence/trades/okx_weekly.jsonl")


def test_read_okx_weekly_schema():
    cat = ObservationCatalog()
    _skip_if_absent(cat, "okx.trades.weekly")
    rows = cat.read_jsonl("okx.trades.weekly", limit=3)
    assert len(rows) == 3
    assert rows[0]["source"] == "okx"
    assert "symbol" in rows[0]


def test_trade_record_validation_rejects_extra_fields():
    cat = ObservationCatalog()
    schema = cat.get_entry("okx.trades.weekly").schema_path
    if not schema or not Path(schema).exists():
        pytest.skip("trade_record schema file absent (env without shared_intelligence)")
    bad = {
        "source": "okx",
        "symbol": "BTC",
        "strategy": "x",
        "entry_time": "2026-01-01T00:00:00Z",
        "exit_time": "2026-01-01T01:00:00Z",
        "holding_minutes": 1,
        "session": "asia",
        "pnl_pct": 1.0,
        "win": True,
        "boost_rule": "illegal_experience",
    }
    with pytest.raises(CatalogError):
        validate_row("okx.trades.weekly", bad, schema)


def test_unknown_catalog_id_raises():
    cat = ObservationCatalog()
    with pytest.raises(CatalogError):
        cat.get_entry("okx.experience.review")


def test_stat_okx_trade_memory():
    cat = ObservationCatalog()
    st = cat.stat("okx.trade_memory.export")
    assert st["exists"] is True
    assert st["files"] == 1


def test_phase3d_catalog_ids_present():
    cat = ObservationCatalog()
    ids = {e.catalog_id for e in cat.list_allowlist()}
    assert "pm.local.funding.unified" in ids
    assert "pm.local.crypto_price_tape" in ids
    assert "macro.dxy.daily" in ids


def test_macro_dxy_graceful_when_missing():
    cat = ObservationCatalog()
    st = cat.stat("macro.dxy.daily")
    # catalog registered; file may not exist yet
    assert st["catalog_id"] == "macro.dxy.daily"

