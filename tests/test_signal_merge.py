"""Tests for multi-agent signal merge (orchestrator consolidate fix)."""

import json
import sys
import time
from datetime import datetime
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from runtime import signal_merge as sm


def _fresh(**kwargs):
    base = {
        "generated_at": datetime.now().isoformat(),
        "timestamp": datetime.now().isoformat(),
        "confidence": 70,
    }
    base.update(kwargs)
    return base


def _b_sig(market_id="m1", direction="NO", confidence=80):
    return _fresh(
        market_id=market_id,
        market_slug=market_id,
        direction=direction,
        source="agent_b",
        confidence=confidence,
    )


def _d_sig(market_id="m2", direction="YES", confidence=75, **extra):
    base = _fresh(
        market_id=market_id,
        market_slug=market_id,
        direction=direction,
        source="agent_d",
        strategy="risk_free_arbitrage",
        confidence=confidence,
    )
    base.update(extra)
    return base


class TestSignalMergeUnit:
    def test_b_only_unchanged_core_fields(self):
        b = [_b_sig()]
        merged = sm.merge_signals(b, [], cycle_id="cycle-1")
        assert len(merged) == 1
        assert merged[0]["source_agent"] == "agent_b"
        assert merged[0]["signal_origin"] == "intelligence_report"
        assert merged[0]["generated_cycle_id"] == "cycle-1"
        assert merged[0]["signal_merge_reason"] == "agent_b_primary"

    def test_b_plus_non_b_merged(self):
        b = [_b_sig(market_id="b1")]
        non_b = [_d_sig(market_id="d1")]
        merged = sm.merge_signals(b, non_b, cycle_id="c1")
        assert len(merged) == 2
        agents = {s["source_agent"] for s in merged}
        assert agents == {"agent_b", "agent_d"}

    def test_dedup_same_key_b_wins(self):
        b = [_b_sig(market_id="same", direction="NO", confidence=60)]
        # agent_e-style directional signal shares dedup key with B (not ARB bucket)
        non_b = [_fresh(
            market_id="same", direction="NO", source="agent_e", confidence=95,
        )]
        merged = sm.merge_signals(b, non_b)
        assert len(merged) == 1
        assert merged[0]["source_agent"] == "agent_b"

    def test_dedup_higher_confidence_non_b_when_no_b(self):
        non_b = [
            _d_sig(market_id="x", confidence=60),
            _d_sig(market_id="x", confidence=90),
        ]
        # same key from duplicate entries — second pass in merge replaces first if higher
        merged = sm.merge_signals([], non_b)
        assert len(merged) == 1
        assert merged[0]["confidence"] == 90

    def test_stale_non_b_excluded(self):
        stale = _d_sig()
        stale["generated_at"] = datetime.fromtimestamp(time.time() - 5 * 3600).isoformat()
        fresh_b = [_b_sig()]
        file_sigs = [stale]
        merged = sm.consolidate_merge(
            fresh_b,
            file_sigs,
            max_age_seconds=7200,
        )
        assert len(merged) == 1
        assert merged[0]["source_agent"] == "agent_b"

    def test_max_total_twenty(self):
        b = [_b_sig(market_id=f"b{i}") for i in range(15)]
        non_b = [_d_sig(market_id=f"d{i}") for i in range(15)]
        merged = sm.merge_signals(b, non_b, max_total=20)
        assert len(merged) == 20
        assert sum(1 for s in merged if s["source_agent"] == "agent_b") == 15
        assert sum(1 for s in merged if s["source_agent"] == "agent_d") == 5

    def test_max_three_per_non_b_agent(self):
        non_b = [_d_sig(market_id=f"d{i}", confidence=50 + i) for i in range(6)]
        capped = sm.cap_per_non_b_agent(non_b, max_per_agent=3)
        assert len(capped) == 3
        confs = sorted([s["confidence"] for s in capped], reverse=True)
        assert confs == [55, 54, 53]

    def test_empty_merge_returns_empty(self):
        assert sm.consolidate_merge([], [], max_age_seconds=7200) == []

    def test_cycle_id_filters_stale_non_b(self):
        stale = _d_sig(market_id="old", generated_cycle_id="cycle-old")
        fresh = _d_sig(market_id="new", generated_cycle_id="cycle-new")
        out = sm.filter_fresh_non_b_from_file(
            [stale, fresh], max_age_seconds=7200, cycle_id="cycle-new",
        )
        assert len(out) == 1
        assert out[0]["market_id"] == "new"

    def test_coint_cap_priority(self):
        sigs = [
            _fresh(market_id="a", source="cointegration", source_agent="cointegration",
                   research_candidate=False, confidence=90, evidence={"zscore": 1.0}),
            _fresh(market_id="b", source="cointegration", source_agent="cointegration",
                   research_candidate=True, confidence=50, evidence={"zscore": 3.0}),
        ]
        selected, stats = sm.cap_cointegration_probe_signals(sigs, cap=1)
        assert stats["selected"] == 1
        assert selected[0]["market_id"] == "b"


class TestOrchestratorConsolidateIntegration:
    def _setup_orch(self, tmp_path, monkeypatch):
        monkeypatch.setenv("SIGNAL_MAX_AGE_SECONDS", "7200")
        import orchestrator as orch_mod
        orch = orch_mod.Orchestrator(base_dir=tmp_path)
        orch._current_cycle_id = "test-cycle-001"
        return orch

    def test_consolidate_b_only(self, tmp_path, monkeypatch):
        orch = self._setup_orch(tmp_path, monkeypatch)
        (orch.data_dir / "latest_data.json").write_text(json.dumps({
            "polymarket_markets": [{
                "id": "99", "slug": "test-slug", "question": "Test Q?",
                "outcomes": ["Yes", "No"], "outcome_prices": [0.3, 0.7],
            }],
        }))
        (orch.data_dir / "intelligence_report.json").write_text(json.dumps({
            "signals": [{
                "market_slug": "test-slug",
                "side": "buy_no",
                "price": 0.7,
                "confidence": 85,
                "ev": 10,
                "generated_at": datetime.now().isoformat(),
            }],
        }))
        assert orch._consolidate_signals_for_review() is True
        sigs = json.loads((orch.data_dir / "signals.json").read_text())
        assert len(sigs) == 1
        assert sigs[0]["source_agent"] == "agent_b"
        assert sigs[0]["direction"] == "NO"

    def test_consolidate_b_plus_d(self, tmp_path, monkeypatch):
        orch = self._setup_orch(tmp_path, monkeypatch)
        (orch.data_dir / "latest_data.json").write_text(json.dumps({
            "polymarket_markets": [{
                "id": "1", "slug": "slug-b", "question": "B?",
                "outcomes": ["Yes", "No"], "outcome_prices": [0.4, 0.6],
            }],
        }))
        (orch.data_dir / "intelligence_report.json").write_text(json.dumps({
            "signals": [{
                "market_slug": "slug-b",
                "side": "buy_no",
                "price": 0.6,
                "confidence": 80,
                "generated_at": datetime.now().isoformat(),
            }],
        }))
        (orch.data_dir / "signals.json").write_text(json.dumps([
            _d_sig(market_id="slug-d", market_slug="slug-d", confidence=77),
        ]))
        assert orch._consolidate_signals_for_review() is True
        sigs = json.loads((orch.data_dir / "signals.json").read_text())
        assert len(sigs) == 2
        agents = {s["source_agent"] for s in sigs}
        assert agents == {"agent_b", "agent_d"}

    def test_consolidate_empty_when_no_signals(self, tmp_path, monkeypatch):
        orch = self._setup_orch(tmp_path, monkeypatch)
        (orch.data_dir / "intelligence_report.json").write_text(
            json.dumps({"signals": []}),
        )
        (orch.data_dir / "signals.json").write_text("[]")
        assert orch._consolidate_signals_for_review() is False

    def test_consolidate_non_b_only_when_b_empty(self, tmp_path, monkeypatch):
        orch = self._setup_orch(tmp_path, monkeypatch)
        (orch.data_dir / "intelligence_report.json").write_text(
            json.dumps({"signals": []}),
        )
        (orch.data_dir / "signals.json").write_text(json.dumps([
            _d_sig(market_id="only-d", market_slug="only-d"),
        ]))
        assert orch._consolidate_signals_for_review() is True
        sigs = json.loads((orch.data_dir / "signals.json").read_text())
        assert len(sigs) == 1
        assert sigs[0]["source_agent"] == "agent_d"
