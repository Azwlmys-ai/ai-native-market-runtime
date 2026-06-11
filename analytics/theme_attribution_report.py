#!/usr/bin/env python3
"""
Theme-level attribution (cross-market learning layer).

Output: shared_intelligence/insights/theme_attribution_report.md

Usage:
    PYTHONPATH=. python3 analytics/theme_attribution_report.py
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
_DEFAULT_OUT = _SHARED / "insights" / "theme_attribution_report.md"


def _load_jsonl(path: Path) -> list[dict]:
    rows: list[dict] = []
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def _by_theme(rows: list[dict]) -> dict[str, list[dict]]:
    groups: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        for theme in row.get("themes") or []:
            groups[theme].append(row)
    return dict(groups)


def _pf_str(pf: float) -> str:
    return "∞" if pf == float("inf") else f"{pf:.4f}"


def _by_source_theme(rows: list[dict]) -> dict[str, dict[str, list[dict]]]:
    out: dict[str, dict[str, list[dict]]] = defaultdict(lambda: defaultdict(list))
    for row in rows:
        src = row.get("source") or "unknown"
        for theme in row.get("themes") or []:
            out[theme][src].append(row)
    return {t: dict(s) for t, s in out.items()}


def build_report(rows: list[dict], generated_at: datetime) -> str:
    themed = [r for r in rows if r.get("theme_count", 0) > 0]
    by_theme = _by_theme(themed)
    by_src = _by_source_theme(themed)

    lines = [
        "# Theme Attribution Report",
        "",
        "> Phase 2.1 — Theme layer is observational. Learning ≠ Trading.",
        "",
        f"- Generated: {generated_at.isoformat()}",
        f"- Trades with themes: **{len(themed)}** / {len(rows)}",
        f"- Themes tracked: **{len(by_theme)}**",
        "",
        "---",
        "",
        "## Theme Summary",
        "",
        "| Theme | Trades | Win Rate | Profit Factor | Expectancy |",
        "|-------|--------|----------|---------------|------------|",
    ]

    for theme in sorted(by_theme.keys()):
        trades = by_theme[theme]
        pf = profit_factor(trades)
        lines.append(
            f"| {theme} | {len(trades)} | {win_rate(trades):.2%} | "
            f"{_pf_str(pf)} | {expectancy(trades):+.6f}% |"
        )

    if not by_theme:
        lines.append("| _none_ | — | — | — | — |")

    lines += ["", "---", "", "## Theme × Source", ""]
    for theme in sorted(by_src.keys()):
        lines.append(f"### {theme}")
        lines.append("")
        lines.append("| Source | Trades | Win Rate | Expectancy |")
        lines.append("|--------|--------|----------|------------|")
        for src, trades in sorted(by_src[theme].items()):
            lines.append(
                f"| {src} | {len(trades)} | {win_rate(trades):.2%} | "
                f"{expectancy(trades):+.6f}% |"
            )
        lines.append("")

    lines += [
        "---",
        "",
        "## Cross-Market Questions (observational)",
        "",
        "- **AI Theme:** How do SOXL/NVDL/BTC react around NVDA+AVGO earnings windows?",
        "- **RATES Theme:** Do NFP/FOMC windows hurt ETF holds more than OKX scalps?",
        "- **INFLATION Theme:** Is CPI asymmetry visible in semis vs crypto?",
        "",
        "Promotion to Insight requires ≥30 samples + statistical review (see observation_promotion_rules.md).",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    p = argparse.ArgumentParser(description="Build theme attribution report")
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
