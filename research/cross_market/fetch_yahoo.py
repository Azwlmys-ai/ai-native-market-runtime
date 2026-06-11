"""Yahoo chart API daily fetch — research-only, no trading deps."""

from __future__ import annotations

import json
import ssl
import urllib.parse
import urllib.request
from datetime import datetime, timezone


def _ssl_context():
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


def fetch_yahoo_daily(ticker: str, start: str, end: str) -> list[dict]:
    """Return [{date, close}, ...] sorted ascending."""
    start_ts = int(datetime.strptime(start, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp())
    end_ts = int(datetime.strptime(end, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp())
    qs = urllib.parse.urlencode({"interval": "1d", "period1": start_ts, "period2": end_ts})
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(ticker)}?{qs}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=30, context=_ssl_context()) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except Exception as exc:
        print(f"  [warn] Yahoo fetch failed for {ticker}: {exc}")
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
