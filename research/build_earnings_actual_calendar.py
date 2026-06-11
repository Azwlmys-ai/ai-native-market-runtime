#!/usr/bin/env python3
"""Build earnings_actual_calendar.json from verified date table."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import sys

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from research.earnings_actual_dates import EARNINGS_ACTUAL  # noqa: E402

_OUT = Path("/Users/libo/shared_intelligence/events/earnings_actual_calendar.json")
_ET = ZoneInfo("America/New_York")

# Earnings AMC default windows (Phase 2.1)
_EARNINGS_WINDOWS = {"pre_window_hours": 12, "post_window_hours": 72}


def _amc_utc(day: str) -> str:
    """4 PM Eastern on release day → UTC."""
    local = datetime.strptime(day, "%Y-%m-%d").replace(
        hour=16, minute=0, tzinfo=_ET,
    )
    return local.astimezone(timezone.utc).isoformat()


def build() -> dict:
    events = []
    for ticker, day, source in EARNINGS_ACTUAL:
        label = f"{ticker}_EARNINGS"
        events.append({
            "id": f"{label}_{day}",
            "type": "EARNINGS",
            "label": label,
            "ticker": ticker,
            "event_type": "EARNINGS",
            "event_time": _amc_utc(day),
            "datetime_utc": _amc_utc(day),
            "is_actual": True,
            "source": source,
            "impact": "high",
            **_EARNINGS_WINDOWS,
        })
    events.sort(key=lambda e: e["event_time"])
    return {
        "calendar": "earnings_actual",
        "version": 2,
        "description": "Verified earnings dates — replaces proxy calendar for attribution",
        "events": events,
    }


def main() -> int:
    payload = build()
    _OUT.parent.mkdir(parents=True, exist_ok=True)
    _OUT.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote {len(payload['events'])} actual earnings → {_OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
