import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from paper_pnl import PaperPortfolio


def _portfolio(tmp_path):
    (tmp_path / "data").mkdir(exist_ok=True)
    return PaperPortfolio(base_dir=tmp_path)


def test_numeric_market_id_matches_numeric_market_id(tmp_path):
    pp = _portfolio(tmp_path)
    pp.open_position({
        "market_id": "553824",
        "market_name": "Cup winner?",
        "direction": "NO",
        "price": 0.50,
        "position_size": 0.10,
    })

    closed = pp.close_position({
        "market_id": "553824",
        "outcome": "no",
        "price": 0.40,
    })

    assert closed is not None
    assert closed.closed_at
    assert closed.realized_pnl == 200.0


def test_slug_sell_signal_matches_open_position_slug_alias(tmp_path):
    pp = _portfolio(tmp_path)
    pp.open_position({
        "market_id": "540844",
        "market_name": "Will bitcoin hit $1m before GTA VI?",
        "market": "Will bitcoin hit $1m before GTA VI?",
        "market_slug": "will-bitcoin-hit-1m-before-gta-vi-872",
        "direction": "NO",
        "price": 0.50,
        "position_size": 0.10,
    })

    closed = pp.close_position({
        "market": "will-bitcoin-hit-1m-before-gta-vi-872",
        "outcome": "no",
        "price": 0.45,
    })

    assert closed is not None
    assert closed.market_id == "540844"
    assert closed.realized_pnl == 100.0


def test_unmatched_sell_does_not_pollute_portfolio(tmp_path):
    pp = _portfolio(tmp_path)
    pp.open_position({
        "market_id": "1",
        "market_slug": "known-market",
        "direction": "YES",
        "price": 0.50,
    })

    closed = pp.close_position({
        "market": "missing-market",
        "outcome": "yes",
        "price": 0.60,
    })

    assert closed is None
    assert len(pp.positions) == 1
    assert pp.positions[0].market_id == "1"
    trades = (tmp_path / "data" / "paper_trades.jsonl").read_text().splitlines()
    assert json.loads(trades[-1])["type"] == "unmatched_sell"


def test_missing_exit_price_does_not_default_to_half_for_realized_pnl(tmp_path):
    pp = _portfolio(tmp_path)
    pp.open_position({
        "market_id": "2",
        "market_slug": "missing-price-market",
        "direction": "YES",
        "price": 0.30,
    })

    closed = pp.close_position({
        "market": "missing-price-market",
        "outcome": "yes",
    })

    assert closed is not None
    assert closed.exit_price is None
    assert closed.price_source == "missing"
    assert closed.realized_pnl is None
    assert pp.get_summary()["realized_pnl"] == 0


def test_exit_price_calculates_realized_pnl(tmp_path):
    pp = _portfolio(tmp_path)
    pp.open_position({
        "market_id": "3",
        "market_slug": "priced-market",
        "direction": "YES",
        "price": 0.25,
        "position_size": 0.20,
    })

    closed = pp.close_position({
        "market": "priced-market",
        "outcome": "yes",
        "price": 0.50,
    })

    assert closed is not None
    assert closed.exit_price == 0.50
    assert closed.price_source == "price"
    assert closed.realized_pnl == 2000.0
