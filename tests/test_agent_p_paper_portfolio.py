"""
tests/test_agent_p_paper_portfolio.py

验证 dry-run 下 Agent P 读取 paper_portfolio 并合并 pm-trader 持仓。
"""

import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
from agents.agent_p import AgentP, position_dedup_key


def _make_agent(tmp_path):
    (tmp_path / "data").mkdir(exist_ok=True)
    (tmp_path / "logs").mkdir(exist_ok=True)
    (tmp_path / "config").mkdir(exist_ok=True)
    return AgentP(base_dir=str(tmp_path))


def _write_paper_portfolio(tmp_path, positions):
    (tmp_path / "data" / "paper_portfolio.json").write_text(
        json.dumps(positions, ensure_ascii=False, indent=2)
    )


def test_load_paper_open_positions_excludes_closed(tmp_path):
    agent = _make_agent(tmp_path)
    _write_paper_portfolio(tmp_path, [
        {
            "market_id": "111",
            "market_slug": "open-market",
            "direction": "NO",
            "entry_price": 0.5,
            "opened_at": "2026-06-07T10:00:00+00:00",
        },
        {
            "market_id": "222",
            "market_slug": "closed-market",
            "direction": "YES",
            "entry_price": 0.4,
            "closed_at": "2026-06-07T11:00:00+00:00",
        },
        {
            "market_id": "333",
            "market_slug": "status-closed",
            "direction": "NO",
            "entry_price": 0.6,
            "status": "closed",
        },
    ])
    opens = agent.load_paper_open_positions()
    assert len(opens) == 1
    assert opens[0]["market_id"] == "111"


def test_normalize_paper_position_uses_latest_data_price(tmp_path):
    agent = _make_agent(tmp_path)
    latest_data = {
        "polymarket_markets": [
            {
                "id": "540819",
                "slug": "paper-slug-market",
                "outcomes": ["Yes", "No"],
                "outcome_prices": [0.30, 0.70],
            }
        ]
    }
    norm = agent.normalize_paper_position(
        {
            "market_id": "540819",
            "market_slug": "paper-slug-market",
            "direction": "NO",
            "entry_price": 0.50,
            "grade": "paper_probe",
            "source_agent": "agent_b",
        },
        latest_data,
    )
    assert norm["market_slug"] == "paper-slug-market"
    assert norm["outcome"] == "no"
    assert norm["live_price"] == 0.70
    assert norm["percent_pnl"] == pytest.approx(40.0)
    assert norm["grade"] == "paper_probe"
    assert norm["portfolio_source"] == "paper_portfolio"


def test_normalize_paper_position_missing_price_no_fake_pnl(tmp_path):
    agent = _make_agent(tmp_path)
    norm = agent.normalize_paper_position(
        {
            "market_id": "999",
            "market_slug": "no-price-market",
            "direction": "YES",
            "entry_price": 0.50,
        },
        {},
    )
    assert norm["live_price"] is None
    assert norm["percent_pnl"] == 0.0


def test_merge_portfolios_dedupes_pm_and_paper(tmp_path):
    agent = _make_agent(tmp_path)
    pm = [{
        "market_id": "540819",
        "market_slug": "shared-market",
        "outcome": "no",
        "percent_pnl": -1.0,
    }]
    paper = [{
        "market_id": "540819",
        "market_slug": "shared-market",
        "direction": "NO",
        "entry_price": 0.50,
    }, {
        "market_id": "777",
        "market_slug": "paper-only",
        "direction": "YES",
        "entry_price": 0.25,
    }]
    merged = agent.merge_portfolios(pm, paper, {})
    assert len(merged) == 2
    assert merged[0]["market_slug"] == "shared-market"
    assert merged[1]["market_slug"] == "paper-only"


def test_get_portfolio_dry_run_merges_paper(monkeypatch, tmp_path):
    agent = _make_agent(tmp_path)
    monkeypatch.setenv("EXECUTOR_DRY_RUN", "1")
    _write_paper_portfolio(tmp_path, [
        {
            "market_id": "888",
            "market_slug": "dry-run-paper",
            "direction": "NO",
            "entry_price": 0.48,
            "grade": "paper_probe",
        },
    ])
    pm_positions = [{
        "market_id": "1",
        "market_slug": "pm-only",
        "outcome": "yes",
        "percent_pnl": 2.0,
    }]
    with patch.object(agent, "get_pm_trader_portfolio", return_value=pm_positions):
        merged = agent.get_portfolio()
    assert len(merged) == 2
    slugs = {p.get("market_slug") for p in merged}
    assert "pm-only" in slugs
    assert "dry-run-paper" in slugs


def test_analyze_positions_includes_paper_open_not_closed(tmp_path):
    agent = _make_agent(tmp_path)
    (tmp_path / "data" / "strategy_config.json").write_text(json.dumps({
        "take_profit": {"default": {"min": 0.10, "max": 0.15}},
        "stop_loss": {"medium_confidence": -0.10},
        "trailing_stop": {"trigger_profit": 0.20, "trailing_percent": 0.05},
    }))
    positions = [
        agent.normalize_paper_position(
            {
                "market_id": "100",
                "market_slug": "paper-stop-loss",
                "direction": "NO",
                "entry_price": 0.50,
            },
            {
                "polymarket_markets": [{
                    "id": "100",
                    "slug": "paper-stop-loss",
                    "outcomes": ["Yes", "No"],
                    "outcome_prices": [0.80, 0.20],
                }],
            },
        ),
    ]
    signals = agent.analyze_positions(positions)
    assert any(
        (s.get("market_slug") == "paper-stop-loss" and "止损" in s.get("reason", ""))
        for s in signals
    )


def test_position_dedup_key_accepts_slug_or_market_id():
    assert position_dedup_key({
        "market_id": "123",
        "outcome": "no",
    }) == ("123", "NO")
    assert position_dedup_key({
        "market_slug": "slug-only",
        "direction": "YES",
    }) == ("slug-only", "YES")
