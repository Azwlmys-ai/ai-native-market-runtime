"""Load event calendars + themes from shared_intelligence (read-only)."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

_SHARED = Path("/Users/libo/shared_intelligence")
_SHARED_EVENTS = _SHARED / "events"

_MACRO_CALENDARS = (
    "nfp_calendar.json",
    "cpi_calendar.json",
    "fomc_calendar.json",
)

_DEFAULT_WINDOWS: dict[str, tuple[float, float]] = {
    "NFP": (2, 24),
    "CPI": (2, 24),
    "FOMC": (4, 48),
    "EARNINGS": (12, 72),
}

# Semiconductor / mega-cap proxies for earnings → ETF symbol tagging
_EARNINGS_SYMBOL_MAP: dict[str, set[str]] = {
    "NVDA": {"NVDA", "NVDL", "NVDQ", "SOXL", "SOXS"},
    "AVGO": {"AVGO", "SOXL", "SOXS", "NVDL"},
    "TSLA": {"TSLA", "TSLL", "TSLQ"},
    "AAPL": {"AAPL"},
    "MSFT": {"MSFT"},
    "META": {"META"},
    "AMZN": {"AMZN"},
}


def parse_utc(raw: str) -> datetime:
    return datetime.fromisoformat(raw.replace("Z", "+00:00"))


def event_datetime(ev: dict) -> datetime:
    raw = ev.get("event_time") or ev.get("datetime_utc", "")
    return parse_utc(raw)


def event_windows(ev: dict) -> tuple[float, float]:
    if "pre_window_hours" in ev and "post_window_hours" in ev:
        return float(ev["pre_window_hours"]), float(ev["post_window_hours"])
    return _DEFAULT_WINDOWS.get(ev.get("type", ""), (24, 24))


def load_theme_mapping(path: Path | None = None) -> dict:
    p = path or (_SHARED_EVENTS / "theme_mapping.json")
    if not p.exists():
        return {"event_labels": {}, "symbol_themes": {}}
    return json.loads(p.read_text(encoding="utf-8"))


def themes_for_trade(
    event_labels: list[str],
    symbol: str,
    mapping: dict,
) -> list[str]:
    themes: set[str] = set()
    for label in event_labels:
        t = mapping.get("event_labels", {}).get(label)
        if t:
            themes.add(t)
    for t in mapping.get("symbol_themes", {}).get((symbol or "").upper(), []):
        themes.add(t)
    return sorted(themes)


def load_all_events(events_dir: Path = _SHARED_EVENTS) -> list[dict]:
    """Load macro calendars + verified earnings (proxy earnings excluded)."""
    events: list[dict] = []

    for name in _MACRO_CALENDARS:
        path = events_dir / name
        if not path.exists():
            continue
        payload = json.loads(path.read_text(encoding="utf-8"))
        for ev in payload.get("events", []):
            row = dict(ev)
            row["_calendar"] = payload.get("calendar", name.replace("_calendar.json", ""))
            pre, post = event_windows(row)
            row.setdefault("pre_window_hours", pre)
            row.setdefault("post_window_hours", post)
            events.append(row)

    actual_path = events_dir / "earnings_actual_calendar.json"
    if actual_path.exists():
        payload = json.loads(actual_path.read_text(encoding="utf-8"))
        for ev in payload.get("events", []):
            row = dict(ev)
            row["_calendar"] = "earnings_actual"
            pre, post = event_windows(row)
            row.setdefault("pre_window_hours", pre)
            row.setdefault("post_window_hours", post)
            events.append(row)

    events.sort(key=lambda e: event_datetime(e).isoformat())
    return events


def related_symbols(event: dict) -> set[str] | None:
    ticker = event.get("ticker")
    if not ticker:
        return None
    return _EARNINGS_SYMBOL_MAP.get(ticker.upper())


def trade_overlaps_event_window(
    entry_time: datetime,
    exit_time: datetime,
    ev: dict,
) -> bool:
    ev_dt = event_datetime(ev)
    pre_h, post_h = event_windows(ev)
    win_start = ev_dt - timedelta(hours=pre_h)
    win_end = ev_dt + timedelta(hours=post_h)
    return entry_time <= win_end and exit_time >= win_start


def events_near_trade(
    entry_time: datetime,
    events: list[dict],
    *,
    exit_time: datetime | None = None,
    symbol: str | None = None,
) -> list[str]:
    """Asymmetric pre/post windows (Phase 2.1). Observation only."""
    exit_time = exit_time or entry_time
    sym = (symbol or "").upper()
    matched: list[str] = []

    for ev in events:
        if ev.get("type") == "EARNINGS":
            rel = related_symbols(ev)
            if rel is not None and sym and sym not in rel:
                continue

        if trade_overlaps_event_window(entry_time, exit_time, ev):
            matched.append(ev["label"])

    return sorted(set(matched))
