#!/usr/bin/env python3
"""
Event-level attribution statistics (observation only).

Output: shared_intelligence/insights/event_attribution_report.md

Usage:
    PYTHONPATH=. python3 analytics/event_attribution_report.py
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from analytics.metrics import expectancy, profit_factor, win_rate

_SHARED = Path("/Users/libo/shared_intelligence")
_DEFAULT_IN = _SHARED / "trades" / "event_attributed_trades.jsonl"
_DEFAULT_OUT = _SHARED / "insights" / "event_attribution_report.md"


def _load_jsonl(path: Path) -> list[dict]:
    rows: list[dict] = []
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def _by_event(rows: list[dict]) -> dict[str, list[dict]]:
    groups: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        for label in row.get("events") or []:
            groups[label].append(row)
    return dict(groups)


def _pf_str(pf: float) -> str:
    return "∞" if pf == float("inf") else f"{pf:.4f}"


def build_report(rows: list[dict], generated_at: datetime) -> str:
    attributed = [r for r in rows if r.get("event_count", 0) > 0]
    by_event = _by_event(rows)
    multi = [r for r in attributed if r.get("event_count", 0) >= 2]

    lines = [
        "# Event Attribution Report",
        "",
        "> Phase 2 — observation only. No event filters, blocks, or overrides.",
        "",
        f"- Generated: {generated_at.isoformat()}",
        f"- Total trades: **{len(rows)}**",
        f"- Trades with ≥1 event: **{len(attributed)}**",
        f"- Trades with ≥2 events: **{len(multi)}**",
        "",
        "---",
        "",
        "## Per-Event Statistics",
        "",
        "| Event | Trades | Win Rate | Profit Factor | Expectancy |",
        "|-------|--------|----------|---------------|------------|",
    ]

    ranked = sorted(
        by_event.items(),
        key=lambda x: -len(x[1]),
    )
    for label, trades in ranked:
        pf = profit_factor(trades)
        lines.append(
            f"| {label} | {len(trades)} | {win_rate(trades):.2%} | "
            f"{_pf_str(pf)} | {expectancy(trades):+.6f}% |"
        )

    if not ranked:
        lines.append("| _no events matched_ | — | — | — | — |")

    lines += ["", "---", "", "## Multi-Event Trades (sample)", ""]
    for row in sorted(multi, key=lambda r: r.get("pnl_pct", 0))[:15]:
        ev = " + ".join(row.get("events") or [])
        lines.append(
            f"- `{row['source']}/{row['symbol']}` "
            f"pnl={row.get('pnl_pct', 0):+.4f}% "
            f"events=[{ev}]"
        )
    if not multi:
        lines.append("_No multi-event trades in current window._")

    lines += [
        "",
        "---",
        "",
        "## Interpretation Rules",
        "",
        "- Sample size < 5 → **Unverified** (do not promote to knowledge).",
        "- Observation ≠ Knowledge. No automatic strategy changes.",
        "- Goal: test whether events (e.g. NFP + AVGO) repeat as loss clusters.",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    p = argparse.ArgumentParser(description="Build event attribution markdown report")
    p.add_argument("--in", dest="in_path", type=Path, default=_DEFAULT_IN)
    p.add_argument("--out", type=Path, default=_DEFAULT_OUT)
    args = p.parse_args()

    if not args.in_path.exists():
        print(f"ERROR: run event_joiner.py first — missing {args.in_path}")
        return 1

    rows = _load_jsonl(args.in_path)
    report = build_report(rows, datetime.now(timezone.utc))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(report, encoding="utf-8")
    print(f"Report → {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
