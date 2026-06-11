"""Offline lead-lag preliminary test — audit phase only."""

from __future__ import annotations

import math
from typing import Any

from .config import LEAD_LAG_LAGS, LEAD_LAG_PAIRS
from .data_utils import pearson
from .paths import MIN_LEAD_LAG_SAMPLES


def _aligned_pairs(
    driver_rets: dict[str, float],
    target_rets: dict[str, float],
    lag: int,
) -> list[tuple[float, float]]:
    """Return (driver_ret, target_ret) pairs for given lag (calendar intersection)."""
    driver_dates = sorted(driver_rets.keys())
    target_dates = set(target_rets.keys())
    pairs: list[tuple[float, float]] = []
    for d in driver_dates:
        # target date = d + lag trading days approximated by calendar offset
        # For daily audit: use sorted target calendar, find date lag positions ahead
        if lag == 0:
            t_date = d
        else:
            # find index of d in sorted common calendar
            if d not in target_dates:
                continue
            all_dates = sorted(target_dates & set(driver_dates))
            if d not in all_dates:
                continue
            idx = all_dates.index(d)
            if idx + lag >= len(all_dates):
                continue
            t_date = all_dates[idx + lag]
        if t_date not in target_rets:
            continue
        pairs.append((driver_rets[d], target_rets[t_date]))
    return pairs


def run_lead_lag(
    series: dict[str, dict[str, float]],
    min_samples: int = MIN_LEAD_LAG_SAMPLES,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for driver, target in LEAD_LAG_PAIRS:
        d_rets = series.get(driver, {})
        t_rets = series.get(target, {})
        if not d_rets or not t_rets:
            results.append({
                "driver": driver,
                "target": target,
                "status": "INSUFFICIENT DATA",
                "reason": "missing series",
            })
            continue
        for lag in LEAD_LAG_LAGS:
            pairs = _aligned_pairs(d_rets, t_rets, lag)
            n = len(pairs)
            if n < min_samples:
                results.append({
                    "driver": driver,
                    "target": target,
                    "lag": lag,
                    "sample_count": n,
                    "hit_rate": None,
                    "correlation": None,
                    "status": "INSUFFICIENT DATA",
                })
                continue
            xs = [p[0] for p in pairs]
            ys = [p[1] for p in pairs]
            corr = pearson(xs, ys)
            hits = sum(
                1 for x, y in pairs
                if (x > 0 and y > 0) or (x < 0 and y < 0)
            )
            hit_rate = hits / n
            results.append({
                "driver": driver,
                "target": target,
                "lag": lag,
                "sample_count": n,
                "hit_rate": round(hit_rate, 4),
                "correlation": round(corr, 4) if not math.isnan(corr) else None,
                "status": "OK",
            })
    return results
