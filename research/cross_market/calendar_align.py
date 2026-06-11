"""Trading-day alignment — US Close→CN Open, CN Close→US Open (research-only)."""

from __future__ import annotations

from typing import Iterable, Literal

AlignmentMode = Literal[
    "same_calendar",
    "us_close_cn_open",
    "cn_close_us_open",
    "cn_close_cn_next",
]

CN_KEYS = frozenset({"000001", "399001", "399006", "000300", "northbound"})
US_KEYS = frozenset({
    "QQQ", "SPY", "SOXX", "DXY", "US10Y", "US2Y", "BTC", "ETH", "SOL",
    "Factor_A", "Factor_B", "Factor_C", "Factor_D", "Factor_E", "Factor_F",
    "NVDA", "AMD", "MSFT", "AMZN", "GOOGL", "TSM", "ASML",
})


def trading_days_from_bars(bars: list[dict]) -> list[str]:
    return sorted({b["date"] for b in bars if b.get("date")})


def trading_days_from_returns(rets: dict[str, float]) -> list[str]:
    return sorted(rets.keys())


def _next_after(date: str, calendar: list[str]) -> str | None:
    for d in calendar:
        if d > date:
            return d
    return None


def _next_on_or_after(date: str, calendar: list[str]) -> str | None:
    for d in calendar:
        if d >= date:
            return d
    return None


def build_pairs(
    driver_days: list[str],
    target_days: list[str],
    mode: AlignmentMode,
) -> list[tuple[str, str]]:
    """Return (driver_date, target_date) pairs per alignment rule."""
    target_set = set(target_days)
    pairs: list[tuple[str, str]] = []

    if mode == "same_calendar":
        for d in driver_days:
            if d in target_set:
                pairs.append((d, d))
        return pairs

    if mode == "us_close_cn_open":
        for d in driver_days:
            t = _next_after(d, target_days)
            if t:
                pairs.append((d, t))
        return pairs

    if mode == "cn_close_us_open":
        for d in driver_days:
            t = _next_on_or_after(d, target_days)
            if t:
                pairs.append((d, t))
        return pairs

    if mode == "cn_close_cn_next":
        for d in driver_days:
            t = _next_after(d, target_days)
            if t:
                pairs.append((d, t))
        return pairs

    return pairs


def infer_alignment(driver: str, target: str) -> AlignmentMode:
    d_cn = driver in CN_KEYS or driver.startswith("0") or driver.startswith("3")
    t_cn = target in CN_KEYS or target.startswith("0") or target.startswith("3")
    d_us = driver in US_KEYS or driver.startswith("Factor_")
    t_us = target in US_KEYS or target.startswith("Factor_")

    if d_us and t_cn:
        return "us_close_cn_open"
    if d_cn and t_us:
        return "cn_close_us_open"
    if d_cn and t_cn:
        return "cn_close_cn_next"
    return "same_calendar"


def alignment_rules_doc() -> str:
    return """## 对齐规则 (V0.1)

### US Close → CN Open (`us_close_cn_open`)
- 驱动：美股/宏观因子在美交易日 T 的日收益
- 目标：A股在 T 之后**下一个 A股交易日**的日收益
- 处理：周末/美中节假日通过各自交易日历隐式排除

### CN Close → US Open (`cn_close_us_open`)
- 驱动：A股/北向在 A股交易日 T 的日收益（流量用水平变化率）
- 目标：美股在 T **当日或之后第一个美股交易日**的日收益

### CN → CN Next (`cn_close_cn_next`)
- 驱动：北向资金等 A股侧因子在 T
- 目标：A股指数在 T 之后下一个 A股交易日

### Same Calendar (`same_calendar`)
- 同市场或 24/7 资产（BTC→QQQ）保留同日对齐作为对照
"""


def load_cn_calendar(china_codes: Iterable[str], load_bars_fn) -> list[str]:
    days: set[str] = set()
    for code in china_codes:
        for d in load_bars_fn(code):
            days.add(d["date"])
    return sorted(days)


def load_us_calendar(us_symbols: Iterable[str], load_bars_fn) -> list[str]:
    days: set[str] = set()
    for sym in us_symbols:
        for d in load_bars_fn(code=sym):
            days.add(d["date"])
    return sorted(days)
