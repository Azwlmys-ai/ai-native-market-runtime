"""Lead-lag research — statistical only, no trading signals."""

from __future__ import annotations

import math
from dataclasses import dataclass, asdict
from typing import Any

from .calendar_align import AlignmentMode, build_pairs, infer_alignment, trading_days_from_returns
from .paths import LEAD_LAG_WINDOWS


@dataclass
class LeadLagResult:
    driver: str
    target: str
    lag_days: int
    window_days: int
    sample_count: int
    hit_rate: float
    avg_return: float
    avg_drawdown: float
    correlation: float
    direction: str
    alignment: str = "same_calendar"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _pearson(xs: list[float], ys: list[float]) -> float:
    n = len(xs)
    if n < 3:
        return float("nan")
    mx = sum(xs) / n
    my = sum(ys) / n
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    dx = math.sqrt(sum((x - mx) ** 2 for x in xs))
    dy = math.sqrt(sum((y - my) ** 2 for y in ys))
    if dx == 0 or dy == 0:
        return float("nan")
    return num / (dx * dy)


def _window_signal(driver_chg: float, threshold: float = 0.0) -> int:
    if driver_chg > threshold:
        return 1
    if driver_chg < -threshold:
        return -1
    return 0


def _pairs_to_index(
    pairs: list[tuple[str, str]],
) -> tuple[list[str], dict[str, str]]:
    """Map target_date -> driver_date for aligned pairs (unique targets)."""
    driver_dates = sorted({p[0] for p in pairs})
    target_by_driver = {d: t for d, t in pairs}
    return driver_dates, target_by_driver


def analyze_lead_lag(
    driver: str,
    target: str,
    driver_rets: dict[str, float],
    target_rets: dict[str, float],
    windows: tuple[int, ...] = LEAD_LAG_WINDOWS,
    lags: tuple[int, ...] = (1,),
    alignment: AlignmentMode | None = None,
    pairs: list[tuple[str, str]] | None = None,
) -> list[LeadLagResult]:
    """Lead-lag with optional trading-day alignment."""
    align = alignment or infer_alignment(driver, target)
    if pairs is None:
        pairs = build_pairs(
            trading_days_from_returns(driver_rets),
            trading_days_from_returns(target_rets),
            align,
        )
    if len(pairs) < 30:
        return []

    driver_dates, target_for_driver = _pairs_to_index(pairs)
    # ordered driver dates that have aligned targets
    aligned_driver_dates = [d for d in driver_dates if d in target_for_driver]

    results: list[LeadLagResult] = []
    for window in windows:
        for lag in lags:
            signals: list[tuple[float, float, float]] = []  # signed, target, driver
            for i in range(window + lag - 1, len(aligned_driver_dates)):
                driver_end_idx = i - (lag - 1)
                driver_start_idx = driver_end_idx - window + 1
                if driver_start_idx < 0:
                    continue
                driver_window = aligned_driver_dates[driver_start_idx:driver_end_idx + 1]
                driver_chg = sum(driver_rets.get(d, 0.0) for d in driver_window)
                driver_anchor = aligned_driver_dates[driver_end_idx]
                target_date = target_for_driver.get(driver_anchor)
                if not target_date or target_date not in target_rets:
                    continue
                target_ret = target_rets[target_date]
                sig = _window_signal(driver_chg)
                if sig != 0:
                    driver_ret = driver_rets.get(driver_anchor, 0.0)
                    signals.append((sig * target_ret, target_ret, driver_ret))

            if len(signals) < 10:
                results.append(LeadLagResult(
                    driver=driver, target=target, lag_days=lag, window_days=window,
                    sample_count=len(signals), hit_rate=float("nan"),
                    avg_return=float("nan"), avg_drawdown=float("nan"),
                    correlation=float("nan"), direction="insufficient_sample",
                    alignment=align,
                ))
                continue

            xs = [s[2] for s in signals]
            ys = [s[1] for s in signals]
            corr = _pearson(xs, ys)
            hits = sum(1 for signed_ret, _, _ in signals if signed_ret > 0)
            hit_rate = hits / len(signals)
            avg_ret = sum(s[1] for s in signals) / len(signals)
            cum = 0.0
            peak = 0.0
            max_dd = 0.0
            for signed_ret, _, _ in signals:
                cum += signed_ret
                peak = max(peak, cum)
                max_dd = min(max_dd, cum - peak)
            avg_dd = max_dd / len(signals) if signals else 0.0
            direction = "driver_leads" if hit_rate > 0.52 and abs(corr) > 0.05 else "no_signal"
            results.append(LeadLagResult(
                driver=driver, target=target, lag_days=lag, window_days=window,
                sample_count=len(signals),
                hit_rate=round(hit_rate, 4),
                avg_return=round(avg_ret * 100, 4),
                avg_drawdown=round(avg_dd * 100, 4),
                correlation=round(corr, 4) if not math.isnan(corr) else float("nan"),
                direction=direction,
                alignment=align,
            ))
    return results


def rank_relationships(all_results: list[LeadLagResult], top_n: int = 10) -> tuple[list[dict], list[dict]]:
    scored = []
    for r in all_results:
        if r.driver == r.target:
            continue
        if r.sample_count < 30 or math.isnan(r.correlation):
            continue
        score = abs(r.correlation) * abs(r.hit_rate - 0.5)
        scored.append((score, r))
    scored.sort(key=lambda x: x[0], reverse=True)
    strongest = [x[1].to_dict() for x in scored[:top_n]]
    weakest = [x[1].to_dict() for x in scored[-top_n:]]
    weakest.sort(key=lambda x: x.get("correlation", 0))
    return strongest, weakest


def run_full_matrix(
    drivers: dict[str, dict[str, float]],
    targets: dict[str, dict[str, float]],
    use_alignment: bool = True,
) -> list[LeadLagResult]:
    all_results: list[LeadLagResult] = []
    for d_name, d_rets in drivers.items():
        for t_name, t_rets in targets.items():
            if not d_rets or not t_rets:
                continue
            align = infer_alignment(d_name, t_name) if use_alignment else "same_calendar"
            pairs = build_pairs(
                trading_days_from_returns(d_rets),
                trading_days_from_returns(t_rets),
                align,
            )
            all_results.extend(
                analyze_lead_lag(d_name, t_name, d_rets, t_rets, pairs=pairs, alignment=align)
            )
    return all_results
