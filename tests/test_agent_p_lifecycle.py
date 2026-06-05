"""
tests/test_agent_p_lifecycle.py

验证 Agent P positions.json 生命周期管理：
- closed registry 防止重复生成止损信号
- stop-loss 触发后 position 被标记 closed
- closed position 保留 exit_price / close_reason / closed_at
- save_positions 正确合并 status 字段
"""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
from agents.agent_p import AgentP


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_agent(tmp_path):
    """Create an AgentP instance backed by a temp directory."""
    (tmp_path / "data").mkdir(exist_ok=True)
    (tmp_path / "logs").mkdir(exist_ok=True)
    (tmp_path / "config").mkdir(exist_ok=True)
    return AgentP(base_dir=str(tmp_path))


DEAD_POSITIONS = [
    {
        "market_slug": "will-bitcoin-hit-1m-before-gta-vi-872",
        "market_question": "Will bitcoin hit $1m before GTA VI?",
        "outcome": "no",
        "shares": 781.25,
        "avg_entry_price": 0.512,
        "total_cost": 400.0,
        "live_price": 0.0,
        "current_value": 0.0,
        "unrealized_pnl": -400.0,
        "percent_pnl": -100.0,
    },
    {
        "market_slug": "will-the-colorado-avalanche-win-the-2026-nhl-stanley-cup",
        "market_question": "Will the Colorado Avalanche win the 2026 NHL Stanley Cup?",
        "outcome": "no",
        "shares": 0.138,
        "avg_entry_price": 0.689,
        "total_cost": 0.095,
        "live_price": 0.0,
        "current_value": 0.0,
        "unrealized_pnl": -0.095,
        "percent_pnl": -100.0,
    },
]

LIVE_POSITION = {
    "market_slug": "will-jesus-christ-return-before-gta-vi-665",
    "market_question": "Will Jesus Christ return before GTA VI?",
    "outcome": "no",
    "shares": 577.0,
    "avg_entry_price": 0.52,
    "total_cost": 300.0,
    "live_price": 0.515,
    "current_value": 297.0,
    "unrealized_pnl": -2.88,
    "percent_pnl": -0.96,
}


# ---------------------------------------------------------------------------
# Test: closed registry skips positions in analyze_positions
# ---------------------------------------------------------------------------

def test_closed_registry_skips_position(tmp_path):
    """Positions in the closed registry must NOT generate sell signals."""
    agent = _make_agent(tmp_path)

    # Pre-populate registry with the two dead positions
    registry = [
        {
            "market_slug": "will-bitcoin-hit-1m-before-gta-vi-872",
            "outcome": "no",
            "closed_at": "2026-05-28T10:00:00",
            "exit_price": 0.5075,
            "close_reason": "止损 (-100.00%, 阈值 -12%)",
            "close_source": "agent_p_stop_loss",
        },
        {
            "market_slug": "will-the-colorado-avalanche-win-the-2026-nhl-stanley-cup",
            "outcome": "no",
            "closed_at": "2026-05-28T10:00:00",
            "exit_price": 0.689,
            "close_reason": "止损 (-100.00%, 阈值 -12%)",
            "close_source": "agent_p_stop_loss",
        },
    ]
    (tmp_path / "data" / "positions_closed_registry.json").write_text(
        json.dumps(registry)
    )

    # analyze_positions with the dead positions + one live position
    positions = DEAD_POSITIONS + [LIVE_POSITION]
    signals = agent.analyze_positions(positions)

    slugs_with_signals = {s.get("market_slug") or s.get("market") for s in signals}

    # Dead positions must NOT appear in signals
    assert "will-bitcoin-hit-1m-before-gta-vi-872" not in slugs_with_signals, \
        "bitcoin position should be skipped (in closed registry)"
    assert "will-the-colorado-avalanche-win-the-2026-nhl-stanley-cup" not in slugs_with_signals, \
        "colorado position should be skipped (in closed registry)"

    # The live position is still active (pnl ~= -1%, above default -10% stop loss)
    # It should NOT generate a stop-loss signal
    assert not any("止损" in s.get("reason", "") and "jesus" in (s.get("market_slug") or "")
                   for s in signals)


def test_status_closed_position_is_skipped(tmp_path):
    """Positions with status='closed' are skipped even without registry lookup."""
    agent = _make_agent(tmp_path)

    positions = [
        {**DEAD_POSITIONS[0], "status": "closed"},
        LIVE_POSITION,
    ]
    signals = agent.analyze_positions(positions)
    slugs = {s.get("market_slug") or s.get("market") for s in signals}
    assert "will-bitcoin-hit-1m-before-gta-vi-872" not in slugs


# ---------------------------------------------------------------------------
# Test: update_closed_registry writes urgent signals
# ---------------------------------------------------------------------------

def test_update_closed_registry_writes_urgent(tmp_path):
    """update_closed_registry must write urgent signals to the registry file."""
    agent = _make_agent(tmp_path)

    sell_signals = [
        {
            "market_slug": "will-bitcoin-hit-1m-before-gta-vi-872",
            "market": "will-bitcoin-hit-1m-before-gta-vi-872",
            "outcome": "no",
            "price": 0.5075,
            "reason": "止损 (-100.00%, 阈值 -12%)",
            "priority": "urgent",
            "pnl": -1.0,
        },
        {
            "market_slug": "will-the-colorado-avalanche-win-the-2026-nhl-stanley-cup",
            "market": "will-the-colorado-avalanche-win-the-2026-nhl-stanley-cup",
            "outcome": "no",
            "price": 0.689,
            "reason": "止损 (-100.00%, 阈值 -12%)",
            "priority": "urgent",
            "pnl": -1.0,
        },
        {
            # high priority (take-profit) — must NOT be written to closed registry
            "market_slug": "some-profitable-market",
            "market": "some-profitable-market",
            "outcome": "yes",
            "price": 0.85,
            "reason": "止盈 (20%, 目标 15%)",
            "priority": "high",
            "pnl": 0.20,
        },
    ]

    agent.update_closed_registry(sell_signals)

    registry_file = tmp_path / "data" / "positions_closed_registry.json"
    assert registry_file.exists(), "registry file must be created"

    with open(registry_file) as f:
        records = json.load(f)

    slugs = {r["market_slug"] for r in records}
    assert "will-bitcoin-hit-1m-before-gta-vi-872" in slugs
    assert "will-the-colorado-avalanche-win-the-2026-nhl-stanley-cup" in slugs
    assert "some-profitable-market" not in slugs, \
        "non-urgent (take-profit) signals must not enter closed registry"


def test_update_closed_registry_is_idempotent(tmp_path):
    """Calling update_closed_registry twice with same signal must not duplicate entries."""
    agent = _make_agent(tmp_path)
    sig = [{
        "market_slug": "will-bitcoin-hit-1m-before-gta-vi-872",
        "market": "will-bitcoin-hit-1m-before-gta-vi-872",
        "outcome": "no",
        "price": 0.5075,
        "reason": "止损",
        "priority": "urgent",
        "pnl": -1.0,
    }]
    agent.update_closed_registry(sig)
    agent.update_closed_registry(sig)

    with open(tmp_path / "data" / "positions_closed_registry.json") as f:
        records = json.load(f)
    bitcoin_entries = [r for r in records if r["market_slug"] == "will-bitcoin-hit-1m-before-gta-vi-872"]
    assert len(bitcoin_entries) == 1, "idempotent: must not duplicate entries"


# ---------------------------------------------------------------------------
# Test: closed registry entries retain required fields
# ---------------------------------------------------------------------------

def test_closed_registry_entry_has_required_fields(tmp_path):
    """Registry entries must have exit_price, close_reason, closed_at, close_source."""
    agent = _make_agent(tmp_path)
    agent.update_closed_registry([{
        "market_slug": "test-market",
        "market": "test-market",
        "outcome": "no",
        "price": 0.73,
        "reason": "止损 (-100.00%, 阈值 -12%)",
        "priority": "urgent",
        "pnl": -1.0,
    }])

    with open(tmp_path / "data" / "positions_closed_registry.json") as f:
        records = json.load(f)
    r = records[0]
    assert r["exit_price"] == 0.73
    assert "止损" in r["close_reason"]
    assert r["closed_at"]  # non-empty timestamp
    assert r["close_source"] == "agent_p_stop_loss"


# ---------------------------------------------------------------------------
# Test: full cycle — generate signals → update registry → next cycle skips
# ---------------------------------------------------------------------------

def test_second_cycle_generates_no_signals_for_closed_positions(tmp_path):
    """Simulate two cycles: 1st generates stop-loss → registry written; 2nd skips them."""
    agent = _make_agent(tmp_path)

    positions = list(DEAD_POSITIONS) + [LIVE_POSITION]

    # --- Cycle 1 ---
    signals_c1 = agent.analyze_positions(positions)
    urgent_slugs_c1 = {
        s.get("market_slug") or s.get("market")
        for s in signals_c1 if s.get("priority") == "urgent"
    }
    # Both dead positions must trigger urgent signals
    assert "will-bitcoin-hit-1m-before-gta-vi-872" in urgent_slugs_c1
    assert "will-the-colorado-avalanche-win-the-2026-nhl-stanley-cup" in urgent_slugs_c1

    # Simulate run() writing to registry
    agent.update_closed_registry(signals_c1)

    # --- Cycle 2 (same positions from pm-trader) ---
    signals_c2 = agent.analyze_positions(positions)
    slugs_c2 = {s.get("market_slug") or s.get("market") for s in signals_c2}

    assert "will-bitcoin-hit-1m-before-gta-vi-872" not in slugs_c2, \
        "Cycle 2: bitcoin must NOT generate signal (already in closed registry)"
    assert "will-the-colorado-avalanche-win-the-2026-nhl-stanley-cup" not in slugs_c2, \
        "Cycle 2: colorado must NOT generate signal (already in closed registry)"


# ---------------------------------------------------------------------------
# Test: save_positions merges status from registry
# ---------------------------------------------------------------------------

def test_save_positions_annotates_status(tmp_path):
    """save_positions must write status=closed for registry positions, status=open otherwise."""
    agent = _make_agent(tmp_path)

    # Write registry with bitcoin
    (tmp_path / "data" / "positions_closed_registry.json").write_text(json.dumps([{
        "market_slug": "will-bitcoin-hit-1m-before-gta-vi-872",
        "outcome": "no",
        "closed_at": "2026-05-29T00:00:00",
        "exit_price": 0.5075,
        "close_reason": "止损",
        "close_source": "agent_p_stop_loss",
    }]))

    positions = [DEAD_POSITIONS[0], LIVE_POSITION]
    agent.save_positions(positions)

    with open(tmp_path / "data" / "positions.json") as f:
        saved = json.load(f)

    bitcoin = next(p for p in saved if p["market_slug"] == "will-bitcoin-hit-1m-before-gta-vi-872")
    live = next(p for p in saved if p["market_slug"] == "will-jesus-christ-return-before-gta-vi-665")

    assert bitcoin["status"] == "closed"
    assert bitcoin["exit_price"] == 0.5075
    assert bitcoin["close_reason"] == "止损"
    assert bitcoin["closed_at"] == "2026-05-29T00:00:00"

    assert live["status"] == "open"


# ---------------------------------------------------------------------------
# Test: the 4 target dead markets in the actual positions.json trigger registry
# ---------------------------------------------------------------------------

def test_four_dead_markets_trigger_and_register(tmp_path):
    """The actual 4 dead-market positions (pnl=-100%) must all get registered after cycle 1."""
    agent = _make_agent(tmp_path)

    dead_four = [
        {
            "market_slug": "will-bitcoin-hit-1m-before-gta-vi-872",
            "outcome": "no", "percent_pnl": -100.0,
            "avg_entry_price": 0.512, "live_price": 0.0,
            "shares": 781.25, "total_cost": 400.0,
        },
        {
            "market_slug": "will-the-colorado-avalanche-win-the-2026-nhl-stanley-cup",
            "outcome": "no", "percent_pnl": -100.0,
            "avg_entry_price": 0.689, "live_price": 0.0,
            "shares": 0.138, "total_cost": 0.095,
        },
        {
            "market_slug": "will-the-anaheim-ducks-win-the-2026-nhl-stanley-cup",
            "outcome": "no", "percent_pnl": -100.0,
            "avg_entry_price": 0.959, "live_price": 0.0,
            "shares": 104.3, "total_cost": 100.0,
        },
        {
            "market_slug": "will-the-buffalo-sabres-win-the-2026-nhl-stanley-cup",
            "outcome": "no", "percent_pnl": -100.0,
            "avg_entry_price": 0.928, "live_price": 0.0,
            "shares": 107.8, "total_cost": 100.0,
        },
    ]

    # Cycle 1: all 4 must generate urgent signals
    signals = agent.analyze_positions(dead_four)
    urgent = [s for s in signals if s.get("priority") == "urgent"]
    assert len(urgent) == 4, f"Expected 4 urgent signals, got {len(urgent)}"

    agent.update_closed_registry(signals)

    # Verify all 4 written to registry
    with open(tmp_path / "data" / "positions_closed_registry.json") as f:
        records = json.load(f)
    registered_slugs = {r["market_slug"] for r in records}
    for pos in dead_four:
        assert pos["market_slug"] in registered_slugs, \
            f"{pos['market_slug']} must be in closed registry after cycle 1"

    # Cycle 2: no signals for any of the 4
    signals_c2 = agent.analyze_positions(dead_four)
    assert signals_c2 == [], \
        f"Cycle 2 must return empty signals for all 4 dead markets, got: {signals_c2}"
