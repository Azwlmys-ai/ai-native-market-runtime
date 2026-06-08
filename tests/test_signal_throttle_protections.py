"""Signal throttle + Agent M/B timeout protections (Phase 3f-loop perf fix)."""

import json
import sys
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from runtime import signal_merge as sm


def _coint_sig(i: int, *, research=False, confidence=50, zscore=2.0):
    return {
        "market_id": f"m{i}",
        "market_slug": f"m{i}",
        "direction": "YES" if i % 2 == 0 else "NO",
        "confidence": confidence,
        "research_candidate": research,
        "tier": "research" if research else "exploration",
        "probe": True,
        "source": "cointegration",
        "source_agent": "cointegration",
        "evidence": {"zscore": zscore},
        "data_sources": ["data/market_price_history.json"],
        "logic_chain": ["coint test"],
        "generated_at": datetime.now().isoformat(),
    }


class TestCointCap:
    def test_sixty_candidates_cap_to_eight(self):
        signals = [_coint_sig(i, research=(i < 5), confidence=90 - i, zscore=3.0 - i * 0.01)
                   for i in range(60)]
        selected, stats = sm.cap_cointegration_probe_signals(signals, cap=8)
        assert stats["candidate_total"] == 60
        assert stats["selected"] == 8
        assert stats["dropped"] == 52
        assert stats["cap"] == 8
        assert len(selected) == 8
        assert all(s.get("research_candidate") for s in selected[:5])

    def test_apply_max_total_twenty(self):
        b = [{"source_agent": "agent_b", "market_id": f"b{i}", "direction": "YES",
              "confidence": 80, "generated_at": datetime.now().isoformat()} for i in range(5)]
        coint = [_coint_sig(i) for i in range(30)]
        merged = b + coint
        capped = sm.apply_max_total_cap(merged, 20)
        assert len(capped) == 20
        assert sum(1 for s in capped if s["source_agent"] == "agent_b") == 5


class TestAgentBTimeout:
    def test_b_timeout_skips_stale_intel(self, tmp_path, monkeypatch):
        import orchestrator as orch_mod

        monkeypatch.setenv("SIGNAL_MAX_AGE_SECONDS", "7200")
        orch = orch_mod.Orchestrator(base_dir=tmp_path)
        orch._current_cycle_id = "cycle-b-timeout"
        orch._agent_b_ok_this_cycle = False

        (orch.data_dir / "intelligence_report.json").write_text(json.dumps({
            "signals": [{
                "market_slug": "old-slug",
                "side": "buy_no",
                "confidence": 90,
                "generated_at": datetime.now().isoformat(),
            }],
        }))
        (orch.data_dir / "latest_data.json").write_text(json.dumps({
            "polymarket_markets": [{
                "id": "1", "slug": "old-slug", "question": "Old?",
                "outcomes": ["Yes", "No"], "outcome_prices": [0.4, 0.6],
            }],
        }))
        (orch.data_dir / "signals.json").write_text("[]")

        assert orch._consolidate_signals_for_review() is False

    def test_non_b_stale_cycle_skipped(self):
        stale = {
            "market_id": "d1", "direction": "YES", "source": "agent_d",
            "generated_at": datetime.now().isoformat(),
            "generated_cycle_id": "old-cycle",
            "confidence": 80,
        }
        fresh = {
            "market_id": "d2", "direction": "YES", "source": "agent_d",
            "generated_at": datetime.now().isoformat(),
            "generated_cycle_id": "new-cycle",
            "confidence": 70,
        }
        out = sm.filter_fresh_non_b_from_file(
            [stale, fresh], max_age_seconds=7200, cycle_id="new-cycle",
        )
        assert len(out) == 1
        assert out[0]["market_id"] == "d2"


class TestAgentMLightweight:
    def test_coint_probe_skips_llm(self, tmp_path):
        from agents.agent_m import AgentM

        agent = AgentM(base_dir=tmp_path)
        signal = _coint_sig(1, research=True, confidence=55, zscore=2.5)
        with patch("agents.agent_m.call_llm_sync") as mock_llm:
            result = agent.review_signal(signal)
            mock_llm.assert_not_called()
        assert result["review_status"] == "lightweight_coint"
        assert result["decision"] in ("PAPER_PROBE", "REJECT", "DEFER")

    def test_coint_probe_paper_probe_grade(self, tmp_path):
        from agents.agent_m import AgentM

        agent = AgentM(base_dir=tmp_path)
        signal = _coint_sig(2, research=True, confidence=60, zscore=2.8)
        result = agent.review_signal(signal)
        grade = agent._grade(result)
        assert grade == "PAPER_PROBE"


class TestAgentMPartial:
    def test_partial_flush_writes_metadata(self, tmp_path, monkeypatch):
        from agents.agent_m import AgentM

        monkeypatch.setenv("PA_AGENT_M_PARTIAL_EVERY", "2")
        monkeypatch.setenv("PA_CYCLE_ID", "partial-cycle-001")
        (tmp_path / "data").mkdir(parents=True, exist_ok=True)
        signals = [_coint_sig(i) for i in range(4)]
        (tmp_path / "data" / "signals.json").write_text(json.dumps(signals))

        agent = AgentM(base_dir=tmp_path)
        agent.run()

        review = json.loads((tmp_path / "data" / "review_results.json").read_text())
        assert review["partial"] is False
        assert review["generated_cycle_id"] == "partial-cycle-001"
        assert review["processed_count"] == 4
        assert review["total"] == 4
        assert review["paper_probe"] >= 1


class TestStaleReviewExecution:
    def test_partial_review_blocks_executor(self, tmp_path, monkeypatch):
        from executors.signal_executor import SignalExecutor

        data = tmp_path / "data"
        data.mkdir(parents=True, exist_ok=True)
        (data / "review_results.json").write_text(json.dumps({
            "partial": True,
            "generated_cycle_id": "cycle-x",
            "processed_count": 3,
            "total": 10,
            "timestamp": datetime.now().isoformat(),
        }))
        (data / "approved_signals.json").write_text(json.dumps([_coint_sig(1)]))

        monkeypatch.setenv("EXECUTOR_DRY_RUN", "1")
        monkeypatch.setenv("PA_CYCLE_ID", "cycle-x")
        ex = SignalExecutor(base_dir=str(tmp_path))
        assert ex.load_approved_signals() == []

    def test_dry_run_success_zero(self, tmp_path, monkeypatch):
        from executors.signal_executor import SignalExecutor

        monkeypatch.setenv("EXECUTOR_DRY_RUN", "1")
        data = tmp_path / "data"
        data.mkdir(parents=True, exist_ok=True)
        sig = _coint_sig(1)
        (data / "review_results.json").write_text(json.dumps({
            "partial": False,
            "generated_cycle_id": "cycle-y",
            "timestamp": datetime.now().isoformat(),
        }))
        (data / "approved_signals.json").write_text(json.dumps([sig]))
        monkeypatch.setenv("PA_CYCLE_ID", "cycle-y")

        ex = SignalExecutor(base_dir=str(tmp_path))
        ex.run()
        out = json.loads((data / "execution_results.json").read_text())
        assert out["success"] == 0
        assert out["dry_run"] >= 1


class TestOrchestratorCointCapIntegration:
    def test_consolidate_caps_coint_and_total(self, tmp_path, monkeypatch):
        import orchestrator as orch_mod
        from runtime import cointegration as ci

        monkeypatch.setenv("PA_COINT_SIGNALS", "1")
        monkeypatch.setenv("PA_COINT_SIGNAL_CAP", "8")
        monkeypatch.setenv("SIGNAL_MERGE_MAX_TOTAL", "20")

        orch = orch_mod.Orchestrator(base_dir=tmp_path)
        orch._current_cycle_id = "cap-cycle"

        fake_sigs = [_coint_sig(i, confidence=80 - i) for i in range(60)]
        with patch.object(ci, "find_candidates", return_value={"candidates": []}), \
             patch.object(ci, "to_pipeline_signals", return_value=fake_sigs):
            (orch.data_dir / "intelligence_report.json").write_text(
                json.dumps({"signals": []}),
            )
            (orch.data_dir / "signals.json").write_text("[]")
            assert orch._consolidate_signals_for_review() is True

        sigs = json.loads((orch.data_dir / "signals.json").read_text())
        assert len(sigs) <= 20
        coint = [s for s in sigs if s.get("source_agent") == "cointegration"]
        assert len(coint) <= 8
