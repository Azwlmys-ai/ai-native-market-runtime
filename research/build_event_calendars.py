#!/usr/bin/env python3
"""
Build macro + earnings event calendars into shared_intelligence/events/.

Project:  Polymarket_arbitrage (research/ only)
Output:   /Users/libo/shared_intelligence/events/

Data sources (documented, no live trading impact):
  - NFP:    First Friday of month, 13:30 UTC (08:30 ET)
  - CPI:    BLS approximate release (12th business-day proxy), 13:30 UTC
  - FOMC:   Federal Reserve published schedule (decision day 18:00 UTC)
  - Earnings proxy: deprecated — use build_earnings_actual_calendar.py

Usage:
    python3 research/build_event_calendars.py
"""

from __future__ import annotations

import json
from calendar import monthrange
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

_EVENTS_DIR = Path("/Users/libo/shared_intelligence/events")
_YEARS = (2024, 2025, 2026)

# FOMC decision days (second day of meeting) — Fed published schedule
_FOMC_DECISIONS: dict[int, list[str]] = {
    2024: [
        "2024-01-31", "2024-03-20", "2024-05-01", "2024-06-12",
        "2024-07-31", "2024-09-18", "2024-11-07", "2024-12-18",
    ],
    2025: [
        "2025-01-29", "2025-03-19", "2025-05-07", "2025-06-18",
        "2025-07-30", "2025-09-17", "2025-10-29", "2025-12-10",
    ],
    2026: [
        "2026-01-28", "2026-03-18", "2026-04-29", "2026-06-17",
        "2026-07-29", "2026-09-16", "2026-10-28", "2026-12-09",
    ],
}

# Quarterly earnings anchors (month, day) per fiscal quarter index 0..3
_EARNINGS_ANCHORS: dict[str, list[tuple[int, int]]] = {
    "NVDA": [(2, 21), (5, 22), (8, 28), (11, 20)],
    "AVGO": [(3, 7), (6, 6), (9, 5), (12, 12)],
    "TSLA": [(1, 25), (4, 23), (7, 23), (10, 23)],
    "AAPL": [(2, 1), (5, 2), (8, 1), (10, 31)],
    "MSFT": [(1, 30), (4, 25), (7, 30), (10, 30)],
    "META": [(2, 1), (4, 24), (7, 31), (10, 30)],
    "AMZN": [(2, 1), (4, 30), (8, 1), (10, 31)],
}


def _utc_iso(d: date, hour: int, minute: int = 0) -> str:
    return datetime(d.year, d.month, d.day, hour, minute, tzinfo=timezone.utc).isoformat()


def _first_friday(year: int, month: int) -> date:
    for day in range(1, 8):
        d = date(year, month, day)
        if d.weekday() == 4:
            return d
    raise ValueError(f"No Friday in first week: {year}-{month}")


def _cpi_release_proxy(year: int, month: int) -> date:
    """BLS CPI ~ mid-month; use 12th shifted to nearest weekday."""
    day = min(12, monthrange(year, month)[1])
    d = date(year, month, day)
    while d.weekday() >= 5:
        d += timedelta(days=1)
    return d


def _shift_to_weekday(d: date) -> date:
    while d.weekday() >= 5:
        d += timedelta(days=1)
    return d


def build_nfp() -> dict:
    events = []
    for year in _YEARS:
        for month in range(1, 13):
            d = _first_friday(year, month)
            events.append({
                "id": f"NFP_{d.isoformat()}",
                "type": "NFP",
                "label": "NFP",
                "datetime_utc": _utc_iso(d, 13, 30),
                "event_time": _utc_iso(d, 13, 30),
                "pre_window_hours": 2,
                "post_window_hours": 24,
                "impact": "high",
                "source": "rule:first_friday_0830_et",
                "is_actual": True,
            })
    return {"calendar": "nfp", "version": 2, "events": events}


def build_cpi() -> dict:
    events = []
    for year in _YEARS:
        for month in range(1, 13):
            d = _cpi_release_proxy(year, month)
            events.append({
                "id": f"CPI_{d.isoformat()}",
                "type": "CPI",
                "label": "CPI",
                "datetime_utc": _utc_iso(d, 13, 30),
                "event_time": _utc_iso(d, 13, 30),
                "pre_window_hours": 2,
                "post_window_hours": 24,
                "impact": "high",
                "source": "proxy:bls_mid_month",
                "is_actual": False,
            })
    return {"calendar": "cpi", "version": 2, "events": events}


def build_fomc() -> dict:
    events = []
    for year, dates in _FOMC_DECISIONS.items():
        for ds in dates:
            d = date.fromisoformat(ds)
            events.append({
                "id": f"FOMC_{d.isoformat()}",
                "type": "FOMC",
                "label": "FOMC",
                "datetime_utc": _utc_iso(d, 18, 0),
                "event_time": _utc_iso(d, 18, 0),
                "pre_window_hours": 4,
                "post_window_hours": 48,
                "impact": "high",
                "source": "federalreserve.gov",
                "is_actual": True,
            })
    return {"calendar": "fomc", "version": 2, "events": events}


def build_earnings() -> dict:
    events = []
    for ticker, anchors in _EARNINGS_ANCHORS.items():
        for year in _YEARS:
            for q_idx, (month, day) in enumerate(anchors):
                d = _shift_to_weekday(date(year, month, min(day, monthrange(year, month)[1])))
                label = f"{ticker}_EARNINGS"
                events.append({
                    "id": f"{label}_{d.isoformat()}",
                    "type": "EARNINGS",
                    "label": label,
                    "ticker": ticker,
                    "quarter_index": q_idx,
                    "datetime_utc": _utc_iso(d, 21, 0),  # AMC ~ 4pm ET
                    "impact": "high",
                    "source": "proxy:quarterly_anchor",
                })
    events.sort(key=lambda e: e["datetime_utc"])
    return {"calendar": "earnings", "version": 1, "events": events}


def write_calendar(name: str, payload: dict) -> Path:
    _EVENTS_DIR.mkdir(parents=True, exist_ok=True)
    path = _EVENTS_DIR / f"{name}_calendar.json"
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def main() -> int:
    paths = [
        write_calendar("nfp", build_nfp()),
        write_calendar("cpi", build_cpi()),
        write_calendar("fomc", build_fomc()),
    ]
    for p in paths:
        n = len(json.loads(p.read_text())["events"])
        print(f"Wrote {p.name}: {n} events")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
