"""Shared helpers for historical replay learning (Phase 3)."""

from __future__ import annotations

import json
import math
from pathlib import Path

from research.history_paths import (
    EARNINGS_DIR,
    HISTORY_ROOT,
    MACRO_DIR,
    MARKETS_DIR,
    MARKET_SYMBOLS,
    RETURN_HORIZONS,
)

_PM_PROXY_THEMES = {
    "AI": 0.6,
    "RATES": 0.4,
    "INFLATION": 0.5,
    "SEMICONDUCTORS": 0.7,
    "CRYPTO": 0.3,
    "ENERGY": 0.35,
}


def load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def return_keys(symbol: str) -> list[str]:
    return [f"{symbol}_{h}D" for h in RETURN_HORIZONS]


def market_bucket(symbol: str) -> str:
    if symbol in ("BTC", "ETH"):
        return "crypto"
    return "etf"


def confidence_from_sample(n: int, std: float, mean: float) -> float:
    """Heuristic confidence in [0,1]: more samples + lower relative dispersion → higher."""
    if n < 3:
        return round(min(0.35, n / 10), 2)
    rel = abs(std / mean) if mean else 1.0
    base = min(0.95, 0.45 + math.log1p(n) / 8)
    penalty = min(0.4, rel / 5)
    return round(max(0.1, min(0.99, base - penalty)), 2)


def t_statistic(mean: float, std: float, n: int) -> float:
    if n < 2 or std == 0:
        return 0.0
    return abs(mean) / (std / math.sqrt(n))


def is_significant(mean: float, std: float, n: int, baseline: float, min_n: int = 30) -> bool:
    if n < min_n:
        return False
    if std == 0:
        return abs(mean - baseline) > 0.5
    # lightweight: |t|>2 and |mean-baseline|>0.5pp
    return t_statistic(mean - baseline, std, n) >= 2.0 and abs(mean - baseline) >= 0.5


def load_replay_source_events() -> list[dict]:
    rows: list[dict] = []
    for path in (
        MARKETS_DIR / "macro_replay.json",
        MARKETS_DIR / "earnings_replay.json",
    ):
        payload = load_json(path)
        for ev in payload.get("events", []):
            ev = dict(ev)
            ev.setdefault("event_class", "macro" if "eps_actual" not in ev else "earnings")
            rows.append(ev)
    if rows:
        return rows

    # fallback before market replay built
    macro = load_json(MACRO_DIR / "macro_events.json").get("events", [])
    earn = load_json(EARNINGS_DIR / "earnings_events.json").get("events", [])
    for ev in macro:
        r = dict(ev)
        r["event_class"] = "macro"
        rows.append(r)
    for ev in earn:
        r = dict(ev)
        r["event_class"] = "earnings"
        rows.append(r)
    return rows


def polymarket_proxy_return(theme: str, etf_return: float, crypto_return: float) -> float:
    """Synthetic PM reaction proxy when no historical PM tape (learning-only)."""
    w = _PM_PROXY_THEMES.get(theme, 0.4)
    return round(w * etf_return + (1 - w) * crypto_return * 0.5, 4)
