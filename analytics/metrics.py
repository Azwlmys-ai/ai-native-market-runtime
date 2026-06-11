"""Shared trade metrics for cross-market attribution (stdlib only)."""

from __future__ import annotations

from typing import Any


def win_rate(trades: list[dict]) -> float:
    if not trades:
        return 0.0
    return sum(1 for t in trades if t.get("win")) / len(trades)


def profit_factor(trades: list[dict]) -> float:
    wins = sum(t["pnl_pct"] for t in trades if t.get("pnl_pct", 0) > 0)
    losses = abs(sum(t["pnl_pct"] for t in trades if t.get("pnl_pct", 0) < 0))
    if losses == 0:
        return float("inf") if wins > 0 else 0.0
    return wins / losses


def expectancy(trades: list[dict]) -> float:
    if not trades:
        return 0.0
    return sum(t.get("pnl_pct", 0) for t in trades) / len(trades)


def max_drawdown(trades: list[dict]) -> float:
    """Peak-to-trough drawdown on cumulative pnl_pct (ordered by exit_time)."""
    if not trades:
        return 0.0
    ordered = sorted(trades, key=lambda t: t.get("exit_time", ""))
    equity = 0.0
    peak = 0.0
    max_dd = 0.0
    for t in ordered:
        equity += float(t.get("pnl_pct") or 0.0)
        peak = max(peak, equity)
        max_dd = max(max_dd, peak - equity)
    return round(max_dd, 6)


def best_trade(trades: list[dict]) -> dict | None:
    if not trades:
        return None
    return max(trades, key=lambda t: t.get("pnl_pct", 0))


def worst_trade(trades: list[dict]) -> dict | None:
    if not trades:
        return None
    return min(trades, key=lambda t: t.get("pnl_pct", 0))


def holding_stats(trades: list[dict]) -> dict[str, Any]:
    if not trades:
        return {"count": 0, "avg_minutes": 0.0, "median_minutes": 0.0, "buckets": {}}
    mins = sorted(float(t.get("holding_minutes") or 0) for t in trades)
    n = len(mins)
    mid = mins[n // 2] if n % 2 else (mins[n // 2 - 1] + mins[n // 2]) / 2
    buckets = {"<30m": 0, "30-120m": 0, "2-8h": 0, ">8h": 0}
    for m in mins:
        if m < 30:
            buckets["<30m"] += 1
        elif m < 120:
            buckets["30-120m"] += 1
        elif m < 480:
            buckets["2-8h"] += 1
        else:
            buckets[">8h"] += 1
    return {
        "count": n,
        "avg_minutes": round(sum(mins) / n, 2),
        "median_minutes": round(mid, 2),
        "buckets": buckets,
    }


def group_stats(trades: list[dict], key: str) -> dict[str, dict[str, Any]]:
    groups: dict[str, list[dict]] = {}
    for t in trades:
        groups.setdefault(str(t.get(key) or "unknown"), []).append(t)
    return {
        name: {
            "trade_count": len(rows),
            "win_rate": round(win_rate(rows), 4),
            "expectancy": round(expectancy(rows), 6),
            "profit_factor": round(profit_factor(rows), 4)
            if profit_factor(rows) != float("inf")
            else None,
        }
        for name, rows in sorted(groups.items())
    }


def kpi_summary(trades: list[dict]) -> dict[str, Any]:
    pf = profit_factor(trades)
    return {
        "trade_count": len(trades),
        "win_rate": round(win_rate(trades), 4),
        "expectancy": round(expectancy(trades), 6),
        "profit_factor": round(pf, 4) if pf != float("inf") else None,
        "max_drawdown": max_drawdown(trades),
    }
