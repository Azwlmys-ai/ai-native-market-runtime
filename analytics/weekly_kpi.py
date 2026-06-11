#!/usr/bin/env python3
"""
Unified cross-market KPI snapshot (read-only).

Project:  Polymarket_arbitrage
Root:     /Users/libo/.hermes/polymarket_arbitrage
Allowed:   research/, analytics/, memory/

Input:    /Users/libo/shared_intelligence/trades/
          - us_etf_weekly.jsonl
          - okx_weekly.jsonl
          - polymarket_weekly.jsonl (optional; export via research/export_shared_trades.py)
Output:   /Users/libo/shared_intelligence/kpi/week_XX.json

Usage:
    python analytics/weekly_kpi.py
    python analytics/weekly_kpi.py --week 2026-W23
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from analytics.metrics import kpi_summary

_SHARED = Path("/Users/libo/shared_intelligence")
_DEFAULT_TRADES_DIR = _SHARED / "trades"
_DEFAULT_KPI_DIR = _SHARED / "kpi"


def _iso_week(dt: datetime) -> str:
    return f"{dt.isocalendar().year}-W{dt.isocalendar().week:02d}"


def _week_filename(week: str) -> str:
    return f"week_{week.replace('-', '_').lower()}.json"


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


def build_kpi(
    etf: list[dict],
    okx: list[dict],
    poly: list[dict],
    week: str,
    generated_at: datetime,
) -> dict:
    return {
        "week": week,
        "generated_at": generated_at.isoformat(),
        "phase": "hermes_quant_ecosystem_phase_1",
        "sources": {
            "us_etf": kpi_summary(etf),
            "okx": kpi_summary(okx),
            "polymarket_arbitrage": kpi_summary(poly),
        },
    }


def main() -> int:
    p = argparse.ArgumentParser(description="Build unified weekly KPI JSON")
    p.add_argument("--trades-dir", type=Path, default=_DEFAULT_TRADES_DIR)
    p.add_argument("--kpi-dir", type=Path, default=_DEFAULT_KPI_DIR)
    p.add_argument("--week", default=None)
    args = p.parse_args()

    week = args.week or _iso_week(datetime.now(timezone.utc))
    etf = _load_jsonl(args.trades_dir / "us_etf_weekly.jsonl")
    okx = _load_jsonl(args.trades_dir / "okx_weekly.jsonl")
    poly = _load_jsonl(args.trades_dir / "polymarket_weekly.jsonl")

    payload = build_kpi(etf, okx, poly, week, datetime.now(timezone.utc))
    out_path = args.kpi_dir / _week_filename(week)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"KPI → {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
