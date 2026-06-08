"""
observation_gaps — Phase 3c 只读 Observation 缺口审计（Funding / PM Crypto / DXY）

产出 research/*_gap_*.md；不写交易链、不改源项目。
"""

from __future__ import annotations

import json
import sqlite3
import statistics
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

HISTORY_MARKETS = Path("/Users/libo/shared_intelligence/history/markets")
REPLAY_PATH = Path("/Users/libo/shared_intelligence/history/replay_dataset.jsonl")
OKX_FUNDING_GLOB = Path("/Users/libo/okx_perp_trader/env_rule/user_data/data/okx/futures")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _count_funding_json_files(base_dir: Path) -> dict:
    hist = base_dir / "data" / "historical"
    by_symbol: dict[str, dict] = {}
    for sym in ("BTC", "ETH", "SOL"):
        files = sorted(hist.glob(f"okx_{sym}_USDT_SWAP_funding_rate_*.json"))
        raw_rows = 0
        by_day: dict[str, list[float]] = defaultdict(list)
        for p in files:
            data = json.loads(p.read_text(encoding="utf-8"))
            if not isinstance(data, list):
                continue
            raw_rows += len(data)
            for item in data:
                ts = (item.get("timestamp") or "")[:10]
                fr = item.get("funding_rate")
                if ts and fr is not None:
                    by_day[ts].append(float(fr))
        by_symbol[sym] = {
            "files": [str(p) for p in files],
            "raw_rows": raw_rows,
            "daily_points": len(by_day),
            "date_range": [min(by_day), max(by_day)] if by_day else [],
        }

    feather = []
    if OKX_FUNDING_GLOB.exists():
        for p in sorted(OKX_FUNDING_GLOB.glob("*-funding_rate.feather")):
            feather.append({"path": str(p), "size_bytes": p.stat().st_size})

    asset_hist = base_dir / "data" / "asset_price_history.json"
    live_funding = 0
    if asset_hist.exists():
        ah = json.loads(asset_hist.read_text(encoding="utf-8"))
        live_funding = len(ah.get("BTC_FUNDING", []))

    return {
        "local_json": by_symbol,
        "okx_feather_files": feather,
        "live_btc_funding_points": live_funding,
        "root_cause_n60": (
            "March+April 2026 only (~180 raw 8h settlements → ~60 unique calendar days after daily mean); "
            "ETH local JSON exists but Phase2/model_sandbox loaders historically scanned BTC glob only; "
            "SOL has no local JSON; OKX feather longer history approved_not_wired in catalog."
        ),
    }


def audit_funding(base_dir: Path) -> dict:
    data = _count_funding_json_files(base_dir)
    extension = [
        "Wire okx_{BTC,ETH,SOL}_USDT_SWAP_funding_rate_*.json in all loaders (not BTC-only glob).",
        "Read okx.market.funding feather via catalog (optional pyarrow) for multi-month backfill.",
        "Extend collector date range beyond 2026-03/04; add SOL swap funding collection.",
        "Aggregate 8h → daily for cross-market lag (document settlement cadence).",
    ]
    return {
        "audited_at": _now_iso(),
        "symbols": data["local_json"],
        "okx_feather_files": data["okx_feather_files"],
        "live_rolling": {"BTC_FUNDING": data["live_btc_funding_points"]},
        "why_n_approx_60": data["root_cause_n60"],
        "catalog_entries_recommended": [
            "pm.local.funding.historical",
            "okx.market.funding (existing, wire loaders)",
        ],
        "extension_plan": extension,
    }


def _crypto_market_filter(text: str) -> bool:
    t = text.lower()
    keys = ("bitcoin", "btc", "ethereum", " eth", "crypto", "solana", " sol ")
    return any(k in t for k in keys)


def audit_pm_crypto_replay(base_dir: Path) -> dict:
    replay_lines = 0
    replay_crypto_rows = 0
    replay_sample_keys: list[str] = []
    if REPLAY_PATH.exists():
        with open(REPLAY_PATH, encoding="utf-8") as f:
            for i, line in enumerate(f):
                replay_lines += 1
                row = json.loads(line)
                if i == 0:
                    replay_sample_keys = list(row.keys())[:20]
                if row.get("asset_class") == "crypto" or "BTC" in str(row.get("symbol", "")):
                    r = row.get("return_1d") or row.get("btc_return_1d")
                    if r is not None:
                        replay_crypto_rows += 1

    runtime_markets = []
    db = base_dir / "data" / "runtime.db"
    if db.exists():
        conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
        try:
            for mid, slug, cnt in conn.execute(
                "SELECT market_id, slug, COUNT(*) FROM market_prices GROUP BY market_id, slug"
            ):
                text = f"{slug}"
                if _crypto_market_filter(text):
                    runtime_markets.append({
                        "market_id": mid,
                        "slug": slug,
                        "price_points": cnt,
                    })
        finally:
            conn.close()

    mph_path = base_dir / "data" / "market_price_history.json"
    live_tape = []
    if mph_path.exists():
        mph = json.loads(mph_path.read_text(encoding="utf-8"))
        for mid, pts in mph.items():
            slug = ""
            if runtime_markets:
                for m in runtime_markets:
                    if str(m["market_id"]) == str(mid):
                        slug = m["slug"]
            text = f"{mid} {slug}"
            if _crypto_market_filter(text) or str(mid) in {m["market_id"] for m in runtime_markets}:
                live_tape.append({
                    "market_id": mid,
                    "slug": slug or "(unknown)",
                    "points": len(pts),
                    "yes_price_range": [
                        round(min(p.get("yes_price", 0) for p in pts), 4),
                        round(max(p.get("yes_price", 0) for p in pts), 4),
                    ] if pts else [],
                })

    sim_markets = []
    for fname in (
        "polymarket_extended_march_april_2026.json",
        "polymarket_markets_march_april_2026.json",
    ):
        p = base_dir / "data" / "historical" / fname
        if not p.exists():
            continue
        data = json.loads(p.read_text(encoding="utf-8"))
        if not isinstance(data, list):
            continue
        for row in data:
            q = str(row.get("question") or "")
            mid = str(row.get("id") or "")
            if _crypto_market_filter(q) or _crypto_market_filter(mid):
                hist = row.get("price_history") or []
                sim_markets.append({
                    "market_id": mid,
                    "question": q[:80],
                    "source_file": fname,
                    "hourly_points": len(hist),
                    "note": "simulated_anchor_dataset_not_live_pm",
                })

    return {
        "audited_at": _now_iso(),
        "why_pm_crypto_replay_n0": (
            "shared.history.replay_dataset.jsonl holds earnings/macro event rows (QQQ_* returns), "
            "not PM crypto price tape; _load_pm_crypto_proxy filter (asset_class=crypto) matches 0 rows."
        ),
        "replay_dataset": {
            "path": str(REPLAY_PATH),
            "lines": replay_lines,
            "crypto_proxy_rows": replay_crypto_rows,
            "sample_keys": replay_sample_keys,
        },
        "live_runtime_crypto_markets": runtime_markets,
        "live_price_tape": live_tape,
        "simulated_historical_crypto": sim_markets,
        "catalog_entries_recommended": [
            "pm.local.crypto_price_tape",
            "shared.history.pm_crypto_sim",
        ],
        "extension_plan": [
            "Build PM crypto daily returns from market_price_history.json (live) + historical sim anchors.",
            "Add replay row schema with asset_class=crypto OR dedicated pm_crypto_tape.jsonl.",
            "Match PM markets to BTC anchor for cross-market pair (not earnings replay).",
        ],
    }


def audit_dxy(base_dir: Path) -> dict:
    hist = base_dir / "data" / "historical"
    forex_path = hist / "forex_may_2026.json"
    commodities_path = hist / "commodities_march_april_2026.json"
    macro_path = HISTORY_MARKETS / "macro_replay.json"
    dxy_market = HISTORY_MARKETS / "DXY.json"

    forex_days = 0
    forex_sample = []
    if forex_path.exists():
        fx = json.loads(forex_path.read_text(encoding="utf-8"))
        forex_days = len(fx)
        forex_sample = list(fx.keys())[:5]

    commodity_keys = []
    if commodities_path.exists():
        comm = json.loads(commodities_path.read_text(encoding="utf-8"))
        commodity_keys = list(comm.keys())[:20]

    has_dxy_file = dxy_market.exists()
    collector_has_dxy = False
    collector_note = (
        "collectors/commodity_forex_collector.py fetches gold/oil/forex pairs; "
        "no DX-Y / UUP / trade-weighted USD index series collected today."
    )

    usd_proxy_options = [
        {"proxy": "USD/EUR inverse from forex_may_2026.json", "days": forex_days},
        {"proxy": "UUP ETF daily (not collected)", "days": 0},
        {"proxy": "FRED DTWEXBGS / DXY Yahoo ^DXY", "days": 0, "status": "not_wired"},
    ]

    minimal_schema = {
        "format": "jsonl_or_csv",
        "required_fields": ["date", "close"],
        "optional_fields": ["symbol", "source", "open", "high", "low", "volume"],
        "example_jsonl": {"date": "2026-01-02", "close": 103.45, "symbol": "DXY", "source": "yahoo^DXY"},
        "target_path": str(base_dir / "data" / "historical" / "dxy_daily.jsonl"),
        "catalog_id": "macro.dxy.daily",
    }

    return {
        "audited_at": _now_iso(),
        "dxy_file_in_shared_markets": has_dxy_file,
        "commodity_forex_collector": {"has_dxy": collector_has_dxy, "note": collector_note},
        "existing_forex": {"path": str(forex_path), "days": forex_days, "sample_dates": forex_sample},
        "existing_commodities": {"path": str(commodities_path), "keys": commodity_keys},
        "macro_replay": {"path": str(macro_path), "exists": macro_path.exists()},
        "usd_proxy_options": usd_proxy_options,
        "minimal_input_schema": minimal_schema,
        "catalog_entries_recommended": ["macro.dxy.daily", "macro.usd_proxy.forex"],
        "extension_plan": [
            "Add optional DXY/UUP daily collector → data/historical/dxy_daily.jsonl",
            "Register macro.dxy.daily in cross_project_data_catalog.json (read-only)",
            "Until then, use USD/EUR from forex as weak proxy with low confidence flag",
        ],
    }


def _md_funding(audit: dict) -> str:
    lines = [
        "# Funding Observation Gap (Phase 3c)",
        "",
        f"**Audited:** {audit['audited_at']}",
        "",
        "## Why n≈60",
        "",
        audit["why_n_approx_60"],
        "",
        "## Current Sources",
        "",
    ]
    for sym, info in audit["symbols"].items():
        lines.append(f"### {sym}")
        lines.append(f"- Files: {len(info['files'])}")
        lines.append(f"- Raw rows: {info['raw_rows']}")
        lines.append(f"- Daily points: {info['daily_points']}")
        if info["date_range"]:
            lines.append(f"- Date range: {info['date_range'][0]} → {info['date_range'][1]}")
        lines.append("")

    lines.extend(["## OKX Feather (catalog approved_not_wired)", ""])
    for f in audit["okx_feather_files"]:
        lines.append(f"- `{f['path']}` ({f['size_bytes']} bytes)")
    lines.extend([
        "",
        "## Live Rolling",
        f"- BTC_FUNDING in asset_price_history: {audit['live_rolling']['BTC_FUNDING']} points",
        "",
        "## Extension Plan",
        "",
    ])
    for step in audit["extension_plan"]:
        lines.append(f"- {step}")
    lines.extend(["", "## Catalog", ""])
    for c in audit["catalog_entries_recommended"]:
        lines.append(f"- `{c}`")
    return "\n".join(lines) + "\n"


def _md_pm_crypto(audit: dict) -> str:
    lines = [
        "# PM Crypto Replay Gap (Phase 3c)",
        "",
        f"**Audited:** {audit['audited_at']}",
        "",
        "## Why PM Crypto replay n=0",
        "",
        audit["why_pm_crypto_replay_n0"],
        "",
        "## Replay Dataset",
        "",
        f"- Path: `{audit['replay_dataset']['path']}`",
        f"- Lines: {audit['replay_dataset']['lines']}",
        f"- Crypto proxy rows (current filter): **{audit['replay_dataset']['crypto_proxy_rows']}**",
        f"- Sample keys: `{', '.join(audit['replay_dataset']['sample_keys'][:12])}`",
        "",
        "## Live Runtime Crypto Markets",
        "",
    ]
    for m in audit["live_runtime_crypto_markets"]:
        lines.append(f"- `{m['market_id']}` / `{m['slug']}` — {m['price_points']} price points")
    lines.extend(["", "## Live Price Tape (market_price_history.json)", ""])
    for t in audit["live_price_tape"]:
        lines.append(
            f"- `{t['market_id']}` `{t['slug']}` — n={t['points']}, "
            f"yes_range={t.get('yes_price_range')}"
        )
    lines.extend(["", "## Simulated Historical Crypto (anchor datasets)", ""])
    for s in audit["simulated_historical_crypto"]:
        lines.append(
            f"- `{s['market_id']}` — {s['hourly_points']}h from `{s['source_file']}` "
            f"({s['note']})"
        )
    lines.extend(["", "## Extension Plan", ""])
    for step in audit["extension_plan"]:
        lines.append(f"- {step}")
    return "\n".join(lines) + "\n"


def _md_dxy(audit: dict) -> str:
    sch = audit["minimal_input_schema"]
    lines = [
        "# DXY Observation Gap (Phase 3c)",
        "",
        f"**Audited:** {audit['audited_at']}",
        "",
        "## Current State",
        "",
        f"- DXY.json in shared_intelligence/history/markets: **{audit['dxy_file_in_shared_markets']}**",
        f"- commodity_forex_collector DXY: **{audit['commodity_forex_collector']['has_dxy']}**",
        f"- {audit['commodity_forex_collector']['note']}",
        f"- forex_may_2026.json days: **{audit['existing_forex']['days']}**",
        "",
        "## USD Proxy Options",
        "",
    ]
    for opt in audit["usd_proxy_options"]:
        lines.append(f"- {opt['proxy']}: n={opt.get('days', 0)}")
    lines.extend([
        "",
        "## Minimal Input Schema (if no DXY yet)",
        "",
        f"- Format: `{sch['format']}`",
        f"- Required: `{', '.join(sch['required_fields'])}`",
        f"- Target: `{sch['target_path']}`",
        f"- Catalog ID: `{sch['catalog_id']}`",
        f"- Example: `{json.dumps(sch['example_jsonl'])}`",
        "",
        "## Extension Plan",
        "",
    ])
    for step in audit["extension_plan"]:
        lines.append(f"- {step}")
    return "\n".join(lines) + "\n"


def build_gap_reports(base_dir: Optional[Path] = None, date_suffix: str = "20260607") -> dict:
    root = Path(base_dir) if base_dir else Path(__file__).resolve().parent.parent
    research = root / "research"
    research.mkdir(parents=True, exist_ok=True)

    funding = audit_funding(root)
    pm = audit_pm_crypto_replay(root)
    dxy = audit_dxy(root)

    paths = {
        "funding_md": research / f"funding_observation_gap_{date_suffix}.md",
        "pm_md": research / f"pm_crypto_replay_gap_{date_suffix}.md",
        "dxy_md": research / f"dxy_observation_gap_{date_suffix}.md",
    }
    paths["funding_md"].write_text(_md_funding(funding), encoding="utf-8")
    paths["pm_md"].write_text(_md_pm_crypto(pm), encoding="utf-8")
    paths["dxy_md"].write_text(_md_dxy(dxy), encoding="utf-8")

    return {
        "funding": funding,
        "pm_crypto": pm,
        "dxy": dxy,
        "output_paths": {k: str(v) for k, v in paths.items()},
    }
