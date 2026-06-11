"""Agent B paper_probe 兜底：无 strong signal 时仍产出可审计 probe，且不依赖 LLM。"""

import json
import types
from pathlib import Path
from unittest.mock import MagicMock

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _load_agent_b(tmp_path, monkeypatch):
    """加载 agent_b 并 stub 路径 + LLM。"""
    data_dir = tmp_path / "data"
    logs_dir = tmp_path / "logs"
    data_dir.mkdir(parents=True)
    logs_dir.mkdir(parents=True)
    monkeypatch.chdir(tmp_path)

    src = (PROJECT_ROOT / "agents" / "agent_b.py").read_text(encoding="utf-8")
    stub = "call_llm_hedged_race = None\n" + "\n".join(
        f"# STUB: {ln}" if ln.startswith("from llm_helper") else ln
        for ln in src.splitlines()
    )
    mod = types.ModuleType("agent_b_test")
    mod.__dict__["__file__"] = str(PROJECT_ROOT / "agents" / "agent_b.py")
    exec(compile(stub, "agent_b.py", "exec"), mod.__dict__)  # noqa: S102
    mod.DATA_DIR = data_dir
    mod.LOGS_DIR = logs_dir
    mod.BASE_DIR = tmp_path
    return mod, data_dir


def _sample_markets():
    return [
        {
            "id": "540817",
            "slug": "new-rhianna-album-before-gta-vi-926",
            "question": "New Rihanna Album before GTA VI?",
            "outcomes": ["Yes", "No"],
            "outcome_prices": [0.505, 0.495],
            "liquidity": 16078.0,
            "volume": 100000,
            "end_date": "2026-07-31T12:00:00Z",
        },
        {
            "id": "540819",
            "slug": "will-jesus-christ-return-before-gta-vi-665",
            "question": "Will Jesus Christ return before GTA VI?",
            "outcomes": ["Yes", "No"],
            "outcome_prices": [0.485, 0.515],
            "liquidity": 342158.0,
            "volume": 200000,
            "end_date": "2026-07-31T12:00:00Z",
        },
    ]


def _learned_rules():
    return {
        "market_rules": {
            "recommended": [{"market_type": "GTA_VI", "max_slippage": 600}],
            "avoid": [{"market_type": "Other"}],
        },
        "price_rules": {
            "mid_range": {"price_floor": 0.4, "price_ceiling": 0.6, "action": "buy_NO"},
        },
        "position_sizing": {"GTA_VI": "60%-70%"},
    }


def _write_fixtures(data_dir, *, status="ok"):
    (data_dir / "learned_rules.json").write_text(
        json.dumps({"learned_rules": _learned_rules()}), encoding="utf-8"
    )
    (data_dir / "latest_data.json").write_text(
        json.dumps({
            "polymarket_markets": _sample_markets(),
            "polymarket_status": status,
            "fed_rate": [],
            "btc_funding_rate": None,
        }),
        encoding="utf-8",
    )


def test_strong_signal_unchanged_when_llm_returns_high_conf_ev(tmp_path, monkeypatch):
    mod, data_dir = _load_agent_b(tmp_path, monkeypatch)
    _write_fixtures(data_dir, status="ok")

    strong_json = json.dumps({
        "signals": [{
            "market_slug": "will-jesus-christ-return-before-gta-vi-665",
            "side": "buy_no",
            "price": 0.515,
            "ev": 12.0,
            "confidence": 85,
            "learned_rule_match": "mid_range_GTA_VI",
            "reason": "mid range NO per learned rules",
            "holding_horizon_days": 30,
            "failure_conditions": ["若流动性跌破 $1000"],
        }]
    })
    race_meta = {"grok_started": True, "deepseek_started": False, "winner": "grok",
                 "elapsed_sec": 1.0, "hedge_triggered": False, "timeout": False}
    mod.call_llm_hedged_race = MagicMock(return_value=(strong_json, race_meta))
    mod.main()

    rep = json.loads((data_dir / "intelligence_report.json").read_text())
    assert rep["signals_count"] == 1
    assert rep["diagnostics"]["strong_count"] == 1
    assert rep["diagnostics"]["paper_probe_count"] == 0
    sig = rep["signals"][0]
    assert sig.get("probe") is not True
    assert sig["confidence"] >= 70
    mod.call_llm_hedged_race.assert_called_once()


def test_paper_probe_when_llm_returns_no_strong(tmp_path, monkeypatch):
    mod, data_dir = _load_agent_b(tmp_path, monkeypatch)
    _write_fixtures(data_dir, status="ok")

    weak_json = json.dumps({
        "signals": [{
            "market_slug": "will-jesus-christ-return-before-gta-vi-665",
            "side": "buy_no",
            "price": 0.515,
            "ev": 3.0,
            "confidence": 55,
            "learned_rule_match": "mid_range_GTA_VI",
            "reason": "weak",
            "failure_conditions": ["test"],
        }]
    })
    race_meta = {"grok_started": True, "deepseek_started": False, "winner": "grok",
                 "elapsed_sec": 1.0, "hedge_triggered": False, "timeout": False}
    mod.call_llm_hedged_race = MagicMock(return_value=(weak_json, race_meta))
    mod.main()

    rep = json.loads((data_dir / "intelligence_report.json").read_text())
    assert rep["signals_count"] >= 1
    assert rep["diagnostics"]["strong_count"] == 0
    assert rep["diagnostics"]["paper_probe_count"] >= 1
    probes = [s for s in rep["signals"] if s.get("probe")]
    assert probes
    p = probes[0]
    assert p["probe"] is True
    assert p["models_used"] == ["agent_b"]
    assert p["source_markets"]
    assert p["evidence"]
    assert p["failure_conditions"]
    assert p["confidence"] <= mod.PROBE_CONFIDENCE_CAP
    assert p["position_size"] == mod.PROBE_POSITION_SIZE
    assert p["tier"] == "exploration"
    assert p["data_sources"] and p["logic_chain"]


def test_stale_data_skips_llm_but_emits_paper_probe(tmp_path, monkeypatch):
    mod, data_dir = _load_agent_b(tmp_path, monkeypatch)
    _write_fixtures(data_dir, status="stale")

    mod.call_llm_hedged_race = MagicMock(side_effect=AssertionError("LLM must not run on stale"))
    mod.main()

    rep = json.loads((data_dir / "intelligence_report.json").read_text())
    assert rep["status"] == "degraded"
    assert rep["diagnostics"]["llm_called"] is False
    assert rep["diagnostics"]["paper_probe_count"] >= 1
    assert rep["signals_count"] >= 1
    mod.call_llm_hedged_race.assert_not_called()


def test_is_strong_respects_thresholds():
    from agents import agent_b as ab

    assert ab._is_strong_signal({"confidence": 85, "ev": 10}) is True
    assert ab._is_strong_signal({"confidence": 85, "ev": 5}) is False
    assert ab._is_strong_signal({"confidence": 60, "ev": 10}) is False
    assert ab._is_strong_signal({"confidence": 85, "ev": 10, "probe": True}) is False
