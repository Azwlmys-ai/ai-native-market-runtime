"""LongBridge API probes — read-only, no trading context."""

from __future__ import annotations

import os
import time
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from .paths import LONGBRIDGE_ENV

_RATE_SLEEP = 0.5
_CHUNK_DAYS_5M = 10
_CHUNK_DAYS_1H = 60
_CHUNK_DAYS_1D = 365


def _load_env() -> None:
    if not LONGBRIDGE_ENV.exists():
        return
    for line in LONGBRIDGE_ENV.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"'))


def _has_credentials() -> bool:
    _load_env()
    return bool(os.environ.get("LONGBRIDGE_APP_KEY"))


def _get_ctx():
    from longport.openapi import AdjustType, Config, Period, QuoteContext

    _load_env()
    config = Config(
        app_key=os.environ["LONGBRIDGE_APP_KEY"],
        app_secret=os.environ["LONGBRIDGE_APP_SECRET"],
        access_token=os.environ["LONGBRIDGE_ACCESS_TOKEN"],
    )
    return QuoteContext(config), Period, AdjustType


def probe_quote(symbol: str) -> dict[str, Any]:
    if not _has_credentials():
        return {"ok": False, "error": "no_credentials"}
    try:
        ctx, _, _ = _get_ctx()
        rows = ctx.quote([symbol])
        q = rows[0] if rows else None
        last = getattr(q, "last_done", None) if q else None
        return {"ok": True, "last_done": float(last) if last is not None else None}
    except Exception as exc:
        return {"ok": False, "error": str(exc)[:200]}


def probe_static(symbol: str) -> dict[str, Any]:
    if not _has_credentials():
        return {"ok": False, "error": "no_credentials"}
    try:
        ctx, _, _ = _get_ctx()
        rows = ctx.static_info([symbol])
        info = rows[0] if rows else None
        if not info:
            return {"ok": False, "error": "empty"}
        return {
            "ok": True,
            "name_en": getattr(info, "name_en", None),
            "name_cn": getattr(info, "name_cn", None),
            "board": str(getattr(info, "board", "")),
            "exchange": getattr(info, "exchange", None),
            "currency": getattr(info, "currency", None),
        }
    except Exception as exc:
        return {"ok": False, "error": str(exc)[:200]}


def _fetch_chunked(
    symbol: str,
    period_name: str,
    start: date,
    end: date,
    chunk_days: int,
) -> list[dict[str, Any]]:
    ctx, Period, AdjustType = _get_ctx()
    period_map = {
        "1d": Period.Day,
        "60m": Period.Min_60,
        "5m": Period.Min_5,
    }
    period = period_map[period_name]
    bars_out: list[dict[str, Any]] = []
    seen: set[str] = set()
    cur = start
    while cur <= end:
        chunk_end = min(cur + timedelta(days=chunk_days - 1), end)
        try:
            bars = ctx.history_candlesticks_by_date(
                symbol=symbol,
                period=period,
                adjust_type=AdjustType.NoAdjust,
                start=cur,
                end=chunk_end,
            )
        except Exception:
            bars = []
        for b in bars or []:
            ts = str(b.timestamp)
            if ts in seen:
                continue
            seen.add(ts)
            bars_out.append({
                "ts": ts,
                "open": float(b.open),
                "high": float(b.high),
                "low": float(b.low),
                "close": float(b.close),
                "volume": float(getattr(b, "volume", 0) or 0),
            })
        cur = chunk_end + timedelta(days=1)
        time.sleep(_RATE_SLEEP)
    bars_out.sort(key=lambda x: x["ts"])
    return bars_out


def probe_history_window(
    symbol: str,
    period: str,
    start: date,
    end: date,
) -> dict[str, Any]:
    """Single-call history probe (no pagination) — for availability audit."""
    if not _has_credentials():
        return {"ok": False, "error": "no_credentials", "bars": []}
    try:
        ctx, Period, AdjustType = _get_ctx()
        period_map = {"1d": Period.Day, "60m": Period.Min_60, "5m": Period.Min_5}
        bars = ctx.history_candlesticks_by_date(
            symbol=symbol,
            period=period_map[period],
            adjust_type=AdjustType.NoAdjust,
            start=start,
            end=end,
        )
        out = []
        for b in bars or []:
            out.append({
                "ts": str(b.timestamp),
                "close": float(b.close),
            })
        out.sort(key=lambda x: x["ts"])
        return {"ok": True, "bars": out, "count": len(out)}
    except Exception as exc:
        return {"ok": False, "error": str(exc)[:200], "bars": []}


def fetch_history(
    symbol: str,
    period: str,
    start: date | None = None,
    end: date | None = None,
) -> dict[str, Any]:
    if not _has_credentials():
        return {"ok": False, "error": "no_credentials", "bars": []}
    end = end or date.today()
    start = start or date(2015, 1, 1)
    chunk = {"1d": _CHUNK_DAYS_1D, "60m": _CHUNK_DAYS_1H, "5m": _CHUNK_DAYS_5M}[period]
    try:
        bars = _fetch_chunked(symbol, period, start, end, chunk)
        return {"ok": True, "bars": bars, "count": len(bars)}
    except Exception as exc:
        return {"ok": False, "error": str(exc)[:200], "bars": []}


def probe_cp00048_constituents() -> dict[str, Any]:
    """Best-effort constituent probe — OpenAPI has no dedicated sector-members endpoint."""
    result: dict[str, Any] = {
        "constituent_api_available": False,
        "constituents": [],
        "notes": [],
    }
    if not _has_credentials():
        result["notes"].append("LongBridge credentials unavailable")
        return result

    static = probe_static("CP00048.US")
    result["static"] = static
    result["notes"].append(
        "static_info board=USSector → LongBridge custom US sector/theme index (Blockchain)"
    )
    result["notes"].append(
        "OpenAPI QuoteContext has no sector-constituent/members endpoint; "
        "constituent list not retrievable via current SDK"
    )

    try:
        from longport.openapi import CalcIndex
        ctx, _, _ = _get_ctx()
        calc = ctx.calc_indexes(["CP00048.US"], [CalcIndex.LastDone])
        if calc:
            result["calc_index_last"] = float(getattr(calc[0], "last_done", 0) or 0)
    except Exception as exc:
        result["notes"].append(f"calc_indexes probe: {exc}")

    return result
