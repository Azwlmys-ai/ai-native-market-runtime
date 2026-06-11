#!/usr/bin/env python3
"""
Step 5: Cross-market theme learning report (ETF / Crypto / Polymarket proxy).

Output: shared_intelligence/insights/cross_market_theme_report.md

Usage:
    PYTHONPATH=. python3 analytics/cross_market_theme_report.py
"""

from __future__ import annotations

import argparse
import json
import statistics
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from analytics.replay_common import MARKET_SYMBOLS, load_json, load_jsonl, market_bucket
from research.history_paths import CROSS_MARKET_REPORT, LEARNING_ROOT, REPLAY_DATASET, THEME_PATTERNS


def _theme_market_stats(rows: list[dict], theme: str) -> dict[str, list[float]]:
    buckets: dict[str, list[float]] = defaultdict(list)
    for row in rows:
        if row.get("theme") != theme:
            continue
        for sym in MARKET_SYMBOLS:
            val = row.get(f"{sym}_1D")
            if val is not None:
                buckets[market_bucket(sym)].append(float(val))
        pm = row.get("PM_PROXY_1D")
        if pm is not None:
            buckets["polymarket_proxy"].append(float(pm))
    return dict(buckets)


def _avg(vals: list[float]) -> float:
    return round(statistics.mean(vals), 4) if vals else 0.0


def build_report(rows: list[dict], patterns: dict, generated_at: datetime) -> str:
    themes = sorted({r.get("theme") for r in rows if r.get("theme")})
    lines = [
        "# Cross-Market Theme Report",
        "",
        f"**Generated:** {generated_at.isoformat()}",
        f"**Replay events:** {len(rows)}",
        "",
        "> Learning-only artifact. Polymarket column uses PM_PROXY (synthetic) until historical PM tape is wired.",
        "",
    ]

    answers: dict[str, str] = {}

    for focus in ("AI", "RATES", "INFLATION"):
        stats = _theme_market_stats(rows, focus)
        if not stats:
            continue
        ranked = sorted(
            ((m, _avg(v), len(v)) for m, v in stats.items()),
            key=lambda x: abs(x[1]),
            reverse=True,
        )
        top = ranked[0]
        answers[focus] = f"{top[0]} (avg 1D {top[1]:+.2f}%, n={top[2]})"
        lines += [
            f"## {focus} Theme",
            "",
            "| Market | Avg 1D Return | Sample |",
            "|--------|---------------|--------|",
        ]
        for m, avg, n in ranked:
            lines.append(f"| {m} | {avg:+.2f}% | {n} |")
        lines.append("")

    etf_only = []
    crypto_and_etf = []
    for theme in themes:
        stats = _theme_market_stats(rows, theme)
        has_etf = bool(stats.get("etf"))
        has_crypto = bool(stats.get("crypto"))
        if has_etf and not has_crypto:
            etf_only.append(theme)
        if has_etf and has_crypto:
            crypto_and_etf.append(theme)

    lines += [
        "## PRD Questions",
        "",
        f"1. **AI Theme 最影响哪个市场？** {answers.get('AI', 'insufficient data')}",
        f"2. **Rates Theme 最影响哪个市场？** {answers.get('RATES', 'insufficient data')}",
        f"3. **Inflation Theme 最影响哪个市场？** {answers.get('INFLATION', 'insufficient data')}",
        f"4. **哪些 Theme 只影响 ETF？** {', '.join(etf_only) or 'none isolated (all major themes move ETFs)'}",
        f"5. **哪些 Theme 同时影响 ETF 和 Crypto？** {', '.join(crypto_and_etf) or 'none'}",
        "",
        "## Top Patterns (3D horizon)",
        "",
    ]

    pats = [p for p in patterns.get("patterns", []) if p.get("horizon_days") == 3]
    pats.sort(key=lambda p: (-p.get("confidence", 0), -abs(p.get("avg_return_3d", 0))))
    for p in pats[:12]:
        lines.append(
            f"- **{p['theme']}** × `{p['asset']}` ({p['market']}): "
            f"avg 3D {p['avg_return_3d']:+.2f}% | n={p['sample_size']} | conf={p['confidence']}"
        )

    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--replay", type=Path, default=REPLAY_DATASET)
    parser.add_argument("--patterns", type=Path, default=THEME_PATTERNS)
    parser.add_argument("--out", type=Path, default=CROSS_MARKET_REPORT)
    args = parser.parse_args()

    rows = load_jsonl(args.replay)
    patterns = load_json(args.patterns)
    report = build_report(rows, patterns, datetime.now(timezone.utc))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(report + "\n", encoding="utf-8")
    print(f"Wrote cross-market report → {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
