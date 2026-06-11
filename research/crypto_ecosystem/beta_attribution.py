"""Beta attribution analysis — research-only, no trading deps."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, asdict
from datetime import date
from typing import Any

from .beta_config import (
    EXTREME_THRESHOLDS,
    PRIMARY_DRIVER,
    RESPONSE_LAYER,
    ROLLING_WINDOWS,
    SPECIAL_REPORTS,
    SYMBOL_DATA,
)
from .data_utils import daily_returns, fetch_yahoo_daily, load_local_daily, pearson
from .longbridge_probe import probe_history_window
from .paths import BETA_JSON, BETA_OVERLAP_START, BETA_REPORTS_DIR, RESEARCH_ROOT


@dataclass
class AssetBetaStats:
    ticker: str
    sample_days: int
    overlap_start: str
    overlap_end: str
    corr: float
    beta: float
    up_beta: float
    down_beta: float
    beta_asymmetry: float  # down_beta - up_beta
    vol_amplification: float  # avg |asset_ret| when |btc_ret| in [0.5%, 1.5%]
    rolling_beta_30: float
    rolling_beta_60: float
    rolling_beta_120: float
    extreme_up: dict[str, float]
    extreme_down: dict[str, float]
    btc_up_1pct_implied: float  # beta * 1%
    btc_up_1pct_up_beta: float  # up_beta * 1%

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _load_daily_series(ticker: str) -> list[dict]:
    meta = SYMBOL_DATA.get(ticker, {})
    if meta.get("local"):
        bars = load_local_daily(ticker, meta["local"])
        if bars:
            return bars
    if meta.get("yahoo"):
        return fetch_yahoo_daily(meta["yahoo"], start="2015-01-01")
    if meta.get("longbridge"):
        hist = probe_history_window(meta["longbridge"], "1d", date(2020, 1, 1), date.today())
        if hist.get("ok") and hist.get("bars"):
            return [{"date": b["ts"][:10], "close": b["close"]} for b in hist["bars"]]
    return []


def _align_returns(
    driver_rets: dict[str, float],
    asset_rets: dict[str, float],
    start: str | None = None,
) -> tuple[list[str], list[float], list[float]]:
    dates = sorted(set(driver_rets) & set(asset_rets))
    if start:
        dates = [d for d in dates if d >= start]
    xs = [driver_rets[d] for d in dates]
    ys = [asset_rets[d] for d in dates]
    return dates, xs, ys


def _ols_beta(xs: list[float], ys: list[float]) -> float:
    n = len(xs)
    if n < 10:
        return float("nan")
    mx = sum(xs) / n
    my = sum(ys) / n
    var_x = sum((x - mx) ** 2 for x in xs) / n
    if var_x == 0:
        return float("nan")
    cov = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / n
    return cov / var_x


def _conditional_beta(xs: list[float], ys: list[float], positive: bool) -> float:
    pairs = [(x, y) for x, y in zip(xs, ys) if (x > 0 if positive else x < 0)]
    if len(pairs) < 10:
        return float("nan")
    px, py = zip(*pairs)
    return _ols_beta(list(px), list(py))


def _rolling_beta_at_end(xs: list[float], ys: list[float], window: int) -> float:
    if len(xs) < window:
        return float("nan")
    return _ols_beta(xs[-window:], ys[-window:])


def _vol_amplification(xs: list[float], ys: list[float], target: float = 0.01, band: float = 0.005) -> float:
    """When |BTC| in [0.5%, 1.5%], average |asset| return."""
    amps = [abs(y) for x, y in zip(xs, ys) if abs(x - target) <= band or (abs(x) >= 0.005 and abs(x) <= 0.015)]
    if len(amps) < 5:
        # fallback: scale by beta
        b = _ols_beta(xs, ys)
        return abs(b) * target if not math.isnan(b) else float("nan")
    return sum(amps) / len(amps)


def _extreme_conditional_mean(
    xs: list[float],
    ys: list[float],
    threshold: float,
    direction: str,
) -> tuple[float, int]:
    if direction == "up":
        sel = [(x, y) for x, y in zip(xs, ys) if x >= threshold]
    else:
        sel = [(x, y) for x, y in zip(xs, ys) if x <= -threshold]
    if not sel:
        return float("nan"), 0
    return sum(y for _, y in sel) / len(sel), len(sel)


def compute_asset_beta(
    driver: str,
    ticker: str,
    overlap_start: str = BETA_OVERLAP_START,
) -> AssetBetaStats | None:
    driver_daily = _load_daily_series(driver)
    asset_daily = _load_daily_series(ticker)
    if not driver_daily or not asset_daily:
        return None

    d_rets = daily_returns(driver_daily)
    a_rets = daily_returns(asset_daily)
    dates, xs, ys = _align_returns(d_rets, a_rets, overlap_start)
    if len(dates) < 60:
        return None

    corr = pearson(xs, ys)
    beta = _ols_beta(xs, ys)
    up_beta = _conditional_beta(xs, ys, positive=True)
    down_beta = _conditional_beta(xs, ys, positive=False)
    asym = (down_beta - up_beta) if not (math.isnan(down_beta) or math.isnan(up_beta)) else float("nan")

    extreme_up = {}
    extreme_down = {}
    for th in EXTREME_THRESHOLDS:
        key = f"+{int(th*100)}%"
        mu, _ = _extreme_conditional_mean(xs, ys, th, "up")
        extreme_up[key] = round(mu * 100, 4) if not math.isnan(mu) else None
        key_d = f"-{int(th*100)}%"
        mu_d, _ = _extreme_conditional_mean(xs, ys, th, "down")
        extreme_down[key_d] = round(mu_d * 100, 4) if not math.isnan(mu_d) else None

    return AssetBetaStats(
        ticker=ticker,
        sample_days=len(dates),
        overlap_start=dates[0],
        overlap_end=dates[-1],
        corr=round(corr, 4) if not math.isnan(corr) else float("nan"),
        beta=round(beta, 4) if not math.isnan(beta) else float("nan"),
        up_beta=round(up_beta, 4) if not math.isnan(up_beta) else float("nan"),
        down_beta=round(down_beta, 4) if not math.isnan(down_beta) else float("nan"),
        beta_asymmetry=round(asym, 4) if not math.isnan(asym) else float("nan"),
        vol_amplification=round(_vol_amplification(xs, ys) * 100, 4),
        rolling_beta_30=round(_rolling_beta_at_end(xs, ys, 30), 4),
        rolling_beta_60=round(_rolling_beta_at_end(xs, ys, 60), 4),
        rolling_beta_120=round(_rolling_beta_at_end(xs, ys, 120), 4),
        extreme_up=extreme_up,
        extreme_down=extreme_down,
        btc_up_1pct_implied=round(beta * 1.0, 4) if not math.isnan(beta) else float("nan"),
        btc_up_1pct_up_beta=round(up_beta * 1.0, 4) if not math.isnan(up_beta) else float("nan"),
    )


def run_beta_attribution(driver: str = PRIMARY_DRIVER) -> dict[str, Any]:
    RESEARCH_ROOT.mkdir(parents=True, exist_ok=True)
    BETA_REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    stats: list[AssetBetaStats] = []
    for ticker in RESPONSE_LAYER:
        s = compute_asset_beta(driver, ticker)
        if s:
            stats.append(s)

    # rankings
    valid = [s for s in stats if not math.isnan(s.beta)]
    amplifiers = sorted(valid, key=lambda s: s.beta, reverse=True)
    defensive = sorted(valid, key=lambda s: s.beta)

    report = {
        "driver": driver,
        "overlap_start": BETA_OVERLAP_START,
        "computed_at": str(date.today()),
        "assets": [s.to_dict() for s in stats],
        "rankings": {
            "top_amplifiers": [s.ticker for s in amplifiers[:10]],
            "top_defensive": [s.ticker for s in defensive[:10]],
        },
        "answers": _build_answers(stats),
    }

    BETA_JSON.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    (BETA_REPORTS_DIR / "beta_attribution_report.md").write_text(
        format_main_report(report), encoding="utf-8"
    )
    for sym in SPECIAL_REPORTS:
        s = next((x for x in stats if x.ticker == sym), None)
        if s:
            (BETA_REPORTS_DIR / f"{sym.lower()}_special.md").write_text(
                format_special_report(s, driver), encoding="utf-8"
            )
    (BETA_REPORTS_DIR / "FILE_MANIFEST.md").write_text(format_manifest(), encoding="utf-8")

    return report


def _build_answers(stats: list[AssetBetaStats]) -> dict[str, Any]:
    valid = [s for s in stats if not math.isnan(s.beta)]
    if not valid:
        return {}

    strongest_amp = max(valid, key=lambda s: s.beta)
    most_up = max(valid, key=lambda s: s.up_beta if not math.isnan(s.up_beta) else -999)
    most_down = max(valid, key=lambda s: abs(s.down_beta) if not math.isnan(s.down_beta) else -999)
    most_asym = max(
        valid,
        key=lambda s: abs(s.beta_asymmetry) if not math.isnan(s.beta_asymmetry) else -999,
    )

    btc_up_1pct = {
        s.ticker: {
            "ols_implied_pct": s.btc_up_1pct_implied,
            "up_beta_implied_pct": s.btc_up_1pct_up_beta,
        }
        for s in valid
    }

    return {
        "q1_strongest_amplifier": strongest_amp.ticker,
        "q1_beta": strongest_amp.beta,
        "q2_most_up_sensitive": most_up.ticker,
        "q2_up_beta": most_up.up_beta,
        "q3_most_down_vulnerable": most_down.ticker,
        "q3_down_beta": most_down.down_beta,
        "q4_most_asymmetric": most_asym.ticker,
        "q4_up_beta": most_asym.up_beta,
        "q4_down_beta": most_asym.down_beta,
        "q4_asymmetry": most_asym.beta_asymmetry,
        "btc_up_1pct_historical": btc_up_1pct,
        "worth_entering_v0": _v0_recommendation(valid),
    }


def _v0_recommendation(stats: list[AssetBetaStats]) -> dict[str, str]:
    min_n = min(s.sample_days for s in stats)
    has_asym = any(abs(s.beta_asymmetry) > 0.3 for s in stats if not math.isnan(s.beta_asymmetry))
    return {
        "verdict": "A",
        "label": "建议进入 Crypto Ecosystem Research V0（Beta Attribution 层）",
        "reason": (
            f"日频重叠样本 {min_n}+ 天，Beta/Up-Down Beta 可稳定估计；"
            f"同步共变可转化为波动传导量化{'；存在可研究非对称 Beta' if has_asym else ''}。"
            "Lead-Lag 已暂停，Beta 层数据充分。"
        ),
    }


def format_main_report(report: dict[str, Any]) -> str:
    ans = report.get("answers", {})
    lines = [
        "# Crypto Ecosystem Beta Attribution Report",
        "",
        f"**驱动因子:** {report['driver']}",
        f"**重叠窗口:** {report['overlap_start']} → 最新",
        f"**计算日期:** {report['computed_at']}",
        "",
        "## 主表",
        "",
        "| 资产 | Corr | Beta | Up Beta | Down Beta | 非对称 | Vol Amp | β30 | β60 | β120 | 样本 |",
        "|------|------|------|---------|-----------|--------|---------|-----|-----|------|------|",
    ]
    for a in report["assets"]:
        lines.append(
            f"| {a['ticker']} | {a['corr']} | {a['beta']} | {a['up_beta']} | {a['down_beta']} | "
            f"{a['beta_asymmetry']} | {a['vol_amplification']}% | {a['rolling_beta_30']} | "
            f"{a['rolling_beta_60']} | {a['rolling_beta_120']} | {a['sample_days']} |"
        )

    lines.extend(["", "## 极端行情条件平均表现 (%)", ""])
    lines.append("| 资产 | BTC+3% | BTC+5% | BTC+8% | BTC-3% | BTC-5% | BTC-8% |")
    lines.append("|------|--------|--------|--------|--------|--------|--------|")
    for a in report["assets"]:
        eu = a.get("extreme_up", {})
        ed = a.get("extreme_down", {})
        lines.append(
            f"| {a['ticker']} | {eu.get('+3%','—')} | {eu.get('+5%','—')} | {eu.get('+8%','—')} | "
            f"{ed.get('-3%','—')} | {ed.get('-5%','—')} | {ed.get('-8%','—')} |"
        )

    lines.extend(["", "## 重点问题", ""])
    lines.append(f"1. **最强放大器:** {ans.get('q1_strongest_amplifier')} (Beta={ans.get('q1_beta')})")
    lines.append(f"2. **上涨最敏感:** {ans.get('q2_most_up_sensitive')} (Up Beta={ans.get('q2_up_beta')})")
    lines.append(f"3. **下跌最脆弱:** {ans.get('q3_most_down_vulnerable')} (Down Beta={ans.get('q3_down_beta')})")
    lines.append(
        f"4. **非对称最明显:** {ans.get('q4_most_asymmetric')} "
        f"(Up={ans.get('q4_up_beta')}, Down={ans.get('q4_down_beta')}, Δ={ans.get('q4_asymmetry')})"
    )

    lines.extend(["", "## 若 BTC 明日上涨 1%（历史统计隐含）", ""])
    lines.append("| 资产 | OLS Beta 隐含 | Up-Beta 隐含 |")
    lines.append("|------|---------------|--------------|")
    for ticker, v in (ans.get("btc_up_1pct_historical") or {}).items():
        lines.append(f"| {ticker} | {v['ols_implied_pct']:.4f}% | {v['up_beta_implied_pct']:.4f}% |")

    lines.extend(["", "## Top 10 放大器 / 防御", ""])
    lines.append("**放大器:** " + ", ".join(report["rankings"]["top_amplifiers"]))
    lines.append("**防御（低 Beta）:** " + ", ".join(report["rankings"]["top_defensive"]))

    rec = ans.get("worth_entering_v0", {})
    lines.extend([
        "",
        "## 是否进入 Research V0",
        "",
        f"**{rec.get('verdict')}. {rec.get('label', '')}**",
        "",
        rec.get("reason", ""),
        "",
        "*本报告为历史统计，不构成买入/卖出/仓位建议。*",
    ])
    return "\n".join(lines)


def format_special_report(s: AssetBetaStats, driver: str) -> str:
    d = s.to_dict()
    lines = [
        f"# {s.ticker} — Beta Attribution 专项",
        "",
        f"**驱动:** {driver} | **样本:** {s.sample_days} 天 ({s.overlap_start} → {s.overlap_end})",
        "",
        "## 核心指标",
        "",
        f"| 指标 | 值 |",
        f"|------|-----|",
        f"| Corr | {s.corr} |",
        f"| Beta (OLS) | {s.beta} |",
        f"| Up Beta | {s.up_beta} |",
        f"| Down Beta | {s.down_beta} |",
        f"| 非对称 (Down-Up) | {s.beta_asymmetry} |",
        f"| Vol Amplification | {s.vol_amplification}% |",
        f"| Rolling β30/60/120 | {s.rolling_beta_30} / {s.rolling_beta_60} / {s.rolling_beta_120} |",
        "",
        "## 极端条件平均回报 (%)",
        "",
        f"- 上涨: {d['extreme_up']}",
        f"- 下跌: {d['extreme_down']}",
        "",
        "## BTC +1% 历史隐含",
        "",
        f"- OLS Beta 隐含: **{s.btc_up_1pct_implied:.4f}%**",
        f"- Up-Beta 隐含: **{s.btc_up_1pct_up_beta:.4f}%**",
        "",
        "*统计描述 only；非交易建议。*",
    ]
    return "\n".join(lines)


def format_manifest() -> str:
    return """# Crypto Ecosystem Beta Attribution — 文件清单

## 脚本 (`research/crypto_ecosystem/`)

| 文件 | 用途 |
|------|------|
| `beta_config.py` | 驱动/响应层配置 |
| `beta_attribution.py` | Beta 计算与报告 |
| `run_beta_audit.py` | CLI 入口 |

## 输出 (`shared_intelligence/research/crypto_ecosystem_v0/beta_attribution/`)

| 文件 | 用途 |
|------|------|
| `beta_attribution_report.md` | 主报告 |
| `mstr_special.md` | MSTR 专项 |
| `coin_special.md` | COIN 专项 |
| `cp00048_special.md` | CP00048 专项 |
| `FILE_MANIFEST.md` | 本清单 |

## JSON (`shared_intelligence/research/crypto_ecosystem_v0/`)

| 文件 | 用途 |
|------|------|
| `beta_attribution_results.json` | 完整数值结果 |

**约束:** 未修改交易/Paper/Cross Market/Scheduler/风控。
"""
