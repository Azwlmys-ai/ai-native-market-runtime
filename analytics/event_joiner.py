#!/usr/bin/env python3
"""
Join trades with macro/earnings events (observation only).

Project:  Polymarket_arbitrage
Allowed:   research/, analytics/, memory/
Forbidden: agents/, executors/, risk/

Input:    shared_intelligence/trades/*.jsonl
          shared_intelligence/events/*.json
Output:   shared_intelligence/trades/event_attributed_trades.jsonl

Usage:
    PYTHONPATH=. python3 analytics/event_joiner.py
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from analytics.event_catalog import (
    events_near_trade,
    load_all_events,
    load_theme_mapping,
    parse_utc,
    themes_for_trade,
)

_SHARED = Path("/Users/libo/shared_intelligence")
_DEFAULT_TRADES_DIR = _SHARED / "trades"
_DEFAULT_OUT = _SHARED / "trades" / "event_attributed_trades.jsonl"
_TRADE_FILES = (
    "us_etf_weekly.jsonl",
    "okx_weekly.jsonl",
    "polymarket_weekly.jsonl",
)


def _load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows: list[dict] = []
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def join_trade(trade: dict, events: list[dict], theme_map: dict) -> dict:
    entry_dt = parse_utc(trade["entry_time"])
    exit_dt = parse_utc(trade["exit_time"]) if trade.get("exit_time") else None
    symbol = trade.get("symbol", "")
    event_labels = events_near_trade(
        entry_dt, events, exit_time=exit_dt, symbol=symbol,
    )
    theme_labels = themes_for_trade(event_labels, symbol, theme_map)
    return {
        "source": trade.get("source"),
        "symbol": symbol,
        "strategy": trade.get("strategy"),
        "entry_time": trade["entry_time"],
        "exit_time": trade.get("exit_time"),
        "holding_minutes": trade.get("holding_minutes"),
        "session": trade.get("session"),
        "pnl_pct": trade.get("pnl_pct"),
        "win": trade.get("win"),
        "events": event_labels,
        "event_count": len(event_labels),
        "themes": theme_labels,
        "theme_count": len(theme_labels),
    }


def build_attributed_trades(
    trades_dir: Path,
    events_dir: Path,
) -> list[dict]:
    events = load_all_events(events_dir)
    theme_map = load_theme_mapping(events_dir / "theme_mapping.json")
    all_trades: list[dict] = []
    for name in _TRADE_FILES:
        all_trades.extend(_load_jsonl(trades_dir / name))
    return [join_trade(t, events, theme_map) for t in all_trades]


def main() -> int:
    p = argparse.ArgumentParser(description="Join trades with event calendars")
    p.add_argument("--trades-dir", type=Path, default=_DEFAULT_TRADES_DIR)
    p.add_argument("--events-dir", type=Path, default=_SHARED / "events")
    p.add_argument("--out", type=Path, default=_DEFAULT_OUT)
    args = p.parse_args()

    rows = build_attributed_trades(args.trades_dir, args.events_dir)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")

    with_events = sum(1 for r in rows if r["event_count"] > 0)
    print(f"Attributed {len(rows)} trades ({with_events} with events) → {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
