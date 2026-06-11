"""Data quality helpers — gaps, splits, returns."""

from __future__ import annotations

import json
import math
import ssl
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .paths import HISTORY_MARKETS, PM_HISTORICAL


def _ssl_context():
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


def load_local_daily(ticker: str, local_json: str | None) -> list[dict[str, Any]]:
    if not local_json:
        return []
    path = HISTORY_MARKETS / local_json
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    return [{"date": b["date"], "close": float(b["close"])} for b in data.get("bars", []) if b.get("date")]


def fetch_yahoo_daily(ticker: str, start: str = "2015-01-01", end: str = "2026-12-31") -> list[dict[str, Any]]:
    start_ts = int(datetime.strptime(start, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp())
    end_ts = int(datetime.strptime(end, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp())
    qs = urllib.parse.urlencode({"interval": "1d", "period1": start_ts, "period2": end_ts})
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(ticker)}?{qs}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=30, context=_ssl_context()) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except Exception:
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
    out.sort(key=lambda x: x["date"])
    return out


def bars_to_daily(bars: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Collapse intraday bars to one close per calendar day (last bar of day)."""
    by_day: dict[str, float] = {}
    for b in bars:
        ts = b.get("ts", "")
        day = ts[:10]
        if day:
            by_day[day] = float(b["close"])
    return [{"date": d, "close": c} for d, c in sorted(by_day.items())]


def detect_gaps(daily: list[dict[str, Any]], max_gap_days: int = 5) -> dict[str, Any]:
    if len(daily) < 2:
        return {"gap_count": 0, "max_gap_days": 0, "has_material_gaps": False}
    dates = [datetime.strptime(b["date"], "%Y-%m-%d") for b in daily]
    gaps = []
    for i in range(1, len(dates)):
        delta = (dates[i] - dates[i - 1]).days
        if delta > 1:
            gaps.append({"from": daily[i - 1]["date"], "to": daily[i]["date"], "days": delta - 1})
    max_gap = max((g["days"] for g in gaps), default=0)
    material = [g for g in gaps if g["days"] >= max_gap_days]
    return {
        "gap_count": len(gaps),
        "max_gap_days": max_gap,
        "material_gaps": len(material),
        "has_material_gaps": len(material) > 0,
        "sample_gaps": gaps[:5],
    }


def detect_split_anomalies(daily: list[dict[str, Any]], threshold: float = 0.45) -> dict[str, Any]:
    """Flag single-day moves >45% as potential unadjusted split events."""
    flags = []
    for i in range(1, len(daily)):
        prev = daily[i - 1]["close"]
        cur = daily[i]["close"]
        if prev <= 0:
            continue
        chg = abs(cur / prev - 1.0)
        if chg >= threshold:
            flags.append({
                "date": daily[i]["date"],
                "prev_close": prev,
                "close": cur,
                "pct_change": round(chg * 100, 2),
            })
    return {
        "anomaly_count": len(flags),
        "likely_split_issues": len(flags) > 0,
        "flags": flags[:10],
    }


def daily_returns(daily: list[dict[str, Any]]) -> dict[str, float]:
    rets: dict[str, float] = {}
    for i in range(1, len(daily)):
        prev = daily[i - 1]["close"]
        cur = daily[i]["close"]
        if prev > 0:
            rets[daily[i]["date"]] = cur / prev - 1.0
    return rets


def pearson(xs: list[float], ys: list[float]) -> float:
    n = len(xs)
    if n < 3:
        return float("nan")
    mx = sum(xs) / n
    my = sum(ys) / n
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    dx = math.sqrt(sum((x - mx) ** 2 for x in xs))
    dy = math.sqrt(sum((y - my) ** 2 for y in ys))
    if dx == 0 or dy == 0:
        return float("nan")
    return num / (dx * dy)


def load_okx_hourly(asset: str) -> list[dict[str, Any]]:
    """Merge available OKX hourly files for BTC/ETH/SOL."""
    patterns = [
        PM_HISTORICAL / f"okx_{asset}_USDT_klines_may_2026.json",
        PM_HISTORICAL / f"okx_{asset}_USDT_klines_april_2026.json",
        PM_HISTORICAL / f"okx_{asset}_USDT_klines_march_2026.json",
    ]
    merged: dict[str, dict] = {}
    for path in patterns:
        if not path.exists():
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        rows = data if isinstance(data, list) else []
        for row in rows:
            ts = row.get("timestamp") or row.get("ts") or ""
            if ts:
                merged[ts] = row
    return sorted(merged.values(), key=lambda x: x.get("timestamp", x.get("ts", "")))
