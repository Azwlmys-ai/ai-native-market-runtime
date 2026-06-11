#!/usr/bin/env python3
"""
Cross-market weekly attribution report (read-only learning).

Project:  Polymarket_arbitrage
Root:     /Users/libo/.hermes/polymarket_arbitrage
Allowed:   research/, analytics/, memory/

Input:    /Users/libo/shared_intelligence/trades/
          - us_etf_weekly.jsonl
          - okx_weekly.jsonl
Output:   /Users/libo/shared_intelligence/insights/weekly_attribution_report.md

Usage:
    python analytics/weekly_attribution_report.py
    python analytics/weekly_attribution_report.py --week 2026-W23
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from analytics.metrics import (
    best_trade,
    expectancy,
    group_stats,
    holding_stats,
    profit_factor,
    win_rate,
    worst_trade,
)

_SHARED = Path("/Users/libo/shared_intelligence")
_DEFAULT_TRADES_DIR = _SHARED / "trades"
_DEFAULT_OUT = _SHARED / "insights" / "weekly_attribution_report.md"


def _iso_week(dt: datetime) -> str:
    return f"{dt.isocalendar().year}-W{dt.isocalendar().week:02d}"


def _load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows: list[dict] = []
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def _fmt_trade(t: dict | None) -> str:
    if not t:
        return "_none_"
    return (
        f"{t.get('source')}/{t.get('symbol')} "
        f"pnl={t.get('pnl_pct'):+.4f}% "
        f"({t.get('strategy')}, {t.get('session')})"
    )


def _section_source(name: str, trades: list[dict]) -> list[str]:
    pf = profit_factor(trades)
    pf_str = "∞" if pf == float("inf") else f"{pf:.4f}"
    best = best_trade(trades)
    worst = worst_trade(trades)
    hold = holding_stats(trades)
    by_symbol = group_stats(trades, "symbol")
    by_strategy = group_stats(trades, "strategy")

    lines = [
        f"## {name}",
        "",
        f"- Trades: **{len(trades)}**",
        f"- Win rate: **{win_rate(trades):.2%}**",
        f"- Profit Factor: **{pf_str}**",
        f"- Expectancy: **{expectancy(trades):+.6f}%**",
        f"- Best trade: {_fmt_trade(best)}",
        f"- Worst trade: {_fmt_trade(worst)}",
        "",
        "### Holding time",
        "",
        f"- Avg: {hold['avg_minutes']:.1f} min | Median: {hold['median_minutes']:.1f} min",
        f"- Buckets: {hold['buckets']}",
        "",
        "### By symbol (top 10 by count)",
        "",
    ]
    top_symbols = sorted(by_symbol.items(), key=lambda x: -x[1]["trade_count"])[:10]
    for sym, stats in top_symbols:
        lines.append(
            f"- `{sym}`: n={stats['trade_count']}, "
            f"WR={stats['win_rate']:.2%}, exp={stats['expectancy']:+.4f}%"
        )
    lines += ["", "### By strategy", ""]
    for strat, stats in by_strategy.items():
        lines.append(
            f"- `{strat}`: n={stats['trade_count']}, "
            f"WR={stats['win_rate']:.2%}, PF={stats['profit_factor']}"
        )
    lines.append("")
    return lines


def build_report(
    etf: list[dict],
    okx: list[dict],
    week: str,
    generated_at: datetime,
) -> str:
    all_trades = etf + okx
    lines = [
        "# Weekly Cross-Market Attribution Report",
        "",
        f"> Phase 1 — read-only learning. No strategy/risk/execution changes.",
        "",
        f"- Week: **{week}**",
        f"- Generated: {generated_at.isoformat()}",
        f"- Sources: us_etf ({len(etf)}), okx ({len(okx)})",
        "",
        "---",
        "",
        "## Combined (ETF + OKX)",
        "",
        f"- Total trades: **{len(all_trades)}**",
        f"- Win rate: **{win_rate(all_trades):.2%}**",
        f"- Profit Factor: **{profit_factor(all_trades):.4f}**"
        if profit_factor(all_trades) != float("inf")
        else "- Profit Factor: **∞**",
        f"- Expectancy: **{expectancy(all_trades):+.6f}%**",
        f"- Best: {_fmt_trade(best_trade(all_trades))}",
        f"- Worst: {_fmt_trade(worst_trade(all_trades))}",
        "",
        "---",
        "",
    ]
    lines += _section_source("US ETF", etf)
    lines += ["---", ""]
    lines += _section_source("OKX Futures", okx)
    lines += [
        "---",
        "",
        "## Cross-Market Lessons (observational)",
        "",
        "- Compare win rate and expectancy across sessions before inferring edge.",
        "- Holding-time buckets highlight scalping (OKX) vs swing (ETF) regimes.",
        "- This report does **not** trigger parameter or risk changes.",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    p = argparse.ArgumentParser(description="Build weekly cross-market attribution report")
    p.add_argument("--trades-dir", type=Path, default=_DEFAULT_TRADES_DIR)
    p.add_argument("--out", type=Path, default=_DEFAULT_OUT)
    p.add_argument("--week", default=None)
    args = p.parse_args()

    week = args.week or _iso_week(datetime.now(timezone.utc))
    etf = _load_jsonl(args.trades_dir / "us_etf_weekly.jsonl")
    okx = _load_jsonl(args.trades_dir / "okx_weekly.jsonl")

    if not etf and not okx:
        print("WARNING: no trade files found — run exporters first")

    report = build_report(etf, okx, week, datetime.now(timezone.utc))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(report, encoding="utf-8")
    print(f"Report → {args.out} ({len(etf)} ETF + {len(okx)} OKX trades)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
