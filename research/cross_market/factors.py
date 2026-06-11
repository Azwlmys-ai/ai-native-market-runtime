"""Compute global factor composites from daily closes."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .config import FACTORS
from .paths import CHINA_DIR, FLOWS_DIR, MACRO_DIR, MARKETS_DIR


def load_bars(path: Path) -> list[dict]:
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    return data.get("bars") or []


def bars_to_returns(bars: list[dict]) -> dict[str, float]:
    """date -> daily pct return."""
    sorted_bars = sorted(bars, key=lambda x: x["date"])
    out: dict[str, float] = {}
    prev = None
    for b in sorted_bars:
        c = b.get("close")
        if c is None:
            continue
        if prev is not None and prev > 0:
            out[b["date"]] = (float(c) - prev) / prev
        prev = float(c)
    return out


def composite_returns(symbols: dict[str, str], root: Path = MARKETS_DIR) -> dict[str, float]:
    """Equal-weight average of constituent daily returns."""
    all_rets: list[dict[str, float]] = []
    for label in symbols:
        path = root / f"{label}.json"
        if not path.exists() and label in ("DXY", "US10Y", "US2Y"):
            path = MACRO_DIR / f"{label}.json"
        bars = load_bars(path)
        if bars:
            all_rets.append(bars_to_returns(bars))
    if not all_rets:
        return {}
    dates = set()
    for r in all_rets:
        dates.update(r.keys())
    out: dict[str, float] = {}
    for d in sorted(dates):
        vals = [r[d] for r in all_rets if d in r]
        if vals:
            out[d] = sum(vals) / len(vals)
    return out


def build_all_factors() -> dict[str, dict[str, float]]:
    factors: dict[str, dict[str, float]] = {}
    for fid, fdef in FACTORS.items():
        root = MACRO_DIR if fdef["category"] == "macro" else MARKETS_DIR
        factors[fid] = composite_returns(fdef["symbols"], root)
    return factors


def load_series_returns(name: str) -> dict[str, float]:
    """Load single series returns by symbol/key."""
    paths = [
        MARKETS_DIR / f"{name}.json",
        MACRO_DIR / f"{name}.json",
        CHINA_DIR / f"{name}.json",
        FLOWS_DIR / f"{name}.json",
    ]
    for p in paths:
        bars = load_bars(p)
        if bars:
            return bars_to_returns(bars)
    return {}


def load_flow_levels(name: str = "northbound") -> dict[str, float]:
    """Raw flow levels (not returns) for northbound."""
    bars = load_bars(FLOWS_DIR / f"{name}.json")
    return {b["date"]: float(b["close"]) for b in bars if b.get("close") is not None}


def factor_summary(factors: dict[str, dict[str, float]]) -> list[dict[str, Any]]:
    rows = []
    for fid, rets in factors.items():
        if not rets:
            rows.append({"factor": fid, "name": FACTORS[fid]["name"], "days": 0, "last_return": None})
            continue
        last_date = max(rets.keys())
        rows.append({
            "factor": fid,
            "name": FACTORS[fid]["name"],
            "days": len(rets),
            "last_date": last_date,
            "last_return": round(rets[last_date] * 100, 4),
        })
    return rows
