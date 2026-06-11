#!/usr/bin/env python3
"""
Step 3: Join historical events + market reactions → replay_dataset.jsonl

Learning-only. No trading system changes.

Usage:
    PYTHONPATH=. python3 analytics/historical_replay_joiner.py
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from analytics.replay_common import (
    MARKET_SYMBOLS,
    load_replay_source_events,
    market_bucket,
    polymarket_proxy_return,
    write_jsonl,
)
from research.history_paths import HISTORY_ROOT, REPLAY_DATASET


def join_event(ev: dict) -> dict:
    theme = ev.get("theme", "UNTHEMED")
    row = {
        "event": ev.get("event"),
        "event_class": ev.get("event_class"),
        "date": ev.get("date"),
        "theme": theme,
        "actual": ev.get("actual"),
        "expected": ev.get("expected"),
        "surprise": ev.get("surprise"),
        "ticker": ev.get("ticker"),
        "eps_actual": ev.get("eps_actual"),
        "eps_expected": ev.get("eps_expected"),
        "guidance": ev.get("guidance"),
        "datetime_utc": ev.get("datetime_utc"),
    }
    for sym in MARKET_SYMBOLS:
        for h in (1, 3, 5, 10):
            key = f"{sym}_{h}D"
            if key in ev:
                row[key] = ev[key]
        row[f"{sym}_market"] = market_bucket(sym)

    qqq_1d = ev.get("QQQ_1D")
    btc_1d = ev.get("BTC_1D")
    if qqq_1d is not None and btc_1d is not None:
        row["PM_PROXY_1D"] = polymarket_proxy_return(theme, float(qqq_1d), float(btc_1d))
        row["PM_PROXY_3D"] = polymarket_proxy_return(
            theme, float(ev.get("QQQ_3D") or 0), float(ev.get("BTC_3D") or 0),
        )
    return row


def build_replay_dataset() -> list[dict]:
    events = load_replay_source_events()
    return [join_event(ev) for ev in events]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=REPLAY_DATASET)
    args = parser.parse_args()

    rows = build_replay_dataset()
    write_jsonl(args.out, rows)

    meta = {
        "schema_version": "1.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "count": len(rows),
        "path": str(args.out),
    }
    (HISTORY_ROOT / "replay_meta.json").write_text(
        json.dumps(meta, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Wrote {len(rows)} replay rows → {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
