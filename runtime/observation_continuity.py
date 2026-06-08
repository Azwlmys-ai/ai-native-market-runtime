"""
observation_continuity — Phase 3e 连续采集导出（只读已有快照 → 增量落盘）

不新增采集器；从 orchestrator 已有的 market_price_history / runtime.db /
asset_price_history 增量导出。所有行 observation_only=true。
"""

from __future__ import annotations

import json
import sqlite3
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from runtime.observation_backfill import (
    CRYPTO_ASSET_KEYS,
    _infer_asset,
    _is_crypto_market,
    _normalize_ts,
    _read_feather_funding,
    _read_json_funding,
    _slug_map_from_db,
    collect_funding_observations,
    ensure_dxy_template,
    FEATHER_SYMBOL_MAP,
    OKX_FUNDING_FEATHER,
)

PM_TAPE_PATH = "data/historical/pm_crypto_price_tape.jsonl"
FUNDING_PATH = "data/historical/funding_rates.jsonl"
DXY_PATH = "data/historical/dxy_daily.jsonl"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _tape_dedup_key(row: dict) -> tuple[str, str, str]:
    return (
        _normalize_ts(str(row.get("timestamp", ""))),
        str(row.get("market_id", "")),
        str(row.get("outcome", "yes")),
    )


def _funding_dedup_key(row: dict) -> tuple[str, str]:
    return (str(row.get("symbol", "")), _normalize_ts(str(row.get("timestamp", ""))))


def _load_jsonl_keys(path: Path, key_fn) -> set:
    if not path.exists():
        return set()
    keys = set()
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            keys.add(key_fn(json.loads(line)))
    return keys


def _append_jsonl(path: Path, rows: list[dict]) -> int:
    if not rows:
        return 0
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    return len(rows)


def _market_low_information(prices: list[float]) -> bool:
    return len(prices) >= 2 and min(prices) == max(prices)


def _existing_tape_prices_by_market(path: Path) -> dict[str, list[float]]:
    by_market: dict[str, list[float]] = defaultdict(list)
    if not path.exists():
        return by_market
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            if row.get("outcome") == "yes" and row.get("price") is not None:
                by_market[str(row["market_id"])].append(float(row["price"]))
    return by_market


def audit_pm_crypto_sources(base_dir: Path) -> dict:
    mph = base_dir / "data" / "market_price_history.json"
    db = base_dir / "data" / "runtime.db"
    audit = {
        "orchestrator_records_each_cycle": True,
        "recorder": "orchestrator._record_market_prices → datastore.record_market_prices",
        "fact_sources": ["data/market_price_history.json", "data/runtime.db market_prices"],
        "agent_a_role": "feeds latest_data.json; orchestrator snapshots prices (not Agent A direct write)",
        "market_price_history_exists": mph.exists(),
        "runtime_db_exists": db.exists(),
    }
    if mph.exists():
        mph_data = json.loads(mph.read_text(encoding="utf-8"))
        audit["market_price_history_markets"] = len(mph_data)
    if db.exists():
        conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
        try:
            audit["runtime_db_rows"] = conn.execute("SELECT COUNT(*) FROM market_prices").fetchone()[0]
            audit["runtime_db_markets"] = conn.execute(
                "SELECT COUNT(DISTINCT market_id) FROM market_prices"
            ).fetchone()[0]
        finally:
            conn.close()
    return audit


def _collect_pm_crypto_candidates(base_dir: Path) -> list[dict]:
    """Collect export candidates from runtime.db (full) + market_price_history (rolling)."""
    slug_map = _slug_map_from_db(base_dir)
    seen_pts: set[tuple[str, str, str, str]] = set()
    candidates: list[dict] = []

    def _add(mid: str, slug: str, ts: str, yes_price, liquidity, source: str):
        if not _is_crypto_market(slug):
            return
        norm_ts = _normalize_ts(str(ts))
        sig = (mid, slug, norm_ts, str(yes_price))
        if sig in seen_pts:
            return
        seen_pts.add(sig)
        candidates.append({
            "timestamp": norm_ts,
            "market_id": mid,
            "slug": slug,
            "asset": _infer_asset(slug),
            "outcome": "yes",
            "price": float(yes_price),
            "liquidity": float(liquidity) if liquidity is not None else None,
            "source": source,
            "observation_only": True,
            "live": True,
        })

    db = base_dir / "data" / "runtime.db"
    if db.exists():
        conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
        try:
            for mid, slug, ts, yes_p, _no_p, liq in conn.execute(
                "SELECT market_id, slug, ts, yes_price, no_price, liquidity FROM market_prices"
            ):
                _add(str(mid), str(slug or slug_map.get(str(mid), "")), ts, yes_p, liq, "runtime.db")
        finally:
            conn.close()

    mph = base_dir / "data" / "market_price_history.json"
    if mph.exists():
        data = json.loads(mph.read_text(encoding="utf-8"))
        for mid, points in data.items():
            slug = slug_map.get(str(mid), "")
            for pt in points:
                _add(str(mid), slug, pt.get("ts", ""), pt.get("yes_price"), pt.get("liquidity"),
                     "market_price_history.json")

    return candidates


def export_pm_crypto_tape_incremental(base_dir: Path) -> dict:
    out = base_dir / PM_TAPE_PATH
    existing_keys = _load_jsonl_keys(out, _tape_dedup_key)
    prices_by_market = _existing_tape_prices_by_market(out)
    candidates = _collect_pm_crypto_candidates(base_dir)

    pending: list[dict] = []
    for row in candidates:
        key = _tape_dedup_key(row)
        if key in existing_keys:
            continue
        prices_by_market[row["market_id"]].append(row["price"])
        pending.append(row)
        existing_keys.add(key)

    new_rows: list[dict] = []
    for row in pending:
        row["low_information"] = _market_low_information(prices_by_market[row["market_id"]])
        new_rows.append(row)

    appended = _append_jsonl(out, new_rows)
    total = len(existing_keys)
    markets = defaultdict(int)
    low_info_markets = set()
    if out.exists():
        with open(out, encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                r = json.loads(line)
                markets[r["market_id"]] += 1
                if r.get("low_information"):
                    low_info_markets.add(r["market_id"])

    audit = audit_pm_crypto_sources(base_dir)
    stats = {
        **audit,
        "appended_rows": appended,
        "total_rows": total,
        "market_count": len(markets),
        "low_information_markets": sorted(low_info_markets),
        "output_path": str(out),
        "dedup_key": "timestamp+market_id+outcome",
        "generated_at": _now_iso(),
    }
    return stats


def audit_funding_sources(base_dir: Path) -> dict:
    asset_path = base_dir / "data" / "asset_price_history.json"
    live_symbols = []
    live_counts = {}
    if asset_path.exists():
        ah = json.loads(asset_path.read_text(encoding="utf-8"))
        for sym in ("BTC_FUNDING", "ETH_FUNDING", "SOL_FUNDING"):
            if sym in ah:
                live_symbols.append(sym)
                live_counts[sym] = len(ah[sym])
    return {
        "live_collector": "orchestrator._record_market_prices → BTC_FUNDING in asset_price_history.json",
        "live_symbols_present": live_symbols,
        "live_point_counts": live_counts,
        "static_sources": [
            "data/historical/okx_*_USDT_SWAP_funding_rate_*.json",
            "okx_perp_trader feather *-funding_rate.feather (BTC/ETH)",
        ],
        "sol_status": "missing" if "SOL_FUNDING" not in live_counts else "ok",
        "dedicated_agent": "agents/agent_okx_funding.py exists but not wired to orchestrator main path",
    }


def _live_funding_rows(base_dir: Path) -> list[dict]:
    asset_path = base_dir / "data" / "asset_price_history.json"
    if not asset_path.exists():
        return []
    ah = json.loads(asset_path.read_text(encoding="utf-8"))
    symbol_map = {"BTC_FUNDING": "BTC", "ETH_FUNDING": "ETH", "SOL_FUNDING": "SOL"}
    rows = []
    for feed_sym, out_sym in symbol_map.items():
        for pt in ah.get(feed_sym, []) or []:
            ts = pt.get("ts")
            price = pt.get("price")
            if ts is None or price is None:
                continue
            rows.append({
                "timestamp": _normalize_ts(str(ts)),
                "exchange": "okx",
                "symbol": out_sym,
                "funding_rate": float(price),
                "source_file": "data/asset_price_history.json",
                "observation_only": True,
                "live": True,
            })
    return rows


def export_funding_incremental(base_dir: Path) -> dict:
    out = base_dir / FUNDING_PATH
    existing_keys = _load_jsonl_keys(out, _funding_dedup_key)

    # Static merge (read-only)
    static_rows, static_stats = collect_funding_observations(base_dir)
    live_rows = _live_funding_rows(base_dir)

    new_rows: list[dict] = []
    for row in static_rows + live_rows:
        key = _funding_dedup_key(row)
        if key in existing_keys:
            continue
        new_rows.append(row)
        existing_keys.add(key)

    # First run: if file missing, write all static at once
    if not out.exists() and static_rows:
        out.parent.mkdir(parents=True, exist_ok=True)
        with open(out, "w", encoding="utf-8") as f:
            for row in static_rows:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
        existing_keys = {_funding_dedup_key(r) for r in static_rows}
        new_rows = [r for r in live_rows if _funding_dedup_key(r) not in existing_keys]
        for r in new_rows:
            existing_keys.add(_funding_dedup_key(r))

    appended = _append_jsonl(out, new_rows)
    symbols = defaultdict(int)
    if out.exists():
        with open(out, encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    symbols[json.loads(line)["symbol"]] += 1

    audit = audit_funding_sources(base_dir)
    missing = static_stats.get("missing_symbols", [])
    stats = {
        **audit,
        "appended_rows": appended,
        "total_rows": sum(symbols.values()),
        "symbols": dict(symbols),
        "missing_symbols": missing,
        "static_stats": static_stats,
        "output_path": str(out),
        "dedup_key": "symbol+timestamp",
        "generated_at": _now_iso(),
    }
    return stats


class DxyValidationError(Exception):
    pass


def validate_dxy_row(row: dict, line_no: int = 0) -> None:
    prefix = f"line {line_no}: " if line_no else ""
    if row.get("observation_only") is not True:
        raise DxyValidationError(f"{prefix}observation_only must be true")
    if "date" not in row and "timestamp" not in row:
        raise DxyValidationError(f"{prefix}missing date")
    if "close" not in row:
        raise DxyValidationError(f"{prefix}missing close")
    if "source" not in row:
        raise DxyValidationError(f"{prefix}missing source")
    try:
        float(row["close"])
    except (TypeError, ValueError) as exc:
        raise DxyValidationError(f"{prefix}invalid close") from exc


def load_and_validate_dxy(base_dir: Path) -> tuple[list[dict], dict]:
    p = base_dir / DXY_PATH
    if not p.exists():
        return [], {
            "status": "insufficient_data",
            "reason": "dxy_daily.jsonl missing",
            "rows": 0,
            "example_path": str(base_dir / "data/historical/dxy_daily.jsonl.example"),
        }
    rows = []
    errors = []
    with open(p, encoding="utf-8") as f:
        for i, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            try:
                validate_dxy_row(row, line_no=i)
                rows.append(row)
            except DxyValidationError as exc:
                errors.append(str(exc))
    if errors:
        return rows, {"status": "invalid", "errors": errors, "rows": len(rows)}
    return rows, {"status": "ok", "rows": len(rows), "path": str(p)}


def _write_pm_continuity_md(base_dir: Path, stats: dict) -> Path:
    path = base_dir / "research" / "pm_crypto_tape_continuity.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# PM Crypto Live Tape Continuity (Phase 3e)",
        "",
        f"**Generated:** {stats.get('generated_at')}",
        "",
        "## Audit",
        "",
        f"- Orchestrator records each cycle: **{stats.get('orchestrator_records_each_cycle')}**",
        f"- Recorder: `{stats.get('recorder')}`",
        f"- Fact sources: {', '.join(stats.get('fact_sources', []))}",
        f"- runtime.db rows: **{stats.get('runtime_db_rows', 'n/a')}**",
        f"- market_price_history markets: **{stats.get('market_price_history_markets', 'n/a')}**",
        "",
        "## Export",
        "",
        f"- Output: `{stats.get('output_path')}`",
        f"- Dedup key: `{stats.get('dedup_key')}`",
        f"- Appended this run: **{stats.get('appended_rows', 0)}**",
        f"- Total rows: **{stats.get('total_rows', 0)}**",
        f"- Markets: **{stats.get('market_count', 0)}**",
        f"- low_information markets: `{stats.get('low_information_markets', [])}`",
        "",
        "## Design",
        "",
        "- No new collector; incremental exporter only.",
        "- `live=true`, `observation_only=true`; sim data excluded.",
        "- Host loop gate: `PA_OBSERVATION_BACKFILL=1`",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _write_funding_continuity_md(base_dir: Path, stats: dict) -> Path:
    path = base_dir / "research" / "funding_continuity.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Funding Continuity (Phase 3e)",
        "",
        f"**Generated:** {stats.get('generated_at')}",
        "",
        "## Audit",
        "",
        f"- Live collector: `{stats.get('live_collector')}`",
        f"- Live symbols: `{stats.get('live_symbols_present', [])}`",
        f"- Live counts: `{stats.get('live_point_counts', {})}`",
        f"- SOL status: **{stats.get('sol_status')}**",
        f"- Dedicated agent (not wired): `{stats.get('dedicated_agent')}`",
        "",
        "## Export",
        "",
        f"- Output: `{stats.get('output_path')}`",
        f"- Dedup key: `{stats.get('dedup_key')}`",
        f"- Appended: **{stats.get('appended_rows', 0)}**",
        f"- Total rows: **{stats.get('total_rows', 0)}**",
        f"- Per symbol: `{stats.get('symbols', {})}`",
        f"- Missing (not fabricated): `{stats.get('missing_symbols', [])}`",
        "",
        "## Static sources",
        "",
    ]
    for s in stats.get("static_sources", []):
        lines.append(f"- {s}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _write_dxy_continuity_md(base_dir: Path, dxy_stats: dict, template_stats: dict) -> Path:
    path = base_dir / "research" / "dxy_continuity.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# DXY Continuity (Phase 3e)",
        "",
        f"**Generated:** {_now_iso()}",
        "",
        "## Status",
        "",
        f"- Live file: `{template_stats.get('live_path')}` exists={template_stats.get('live_exists')}",
        f"- Validation: **{dxy_stats.get('status')}**",
        f"- Rows: **{dxy_stats.get('rows', 0)}**",
    ]
    if dxy_stats.get("errors"):
        lines.append(f"- Errors: `{dxy_stats['errors']}`")
    lines.extend([
        "",
        "## Manual input",
        "",
        f"- Example: `{template_stats.get('example_path')}`",
        f"- Spec: `{template_stats.get('spec_path')}`",
        "- Required fields: `date`, `close`, `source`, `observation_only=true`",
        "- No network fetch in Phase 3e",
        "",
        "## Catalog",
        "",
        "- `macro.dxy.daily` → graceful insufficient_data when file missing",
    ])
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def run_phase3e(base_dir: Optional[Path] = None) -> dict:
    root = Path(base_dir) if base_dir else Path(__file__).resolve().parent.parent
    pm_stats = export_pm_crypto_tape_incremental(root)
    funding_stats = export_funding_incremental(root)
    template_stats = ensure_dxy_template(root)
    _, dxy_stats = load_and_validate_dxy(root)

    pm_md = _write_pm_continuity_md(root, pm_stats)
    funding_md = _write_funding_continuity_md(root, funding_stats)
    dxy_md = _write_dxy_continuity_md(root, dxy_stats, template_stats)

    return {
        "pm_crypto_tape": pm_stats,
        "funding": funding_stats,
        "dxy": dxy_stats,
        "dxy_template": template_stats,
        "continuity_reports": {
            "pm_crypto": str(pm_md),
            "funding": str(funding_md),
            "dxy": str(dxy_md),
        },
        "generated_at": _now_iso(),
    }
