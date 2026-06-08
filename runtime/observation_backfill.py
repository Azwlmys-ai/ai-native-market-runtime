"""
observation_backfill — Phase 3d Observation 缺口补齐（只读源 → 写 historical/research）

不写 signals / review / execution。所有产出 observation_only=true。
"""

from __future__ import annotations

import json
import re
import sqlite3
import statistics
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator, Optional

OKX_FUNDING_FEATHER = Path(
    "/Users/libo/okx_perp_trader/env_rule/user_data/data/okx/futures"
)
FEATHER_SYMBOL_MAP = {
    "BTC_USDT_USDT-1h-funding_rate.feather": "BTC",
    "ETH_USDT_USDT-1h-funding_rate.feather": "ETH",
}
CRYPTO_ASSET_KEYS = (
    ("bitcoin", "BTC"),
    ("btc", "BTC"),
    ("ethereum", "ETH"),
    (" eth", "ETH"),
    ("solana", "SOL"),
    (" sol ", "SOL"),
    ("crypto", "CRYPTO"),
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_ts(ts: str) -> str:
    return (ts or "").strip().replace("Z", "+00:00")


def _infer_asset(text: str) -> str:
    t = f" {text.lower()} "
    for key, asset in CRYPTO_ASSET_KEYS:
        if key in t:
            return asset
    return "CRYPTO"


def _is_crypto_market(slug: str, question: str = "") -> bool:
    text = f"{slug} {question}".lower()
    tokens = set(re.findall(r"[a-z0-9]+", text))
    crypto_tokens = {
        "bitcoin", "btc", "ethereum", "eth", "solana", "sol", "crypto", "megaeth",
    }
    return bool(tokens & crypto_tokens)


def _read_feather_funding(path: Path, symbol: str) -> list[dict]:
    try:
        import pyarrow.feather as ft  # type: ignore
    except ImportError:
        return []
    if not path.exists():
        return []
    table = ft.read_table(path)
    data = table.to_pydict()
    dates = data.get("date") or []
    # Freqtrade funding feather stores rate in `open` for this dataset.
    rates = data.get("open") or data.get("close") or []
    rows = []
    for i, dt in enumerate(dates):
        if i >= len(rates):
            break
        rate = rates[i]
        if rate is None:
            continue
        if hasattr(dt, "isoformat"):
            ts = dt.isoformat()
        else:
            ts = str(dt)
        rows.append({
            "timestamp": _normalize_ts(ts),
            "exchange": "okx",
            "symbol": symbol,
            "funding_rate": float(rate),
            "source_file": str(path),
            "observation_only": True,
        })
    return rows


def _read_json_funding(path: Path, symbol: str) -> list[dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        return []
    rows = []
    for item in data:
        ts = item.get("timestamp")
        fr = item.get("funding_rate")
        if not ts or fr is None:
            continue
        rows.append({
            "timestamp": _normalize_ts(str(ts)),
            "exchange": "okx",
            "symbol": symbol,
            "funding_rate": float(fr),
            "source_file": str(path),
            "observation_only": True,
        })
    return rows


def collect_funding_observations(base_dir: Path) -> tuple[list[dict], dict]:
    """Read-only merge of local JSON + OKX feather. SOL missing is reported, not fabricated."""
    hist = base_dir / "data" / "historical"
    merged: dict[tuple[str, str], dict] = {}
    stats: dict = {"symbols": {}, "missing_symbols": []}

    class _Counts:
        def __init__(self):
            self.data: dict[str, int] = defaultdict(int)

        def inc(self, k: str, n: int = 1):
            self.data[k] += n

    sources = _Counts()

    for symbol in ("BTC", "ETH", "SOL"):
        sym_rows: list[dict] = []
        json_files = sorted(hist.glob(f"okx_{symbol}_USDT_SWAP_funding_rate_*.json"))
        for p in json_files:
            rows = _read_json_funding(p, symbol)
            sym_rows.extend(rows)
            sources.inc("json", len(rows))

        if symbol in ("BTC", "ETH"):
            for fname, fsym in FEATHER_SYMBOL_MAP.items():
                if fsym != symbol:
                    continue
                fpath = OKX_FUNDING_FEATHER / fname
                frows = _read_feather_funding(fpath, symbol)
                sym_rows.extend(frows)
                sources.inc("feather", len(frows))

        if not sym_rows and symbol == "SOL":
            stats["missing_symbols"].append({
                "symbol": "SOL",
                "reason": "no_local_json_or_feather",
                "fabricated": False,
            })
            stats["symbols"][symbol] = {"rows": 0, "status": "missing"}
            continue

        for row in sym_rows:
            key = (row["symbol"], row["timestamp"])
            if key not in merged:
                merged[key] = row
            elif "okx_" in merged[key]["source_file"] and merged[key]["source_file"].endswith(".json"):
                pass  # keep JSON
            else:
                merged[key] = row

        stats["symbols"][symbol] = {
            "rows": sum(1 for k, v in merged.items() if k[0] == symbol),
            "status": "ok" if sym_rows else "missing",
            "json_files": len(json_files),
        }

    ordered = sorted(merged.values(), key=lambda r: (r["symbol"], r["timestamp"]))
    stats["total_rows"] = len(ordered)
    stats["source_counts"] = dict(sources.data)
    stats["feather_available"] = bool(sources.data.get("feather"))
    return ordered, stats


def write_funding_rates_jsonl(base_dir: Path) -> dict:
    rows, stats = collect_funding_observations(base_dir)
    out = base_dir / "data" / "historical" / "funding_rates.jsonl"
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    stats["output_path"] = str(out)
    stats["generated_at"] = _now_iso()
    summary_path = base_dir / "research" / "funding_backfill_summary.json"
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(stats, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    stats["summary_path"] = str(summary_path)
    return stats


def load_funding_rates_jsonl(base_dir: Path, symbol: str = "BTC") -> list[dict]:
    p = base_dir / "data" / "historical" / "funding_rates.jsonl"
    if not p.exists():
        return []
    rows = []
    with open(p, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            if row.get("symbol") == symbol and row.get("observation_only") is True:
                rows.append(row)
    return rows


def funding_daily_from_jsonl(base_dir: Path, symbol: str = "BTC") -> list[tuple[str, float]]:
    by_day: dict[str, list[float]] = defaultdict(list)
    for row in load_funding_rates_jsonl(base_dir, symbol=symbol):
        day = row["timestamp"][:10]
        by_day[day].append(float(row["funding_rate"]))
    return [(d, statistics.mean(v)) for d, v in sorted(by_day.items())]


def _slug_map_from_db(base_dir: Path) -> dict[str, str]:
    db = base_dir / "data" / "runtime.db"
    if not db.exists():
        return {}
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        return {
            str(mid): str(slug or "")
            for mid, slug in conn.execute(
                "SELECT DISTINCT market_id, slug FROM market_prices WHERE slug IS NOT NULL"
            )
        }
    finally:
        conn.close()


def collect_pm_crypto_live_tape(base_dir: Path) -> tuple[list[dict], dict]:
    """Build live PM crypto tape from market_price_history + runtime.db slugs only."""
    mph_path = base_dir / "data" / "market_price_history.json"
    stats: dict = {"markets": [], "missing": []}
    if not mph_path.exists():
        stats["missing"].append("market_price_history.json")
        return [], stats

    slug_map = _slug_map_from_db(base_dir)
    mph = json.loads(mph_path.read_text(encoding="utf-8"))
    rows: list[dict] = []

    for market_id, points in mph.items():
        slug = slug_map.get(str(market_id), "")
        if not _is_crypto_market(slug):
            continue
        yes_prices = [float(p["yes_price"]) for p in points if p.get("yes_price") is not None]
        low_info = len(yes_prices) >= 2 and min(yes_prices) == max(yes_prices)
        asset = _infer_asset(slug)
        stats["markets"].append({
            "market_id": str(market_id),
            "slug": slug,
            "asset": asset,
            "points": len(points),
            "low_information": low_info,
        })
        for pt in points:
            ts = pt.get("ts") or ""
            price = pt.get("yes_price")
            if price is None:
                continue
            rows.append({
                "timestamp": _normalize_ts(str(ts)),
                "market_id": str(market_id),
                "slug": slug,
                "asset": asset,
                "outcome": "yes",
                "price": float(price),
                "liquidity": float(pt["liquidity"]) if pt.get("liquidity") is not None else None,
                "source": "market_price_history.json",
                "observation_only": True,
                "low_information": low_info,
                "live": True,
            })

    stats["total_rows"] = len(rows)
    stats["market_count"] = len(stats["markets"])
    return rows, stats


def write_pm_crypto_price_tape_jsonl(base_dir: Path) -> dict:
    rows, stats = collect_pm_crypto_live_tape(base_dir)
    out = base_dir / "data" / "historical" / "pm_crypto_price_tape.jsonl"
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    stats["output_path"] = str(out)
    stats["generated_at"] = _now_iso()
    summary = base_dir / "research" / "pm_crypto_tape_summary.json"
    summary.parent.mkdir(parents=True, exist_ok=True)
    summary.write_text(json.dumps(stats, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    stats["summary_path"] = str(summary)
    return stats


def pm_crypto_daily_returns(base_dir: Path, asset: str = "BTC") -> list[tuple[str, float]]:
    """Daily returns from live PM crypto tape (primary asset market, yes outcome)."""
    p = base_dir / "data" / "historical" / "pm_crypto_price_tape.jsonl"
    if not p.exists():
        return []
    by_day: dict[str, list[float]] = defaultdict(list)
    with open(p, encoding="utf-8") as f:
        for line in f:
            row = json.loads(line)
            if row.get("live") is not True or row.get("observation_only") is not True:
                continue
            if row.get("asset") != asset:
                continue
            day = row["timestamp"][:10]
            by_day[day].append(float(row["price"]))
    days = sorted(by_day)
    out = []
    for i in range(1, len(days)):
        prev = by_day[days[i - 1]][-1]
        cur = by_day[days[i]][-1]
        if prev == 0:
            continue
        out.append((days[i], (cur - prev) / prev))
    return out


def ensure_dxy_template(base_dir: Path) -> dict:
    hist = base_dir / "data" / "historical"
    hist.mkdir(parents=True, exist_ok=True)
    example = hist / "dxy_daily.jsonl.example"
    if not example.exists():
        example.write_text(
            json.dumps({
                "date": "2026-01-02",
                "close": 103.45,
                "symbol": "DXY",
                "source": "manual_csv_import",
                "observation_only": True,
            }, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
    research = base_dir / "research"
    research.mkdir(parents=True, exist_ok=True)
    spec = research / "dxy_manual_input_spec.md"
    if not spec.exists():
        spec.write_text(_dxy_spec_md(), encoding="utf-8")
    live = hist / "dxy_daily.jsonl"
    return {
        "example_path": str(example),
        "live_path": str(live),
        "live_exists": live.exists(),
        "spec_path": str(spec),
        "status": "ok" if live.exists() else "insufficient_data",
    }


def load_dxy_daily(base_dir: Path) -> list[tuple[str, float]]:
    p = base_dir / "data" / "historical" / "dxy_daily.jsonl"
    if not p.exists():
        return []
    out = []
    with open(p, encoding="utf-8") as f:
        for line in f:
            row = json.loads(line)
            d = row.get("date") or row.get("timestamp", "")[:10]
            c = row.get("close")
            if d and c is not None:
                out.append((str(d)[:10], float(c)))
    return out


def _dxy_spec_md() -> str:
    return """# DXY Manual Input Spec (Observation Only)

**Principle:** Observation ≠ Experience. Do not promote to trading rules.

## Target file

`data/historical/dxy_daily.jsonl` (copy from `dxy_daily.jsonl.example`)

## Required fields

| Field | Type | Description |
|-------|------|-------------|
| `date` | string | `YYYY-MM-DD` |
| `close` | float | DXY or USD index close |
| `observation_only` | bool | must be `true` |
| `source` | string | provenance tag (required in Phase 3e validator) |

## Optional fields

- `symbol` (default `DXY`)
- `open`, `high`, `low`, `volume`

## Example JSONL line

```json
{"date": "2026-01-02", "close": 103.45, "symbol": "DXY", "source": "manual_csv_import", "observation_only": true}
```

## Catalog

- `macro.dxy.daily` → graceful `insufficient_data` when file missing
- No network fetch in Phase 3d builders
"""


def run_phase3d(base_dir: Optional[Path] = None) -> dict:
    root = Path(base_dir) if base_dir else Path(__file__).resolve().parent.parent
    return {
        "funding": write_funding_rates_jsonl(root),
        "pm_crypto_tape": write_pm_crypto_price_tape_jsonl(root),
        "dxy": ensure_dxy_template(root),
        "generated_at": _now_iso(),
    }
