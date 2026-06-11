#!/usr/bin/env python3
"""
Step 1–2: Build Historical Replay datasets under shared_intelligence/history/.

Learning-only. Does not touch agents/executors/risk/strategy.

Usage:
    python3 research/build_history_datasets.py [--skip-fetch]
"""

from __future__ import annotations

import json
import sys
from calendar import monthrange
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from research.history_paths import (  # noqa: E402
    EARNINGS_DIR,
    MACRO_DIR,
    MARKETS_DIR,
    MARKET_SYMBOLS,
    SHARED_ROOT,
    THEMES_DIR,
)
from research.build_event_calendars import (  # noqa: E402
    _EARNINGS_ANCHORS,
    _FOMC_DECISIONS,
    _cpi_release_proxy,
    _first_friday,
    _shift_to_weekday,
    _utc_iso,
)

_YEARS = tuple(range(2022, 2027))
_THEME_MAP_PATH = SHARED_ROOT / "events" / "theme_mapping.json"

# Sparse macro actuals (thousands for NFP jobs; % for CPI/PPI; bps for FOMC surprise proxy)
# Sources: public BLS/Fed headlines — enrichment layer; nulls allowed.
_MACRO_ACTUALS: dict[str, list[dict]] = {
    "NFP": [
        {"date": "2022-01-07", "actual": 199000, "expected": 400000},
        {"date": "2022-02-04", "actual": 467000, "expected": 150000},
        {"date": "2023-01-06", "actual": 223000, "expected": 200000},
        {"date": "2024-01-05", "actual": 216000, "expected": 180000},
        {"date": "2025-01-10", "actual": 256000, "expected": 165000},
    ],
    "CPI": [
        {"date": "2022-06-10", "actual": 8.6, "expected": 8.3},
        {"date": "2023-01-12", "actual": 6.5, "expected": 6.5},
        {"date": "2024-01-11", "actual": 3.4, "expected": 3.2},
        {"date": "2025-01-15", "actual": 2.9, "expected": 2.9},
    ],
    "PPI": [
        {"date": "2022-06-14", "actual": 10.8, "expected": 10.4},
        {"date": "2024-01-12", "actual": 1.0, "expected": 1.3},
    ],
}

_FOMC_2022_2023: dict[int, list[str]] = {
    2022: [
        "2022-01-26", "2022-03-16", "2022-05-04", "2022-06-15",
        "2022-07-27", "2022-09-21", "2022-11-02", "2022-12-14",
    ],
    2023: [
        "2023-02-01", "2023-03-22", "2023-05-03", "2023-06-14",
        "2023-07-26", "2023-09-20", "2023-11-01", "2023-12-13",
    ],
}

_YF_MAP = {
    "QQQ": "QQQ",
    "SOXL": "SOXL",
    "SOXS": "SOXS",
    "TQQQ": "TQQQ",
    "BTC": "BTC-USD",
    "ETH": "ETH-USD",
}


def _load_theme_map() -> dict:
    if _THEME_MAP_PATH.exists():
        return json.loads(_THEME_MAP_PATH.read_text(encoding="utf-8"))
    return {"event_labels": {}, "themes": []}


def _surprise(actual, expected):
    if actual is None or expected is None:
        return None
    try:
        return round(float(actual) - float(expected), 4)
    except (TypeError, ValueError):
        return None


def _lookup_macro_actual(event_type: str, d: date) -> dict:
    for row in _MACRO_ACTUALS.get(event_type, []):
        if row["date"] == d.isoformat():
            return row
    return {}


def _ppi_release_proxy(year: int, month: int) -> date:
    day = min(15, monthrange(year, month)[1])
    d = date(year, month, day)
    while d.weekday() >= 5:
        d += timedelta(days=1)
    return d


def _build_macro_events() -> list[dict]:
    theme_map = _load_theme_map()
    labels = theme_map.get("event_labels", {})
    rows: list[dict] = []

    for year in _YEARS:
        for month in range(1, 13):
            d = _first_friday(year, month)
            extra = _lookup_macro_actual("NFP", d)
            rows.append({
                "event": "NFP",
                "date": d.isoformat(),
                "actual": extra.get("actual"),
                "expected": extra.get("expected"),
                "surprise": _surprise(extra.get("actual"), extra.get("expected")),
                "theme": labels.get("NFP", "RATES"),
                "datetime_utc": _utc_iso(d, 13, 30),
            })

    for year in _YEARS:
        for month in range(1, 13):
            d = _cpi_release_proxy(year, month)
            extra = _lookup_macro_actual("CPI", d)
            rows.append({
                "event": "CPI",
                "date": d.isoformat(),
                "actual": extra.get("actual"),
                "expected": extra.get("expected"),
                "surprise": _surprise(extra.get("actual"), extra.get("expected")),
                "theme": labels.get("CPI", "INFLATION"),
                "datetime_utc": _utc_iso(d, 13, 30),
            })

    for year in _YEARS:
        for month in range(1, 13):
            d = _ppi_release_proxy(year, month)
            extra = _lookup_macro_actual("PPI", d)
            rows.append({
                "event": "PPI",
                "date": d.isoformat(),
                "actual": extra.get("actual"),
                "expected": extra.get("expected"),
                "surprise": _surprise(extra.get("actual"), extra.get("expected")),
                "theme": "INFLATION",
                "datetime_utc": _utc_iso(d, 13, 30),
            })

    fomc_all = dict(_FOMC_2022_2023)
    fomc_all.update(_FOMC_DECISIONS)
    for year in sorted(fomc_all):
        for ds in fomc_all[year]:
            d = date.fromisoformat(ds)
            rows.append({
                "event": "FOMC",
                "date": d.isoformat(),
                "actual": None,
                "expected": None,
                "surprise": None,
                "theme": labels.get("FOMC", "RATES"),
                "datetime_utc": _utc_iso(d, 18, 0),
            })

    rows.sort(key=lambda r: r["date"])
    return rows


def _build_earnings_events() -> list[dict]:
    theme_map = _load_theme_map()
    labels = theme_map.get("event_labels", {})
    rows: list[dict] = []

    actual_path = SHARED_ROOT / "events" / "earnings_actual_calendar.json"
    if actual_path.exists():
        for ev in json.loads(actual_path.read_text())["events"]:
            ticker = ev.get("ticker", "")
            label = ev.get("label", f"{ticker}_EARNINGS")
            day = (ev.get("event_time") or "")[:10]
            rows.append({
                "date": day,
                "ticker": ticker,
                "event": label,
                "eps_actual": None,
                "eps_expected": None,
                "guidance": None,
                "theme": labels.get(label, "AI"),
                "datetime_utc": ev.get("event_time"),
                "source": ev.get("source", "earnings_actual"),
            })

    seen = {(r["ticker"], r["date"]) for r in rows}
    for ticker, anchors in _EARNINGS_ANCHORS.items():
        for year in (2022, 2023):
            for month, day in anchors:
                d = _shift_to_weekday(date(year, month, min(day, monthrange(year, month)[1])))
                key = (ticker, d.isoformat())
                if key in seen:
                    continue
                label = f"{ticker}_EARNINGS"
                rows.append({
                    "date": d.isoformat(),
                    "ticker": ticker,
                    "event": label,
                    "eps_actual": None,
                    "eps_expected": None,
                    "guidance": None,
                    "theme": labels.get(label, "AI"),
                    "datetime_utc": _utc_iso(d, 21, 0),
                    "source": "proxy:quarterly_anchor",
                })

    rows.sort(key=lambda r: r["date"])
    return rows


def _ssl_context():
    """macOS Homebrew Python often lacks system CA bundle — use certifi."""
    import ssl

    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        return ssl.create_default_context()


def _fetch_stooq_daily(symbol: str, start: str, end: str) -> list[dict]:
    """Fallback: Stooq daily CSV (US ETFs)."""
    import csv
    import io
    import urllib.parse
    import urllib.request

    stooq_sym = f"{symbol.lower()}.us"
    url = f"https://stooq.com/q/d/l/?s={stooq_sym}&i=d"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=30, context=_ssl_context()) as resp:
            text = resp.read().decode("utf-8", errors="replace")
    except Exception as exc:
        print(f"  [warn] Stooq fetch failed for {symbol}: {exc}")
        return []
    reader = csv.DictReader(io.StringIO(text))
    out = []
    for row in reader:
        d = (row.get("Date") or "")[:10]
        if not d or d < start or d > end:
            continue
        try:
            close = float(row.get("Close") or 0)
        except (TypeError, ValueError):
            continue
        if close > 0:
            out.append({"date": d, "close": round(close, 6)})
    out.sort(key=lambda x: x["date"])
    return out


def _fetch_yahoo_chart_daily(symbol: str, start: str, end: str) -> list[dict]:
    """Fetch daily closes via Yahoo chart API (no yfinance dependency)."""
    import urllib.parse
    import urllib.request

    ticker = _YF_MAP[symbol]
    start_ts = int(datetime.strptime(start, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp())
    end_ts = int(datetime.strptime(end, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp())
    qs = urllib.parse.urlencode({
        "interval": "1d",
        "period1": start_ts,
        "period2": end_ts,
    })
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?{qs}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=30, context=_ssl_context()) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except Exception as exc:
        print(f"  [warn] Yahoo fetch failed for {symbol}: {exc}")
        return []
    result = (payload.get("chart") or {}).get("result") or []
    if not result:
        return []
    timestamps = result[0].get("timestamp") or []
    closes = ((result[0].get("indicators") or {}).get("quote") or [{}])[0].get("close") or []
    out = []
    for ts, close in zip(timestamps, closes):
        if close is None:
            continue
        d = datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d")
        out.append({"date": d, "close": round(float(close), 6)})
    return out


def _fetch_yfinance_daily(symbol: str, start: str, end: str) -> list[dict]:
    rows = _fetch_yahoo_chart_daily(symbol, start, end)
    if rows:
        return rows
    if symbol in ("QQQ", "SOXL", "SOXS", "TQQQ"):
        rows = _fetch_stooq_daily(symbol, start, end)
        if rows:
            print(f"  [info] {symbol}: loaded {len(rows)} bars from Stooq fallback")
            return rows
    try:
        import yfinance as yf
    except ImportError:
        return []
    try:
        df = yf.download(_YF_MAP[symbol], start=start, end=end, progress=False, auto_adjust=True)
    except Exception:
        return []
    if df is None or df.empty:
        return []
    out = []
    for idx, row in df.iterrows():
        close = row.get("Close") if hasattr(row, "get") else row["Close"]
        if hasattr(close, "iloc"):
            close = float(close.iloc[0]) if len(close) else None
        else:
            close = float(close)
        out.append({
            "date": idx.strftime("%Y-%m-%d") if hasattr(idx, "strftime") else str(idx)[:10],
            "close": round(close, 6),
        })
    return out


def _load_local_okx_daily(symbol: str, hist_dir: Path) -> list[dict]:
    """Aggregate hourly OKX klines → daily close (fallback for crypto)."""
    patterns = {
        "BTC": "okx_BTC_USDT_klines*.json",
        "ETH": "okx_ETH_USDT_klines*.json",
    }
    if symbol not in patterns:
        return []
    files = sorted(hist_dir.glob(patterns[symbol]))
    if not files:
        return []
    by_day: dict[str, float] = {}
    for fp in files:
        try:
            rows = json.loads(fp.read_text(encoding="utf-8"))
        except Exception:
            continue
        for bar in rows:
            ts = str(bar.get("timestamp", ""))[:10]
            close = bar.get("close")
            if ts and close is not None:
                by_day[ts] = float(close)
    return [{"date": d, "close": by_day[d]} for d in sorted(by_day)]


def build_market_series(skip_fetch: bool = False) -> dict[str, list[dict]]:
    MARKETS_DIR.mkdir(parents=True, exist_ok=True)
    hist_dir = _ROOT / "data" / "historical"
    series: dict[str, list[dict]] = {}

    for sym in MARKET_SYMBOLS:
        daily: list[dict] = []
        if not skip_fetch:
            daily = _fetch_yfinance_daily(sym, "2022-01-01", "2026-12-31")
        if not daily and sym in ("BTC", "ETH"):
            daily = _load_local_okx_daily(sym, hist_dir)
        series[sym] = daily
        out = {
            "symbol": sym,
            "source": "yfinance" if daily and not skip_fetch else "local_okx_or_empty",
            "start": daily[0]["date"] if daily else None,
            "end": daily[-1]["date"] if daily else None,
            "bars": daily,
        }
        (MARKETS_DIR / f"{sym}.json").write_text(
            json.dumps(out, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
    return series


def compute_event_returns(events: list[dict], series: dict[str, list[dict]]) -> list[dict]:
    """Attach {SYM}_{n}D return fields to each event row."""
    index: dict[str, dict[str, float]] = {}
    dates: dict[str, list[str]] = {}
    for sym, bars in series.items():
        dates[sym] = [b["date"] for b in bars]
        index[sym] = {b["date"]: b["close"] for b in bars}

    enriched = []
    for ev in events:
        row = dict(ev)
        event_date = row.get("date", "")
        for sym in MARKET_SYMBOLS:
            dlist = dates.get(sym) or []
            if not dlist:
                continue
            # last close on or before event date
            base_i = None
            for i, d in enumerate(dlist):
                if d <= event_date:
                    base_i = i
                else:
                    break
            if base_i is None:
                continue
            base_px = index[sym][dlist[base_i]]
            for h in (1, 3, 5, 10):
                tgt_i = base_i + h
                key = f"{sym}_{h}D"
                if tgt_i < len(dlist):
                    tgt_px = index[sym][dlist[tgt_i]]
                    row[key] = round((tgt_px - base_px) / base_px * 100, 4) if base_px else None
                else:
                    row[key] = None
        enriched.append(row)
    return enriched


def write_themes_manifest() -> None:
    THEMES_DIR.mkdir(parents=True, exist_ok=True)
    theme_map = _load_theme_map()
    manifest = {
        "version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "themes": theme_map.get("themes", []),
        "event_theme_map": theme_map.get("event_labels", {}),
        "symbol_theme_map": theme_map.get("symbol_themes", {}),
        "descriptions": theme_map.get("theme_descriptions", {}),
    }
    (THEMES_DIR / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-fetch", action="store_true", help="Skip yfinance download")
    args = parser.parse_args()

    MACRO_DIR.mkdir(parents=True, exist_ok=True)
    EARNINGS_DIR.mkdir(parents=True, exist_ok=True)

    macro = _build_macro_events()
    (MACRO_DIR / "macro_events.json").write_text(
        json.dumps({"events": macro, "count": len(macro)}, indent=2) + "\n",
        encoding="utf-8",
    )
    for ev_type in ("NFP", "CPI", "PPI", "FOMC"):
        subset = [e for e in macro if e["event"] == ev_type]
        (MACRO_DIR / f"{ev_type.lower()}.json").write_text(
            json.dumps({"events": subset, "count": len(subset)}, indent=2) + "\n",
            encoding="utf-8",
        )

    earnings = _build_earnings_events()
    (EARNINGS_DIR / "earnings_events.json").write_text(
        json.dumps({"events": earnings, "count": len(earnings)}, indent=2) + "\n",
        encoding="utf-8",
    )

    write_themes_manifest()
    series = build_market_series(skip_fetch=args.skip_fetch)

    # Pre-compute market replay slices (events + returns) for joiner fast path
    macro_with_returns = compute_event_returns(macro, series)
    earn_with_returns = compute_event_returns(earnings, series)
    (MARKETS_DIR / "macro_replay.json").write_text(
        json.dumps({"events": macro_with_returns}, indent=2) + "\n",
        encoding="utf-8",
    )
    (MARKETS_DIR / "earnings_replay.json").write_text(
        json.dumps({"events": earn_with_returns}, indent=2) + "\n",
        encoding="utf-8",
    )

    print(f"macro events: {len(macro)}")
    print(f"earnings events: {len(earnings)}")
    for sym in MARKET_SYMBOLS:
        print(f"  market {sym}: {len(series.get(sym, []))} daily bars")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
