"""Audit existing data assets before import — reuse-first."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from .config import CN_TARGETS, MACRO_SERIES, US_TARGETS
from .paths import (
    ASHARE_DB,
    CHINA_DIR,
    FLOWS_DIR,
    MACRO_DIR,
    MARKETS_DIR,
)


def _series_info(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"exists": False, "rows": 0, "start": None, "end": None}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        bars = data.get("bars") or []
        dates = [b["date"] for b in bars if b.get("date")]
        return {
            "exists": True,
            "rows": len(bars),
            "start": min(dates) if dates else None,
            "end": max(dates) if dates else None,
            "source": data.get("source"),
        }
    except Exception as exc:
        return {"exists": True, "rows": 0, "error": str(exc)}


def _ashare_daily(code: str) -> dict[str, Any]:
    if not ASHARE_DB.exists():
        return {"exists": False, "rows": 0}
    conn = sqlite3.connect(ASHARE_DB)
    try:
        row = conn.execute(
            "SELECT COUNT(*), MIN(trade_date), MAX(trade_date) FROM daily_bars WHERE symbol = ?",
            (code,),
        ).fetchone()
        return {
            "exists": row[0] > 0,
            "rows": row[0],
            "start": row[1],
            "end": row[2],
            "db": str(ASHARE_DB),
        }
    finally:
        conn.close()


def run_audit() -> dict[str, Any]:
    """Return full reuse inventory for V0."""
    report: dict[str, Any] = {
        "a_share_research_db": {},
        "shared_intelligence": {"markets": {}, "macro": {}, "china": {}, "flows": {}},
        "reuse_plan": [],
        "fetch_plan": [],
    }

    for code, meta in CN_TARGETS.items():
        ashare = _ashare_daily(code)
        report["a_share_research_db"][code] = {**meta, **ashare}
        si_path = CHINA_DIR / f"{code}.json"
        si = _series_info(si_path)
        report["shared_intelligence"]["china"][code] = si
        if ashare.get("rows", 0) > 0:
            report["reuse_plan"].append(f"Export {code} ({meta['name']}) from a_share_research_db → history/china/")
        elif not si.get("exists"):
            report["fetch_plan"].append(f"Fetch {code} ({meta['name']}) — not in a_share DB")

    for key, ticker in MACRO_SERIES.items():
        si = _series_info(MACRO_DIR / f"{key}.json")
        report["shared_intelligence"]["macro"][key] = si
        if not si.get("exists"):
            report["fetch_plan"].append(f"Fetch {key} ({ticker}) → history/macro/")

    nb = _series_info(FLOWS_DIR / "northbound.json")
    report["shared_intelligence"]["flows"]["northbound"] = nb
    if not nb.get("exists"):
        report["fetch_plan"].append("Fetch 北向资金 → history/flows/northbound.json")

    for sym in list(US_TARGETS.keys()) + ["BTC", "ETH", "SOXX"]:
        si = _series_info(MARKETS_DIR / f"{sym}.json")
        report["shared_intelligence"]["markets"][sym] = si

    return report


def format_audit_markdown(report: dict[str, Any]) -> str:
    lines = ["# Cross Market V0 — Data Audit\n"]
    lines.append("## a_share_research_db\n")
    lines.append("| Code | Name | Rows | Start | End | Action |")
    lines.append("|------|------|------|-------|-----|--------|")
    for code, info in report["a_share_research_db"].items():
        action = "REUSE export" if info.get("rows", 0) > 0 else "FETCH"
        lines.append(
            f"| {code} | {info.get('name', '')} | {info.get('rows', 0)} | "
            f"{info.get('start') or '-'} | {info.get('end') or '-'} | {action} |"
        )
    lines.append("\n## Reuse Plan\n")
    for item in report["reuse_plan"]:
        lines.append(f"- {item}")
    lines.append("\n## Fetch Plan\n")
    for item in report["fetch_plan"]:
        lines.append(f"- {item}")
    return "\n".join(lines) + "\n"
