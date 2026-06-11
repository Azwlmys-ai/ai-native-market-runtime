#!/usr/bin/env python3
"""
Export closed paper trades to shared_intelligence (read-only).

Project:  Polymarket_arbitrage
Root:     /Users/libo/.hermes/polymarket_arbitrage
Allowed:   research/, analytics/, memory/
Forbidden: agents trading logic, execution layer, risk layer

Input:    data/paper_trades.jsonl (read-only)
Output:   /Users/libo/shared_intelligence/trades/polymarket_weekly.jsonl

Usage:
    python research/export_shared_trades.py
    python research/export_shared_trades.py --week 2026-W23
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_IN = _ROOT / "data" / "paper_trades.jsonl"
_DEFAULT_OUT = Path("/Users/libo/shared_intelligence/trades/polymarket_weekly.jsonl")


def _iso_week(dt: datetime) -> str:
    return f"{dt.isocalendar().year}-W{dt.isocalendar().week:02d}"


def _parse_ts(raw: str) -> datetime:
    return datetime.fromisoformat(raw.replace("Z", "+00:00"))


def _session_from_ts(dt: datetime) -> str:
    hour = dt.astimezone(timezone.utc).hour
    if 0 <= hour < 8:
        return "asia"
    if 8 <= hour < 16:
        return "europe"
    return "us"


def _load_closed_trades(path: Path) -> list[dict]:
    """Pair open/close events; fall back to close-only rows."""
    opens: dict[tuple[str, str], dict] = {}
    closed: list[dict] = []

    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            t = row.get("type")
            market_id = str(row.get("market_id") or "")
            side = str(row.get("side") or "")
            key = (market_id, side)

            if t == "open":
                opens[key] = row
                continue
            if t != "close":
                continue

            entry_row = opens.get(key, {})
            entry_ts = entry_row.get("ts") or row.get("ts", "")
            exit_ts = row.get("ts", "")
            notional = float(row.get("notional_usd") or 0.0)
            realized = float(row.get("realized_pnl") or 0.0)
            pnl_pct = (realized / notional * 100.0) if notional > 0 else 0.0

            entry_dt = _parse_ts(entry_ts)
            exit_dt = _parse_ts(exit_ts)
            holding_minutes = max((exit_dt - entry_dt).total_seconds() / 60.0, 0.0)

            closed.append({
                "source": "polymarket_arbitrage",
                "symbol": market_id,
                "strategy": str(row.get("source") or "unknown"),
                "entry_time": entry_dt.isoformat().replace("+00:00", "Z"),
                "exit_time": exit_dt.isoformat().replace("+00:00", "Z"),
                "holding_minutes": round(holding_minutes, 2),
                "session": _session_from_ts(entry_dt),
                "pnl_pct": round(pnl_pct, 6),
                "win": realized > 0,
            })

    return closed


def filter_week(trades: list[dict], week: str) -> list[dict]:
    return [
        t for t in trades
        if _iso_week(_parse_ts(t["exit_time"])) == week
    ]


def export_trades(in_path: Path, out_path: Path, week: str | None = None) -> int:
    trades = _load_closed_trades(in_path)
    if week:
        trades = filter_week(trades, week)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as fh:
        for rec in trades:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return len(trades)


def main() -> int:
    p = argparse.ArgumentParser(description="Export Polymarket trades to shared_intelligence")
    p.add_argument("--in", dest="in_path", type=Path, default=_DEFAULT_IN)
    p.add_argument("--out", type=Path, default=_DEFAULT_OUT)
    p.add_argument("--week", default=None)
    args = p.parse_args()

    week = args.week or _iso_week(datetime.now(timezone.utc))
    if not args.in_path.exists():
        print(f"ERROR: input not found: {args.in_path}")
        return 1

    n = export_trades(args.in_path, args.out, week=week)
    print(f"Exported {n} trades for {week} → {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
