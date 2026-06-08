#!/usr/bin/env python3
"""
Phase 2 Observation Layer builder — read-only research outputs.

Generates:
  - research/okx_observation_summary.json
  - research/us_etf_observation_summary.json
  - research/cross_market_discovery_report.md

Does NOT modify agents, strategy, risk, or executor.
"""

from __future__ import annotations

import json
import math
import sqlite3
import statistics
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from runtime.observation_catalog import ObservationCatalog  # noqa: E402

RESEARCH = ROOT / "research"
HISTORY_MARKETS = Path("/Users/libo/shared_intelligence/history/markets")
ETF_DB = Path("/Users/libo/us-lev-etf-cta/data/sqlite/etf_trader.db")
ETF_RESEARCH_DB = Path("/Users/libo/us-lev-etf-cta/data/sqlite/tsll_research.db")
HISTORICAL = ROOT / "data" / "historical"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _percentile(vals: list[float], p: float) -> float | None:
    if not vals:
        return None
    s = sorted(vals)
    k = (len(s) - 1) * p / 100
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return s[int(k)]
    return s[f] * (c - k) + s[c] * (k - f)


def build_okx_summary(catalog: ObservationCatalog) -> dict:
    weekly = catalog.read_jsonl("okx.trades.weekly")
    memory_rows: list[dict] = []
    try:
        for row in catalog.iter_jsonl("okx.trade_memory.export"):
            memory_rows.append(row)
    except Exception as exc:
        memory_rows = []
        memory_err = str(exc)
    else:
        memory_err = None

    all_rows = weekly + memory_rows
    hold_sec = []
    hold_min = []
    exit_reasons: Counter = Counter()
    sessions: Counter = Counter()
    symbols: Counter = Counter()
    vol_bps: list[float] = []
    volume_profile: Counter = Counter()

    for row in weekly:
        symbols[row.get("symbol", "?")] += 1
        sessions[row.get("session", "?")] += 1
        hm = row.get("holding_minutes")
        if hm is not None:
            hold_min.append(float(hm))
        pnl = row.get("pnl_pct")
        if pnl is not None:
            vol_bps.append(abs(float(pnl)) * 100)

    for row in memory_rows:
        sym = row.get("symbol") or row.get("metadata", {}).get("instrument", "?")
        symbols[str(sym)] += 1
        sessions[row.get("session", "?")] += 1
        er = row.get("exit_reason", "unknown")
        exit_reasons[er] += 1
        hs = row.get("hold_sec")
        if hs is not None:
            hold_sec.append(float(hs))
        meta = row.get("metadata") or {}
        bucket = meta.get("holding_bucket")
        if bucket:
            volume_profile[bucket] += 1
        mae = meta.get("mae_bps")
        mfe = meta.get("mfe_bps")
        if mae is not None and mfe is not None:
            vol_bps.append(abs(float(mfe - mae)))

    # Funding from local historical (observation, not experience)
    funding_rates: list[float] = []
    for p in sorted(HISTORICAL.glob("okx_BTC_USDT_SWAP_funding_rate_*.json")):
        data = json.loads(p.read_text())
        if isinstance(data, list):
            for item in data:
                fr = item.get("funding_rate")
                if fr is not None:
                    funding_rates.append(float(fr))

    summary = {
        "generated_at": _now_iso(),
        "principle": "Share Observation, not Experience",
        "sources": {
            "okx_weekly": catalog.stat("okx.trades.weekly"),
            "okx_trade_memory": catalog.stat("okx.trade_memory.export"),
        },
        "record_counts": {
            "okx_weekly": len(weekly),
            "okx_trade_memory_sample": len(memory_rows),
            "combined": len(all_rows),
        },
        "volatility": {
            "pnl_abs_bps_weekly_median": _percentile(vol_bps[: len(weekly)], 50),
            "pnl_abs_bps_weekly_p90": _percentile(vol_bps[: len(weekly)], 90),
            "mae_mfe_spread_median_bps": _percentile(vol_bps[len(weekly) :], 50) if memory_rows else None,
        },
        "funding": {
            "btc_swap_observations": len(funding_rates),
            "mean_rate": statistics.mean(funding_rates) if funding_rates else None,
            "median_rate": statistics.median(funding_rates) if funding_rates else None,
            "min_rate": min(funding_rates) if funding_rates else None,
            "max_rate": max(funding_rates) if funding_rates else None,
            "source": "data/historical/okx_BTC_USDT_SWAP_funding_rate_*.json",
        },
        "holding_time": {
            "weekly_minutes_mean": statistics.mean(hold_min) if hold_min else None,
            "weekly_minutes_median": statistics.median(hold_min) if hold_min else None,
            "memory_hold_sec_mean": statistics.mean(hold_sec) if hold_sec else None,
            "memory_hold_sec_median": statistics.median(hold_sec) if hold_sec else None,
            "memory_hold_sec_p90": _percentile(hold_sec, 90),
        },
        "exit_reason": dict(exit_reasons.most_common(20)),
        "session_distribution": dict(sessions),
        "symbol_distribution": dict(symbols.most_common(15)),
        "volume_profile_holding_buckets": dict(volume_profile),
        "excluded": [
            "experience_review",
            "learning_feedback",
            "knowledge",
            "lessons",
        ],
    }
    if memory_err:
        summary["okx_trade_memory_error"] = memory_err
    return summary


def _query_db(db_path: Path, sql: str) -> list[tuple]:
    if not db_path.exists():
        return []
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        cur = conn.execute(sql)
        return cur.fetchall()
    finally:
        conn.close()


def build_us_etf_summary() -> dict:
    candles_n = _query_db(ETF_DB, "SELECT COUNT(*) FROM candles")[0][0] if ETF_DB.exists() else 0
    signals_n = _query_db(ETF_DB, "SELECT COUNT(*) FROM signals")[0][0] if ETF_DB.exists() else 0
    trades_n = _query_db(ETF_DB, "SELECT COUNT(*) FROM trades")[0][0] if ETF_DB.exists() else 0

    symbols = _query_db(ETF_DB, "SELECT symbol, COUNT(*) FROM candles GROUP BY symbol")
    signal_strats = _query_db(ETF_DB, "SELECT strategy, COUNT(*) FROM signals GROUP BY strategy")
    hold_hrs = [r[0] for r in _query_db(ETF_DB, "SELECT holding_hours FROM trades WHERE holding_hours IS NOT NULL")]
    sessions = _query_db(ETF_DB, "SELECT market_session, COUNT(*) FROM trades GROUP BY market_session")
    close_reasons = _query_db(ETF_DB, "SELECT close_reason, COUNT(*) FROM trades GROUP BY close_reason")

    # Indicators from research DB if populated
    ind_n = _query_db(ETF_RESEARCH_DB, "SELECT COUNT(*) FROM indicators_5m")[0][0] if ETF_RESEARCH_DB.exists() else 0

    # Read-only sample candles stats
    vol_samples = []
    if ETF_DB.exists():
        rows = _query_db(
            ETF_DB,
            "SELECT symbol, ts, close, volume FROM candles ORDER BY ts DESC LIMIT 500",
        )
        by_sym: dict[str, list[float]] = defaultdict(list)
        for sym, _ts, close, vol in rows:
            if close:
                by_sym[sym].append(float(close))
            if vol:
                vol_samples.append(float(vol))

    return {
        "generated_at": _now_iso(),
        "principle": "Share Observation, not Experience",
        "sources": {
            "etf_trader_db": {"path": str(ETF_DB), "exists": ETF_DB.exists()},
            "tsll_research_db": {"path": str(ETF_RESEARCH_DB), "exists": ETF_RESEARCH_DB.exists()},
            "shared_weekly": ObservationCatalog().stat("etf.trades.weekly"),
        },
        "record_counts": {
            "candles": candles_n,
            "signals": signals_n,
            "trades": trades_n,
            "indicators_5m_research": ind_n,
        },
        "candles_by_symbol": {sym: n for sym, n in symbols},
        "signals_by_strategy": {s: n for s, n in signal_strats},
        "trades": {
            "holding_hours_mean": statistics.mean(hold_hrs) if hold_hrs else None,
            "holding_hours_median": statistics.median(hold_hrs) if hold_hrs else None,
            "session_distribution": {s or "unknown": n for s, n in sessions},
            "close_reason_distribution": {s: n for s, n in close_reasons},
        },
        "volume_profile": {
            "recent_candle_volume_mean": statistics.mean(vol_samples) if vol_samples else None,
            "recent_candle_volume_median": statistics.median(vol_samples) if vol_samples else None,
        },
        "excluded": ["review", "lessons", "diagnostics", "risk_decisions"],
    }


def _daily_returns(bars: list[dict]) -> list[tuple[str, float]]:
    out = []
    prev = None
    for b in sorted(bars, key=lambda x: x.get("date", "")):
        c = b.get("close")
        if c is None:
            continue
        c = float(c)
        if prev and prev > 0:
            out.append((b["date"], (c - prev) / prev))
        prev = c
    return out


def _align_returns(
    a: list[tuple[str, float]],
    b: list[tuple[str, float]],
    min_days: int = 5,
) -> tuple[list[float], list[float], int]:
    am = {d: r for d, r in a}
    bm = {d: r for d, r in b}
    dates = sorted(set(am) & set(bm))
    if len(dates) < min_days:
        return [], [], len(dates)
    ra = [am[d] for d in dates]
    rb = [bm[d] for d in dates]
    return ra, rb, len(dates)


def _pearson(x: list[float], y: list[float]) -> float | None:
    n = len(x)
    if n < 5:
        return None
    mx, my = statistics.mean(x), statistics.mean(y)
    num = sum((a - mx) * (b - my) for a, b in zip(x, y))
    den = math.sqrt(sum((a - mx) ** 2 for a in x) * sum((b - my) ** 2 for b in y))
    return num / den if den else None


def _spearman(x: list[float], y: list[float]) -> float | None:
    if len(x) < 5:
        return None

    def ranks(vals: list[float]) -> list[float]:
        order = sorted(range(len(vals)), key=lambda i: vals[i])
        r = [0.0] * len(vals)
        for rank, idx in enumerate(order):
            r[idx] = rank + 1
        return r

    return _pearson(ranks(x), ranks(y))


def _lag_scan(a: list[tuple[str, float]], b: list[tuple[str, float]], max_lag: int = 5) -> dict:
    am = {d: r for d, r in a}
    bm = {d: r for d, r in b}
    dates = sorted(set(am) & set(bm))
    best = {"lag": 0, "pearson": None, "n": 0}
    for lag in range(-max_lag, max_lag + 1):
        xs, ys = [], []
        for i, d in enumerate(dates):
            j = i - lag
            if j < 0 or j >= len(dates):
                continue
            d2 = dates[j]
            if d not in am or d2 not in bm:
                continue
            xs.append(am[d])
            ys.append(bm[d2])
        r = _pearson(xs, ys)
        if r is not None and (best["pearson"] is None or abs(r) > abs(best["pearson"] or 0)):
            best = {"lag": lag, "pearson": r, "n": len(xs)}
    return best


def _confidence(n: int, r: float | None) -> str:
    if r is None or n < 30:
        return "low"
    if n >= 200 and abs(r) >= 0.3:
        return "high"
    if n >= 60 and abs(r) >= 0.2:
        return "medium"
    return "low"


def _load_market_daily(symbol: str) -> list[tuple[str, float]]:
    p = HISTORY_MARKETS / f"{symbol}.json"
    if not p.exists():
        return []
    data = json.loads(p.read_text())
    return _daily_returns(data.get("bars", []))


def _load_gold_daily() -> list[tuple[str, float]]:
    p = HISTORICAL / "commodities_march_april_2026.json"
    if not p.exists():
        return []
    data = json.loads(p.read_text())
    bars = data.get("gold", {}).get("data", [])
    daily: dict[str, list[float]] = defaultdict(list)
    for b in bars:
        d = (b.get("date") or b.get("timestamp", ""))[:10]
        if d and b.get("close") is not None:
            daily[d].append(float(b["close"]))
    out = []
    prev = None
    for d in sorted(daily):
        c = statistics.mean(daily[d])
        if prev and prev > 0:
            out.append((d, (c - prev) / prev))
        prev = c
    return out


def _load_funding_daily() -> list[tuple[str, float]]:
    unified = HISTORICAL / "funding_rates.jsonl"
    if unified.exists():
        try:
            from runtime.observation_backfill import funding_daily_from_jsonl

            series = funding_daily_from_jsonl(ROOT, symbol="BTC")
            if series:
                return series
        except Exception:
            pass
    by_day: dict[str, list[float]] = defaultdict(list)
    for p in sorted(HISTORICAL.glob("okx_*_USDT_SWAP_funding_rate_*.json")):
        data = json.loads(p.read_text())
        if isinstance(data, list):
            for item in data:
                ts = item.get("timestamp", "")[:10]
                fr = item.get("funding_rate")
                if ts and fr is not None:
                    by_day[ts].append(float(fr))
    return [(d, statistics.mean(v)) for d, v in sorted(by_day.items())]


def _load_pm_crypto_proxy() -> list[tuple[str, float]]:
    """PM crypto daily returns from Phase 3d live tape (preferred) or replay fallback."""
    tape = HISTORICAL / "pm_crypto_price_tape.jsonl"
    if tape.exists():
        try:
            from runtime.observation_backfill import pm_crypto_daily_returns

            live = pm_crypto_daily_returns(ROOT, asset="BTC")
            if live:
                return live
        except Exception:
            pass
    p = Path("/Users/libo/shared_intelligence/history/replay_dataset.jsonl")
    if not p.exists():
        return []
    rets = []
    with open(p, "r") as f:
        for line in f:
            row = json.loads(line)
            if row.get("asset_class") == "crypto" or "BTC" in str(row.get("symbol", "")):
                r = row.get("return_1d") or row.get("btc_return_1d")
                d = row.get("date")
                if d is not None and r is not None:
                    rets.append((str(d)[:10], float(r)))
    return rets


def _pair_analysis(
    name: str,
    a: list[tuple[str, float]],
    b: list[tuple[str, float]],
    min_days: int = 5,
) -> dict:
    ra, rb, n = _align_returns(a, b, min_days=min_days)
    lag = _lag_scan(a, b)
    pearson0 = _pearson(ra, rb) if len(ra) >= min_days else None
    spearman0 = _spearman(ra, rb) if len(ra) >= min_days else None
    vol_a = statistics.pstdev(ra) if len(ra) > 1 else None
    vol_b = statistics.pstdev(rb) if len(rb) > 1 else None
    vol_ratio = (vol_a / vol_b) if vol_a and vol_b and vol_b > 0 else None
    return {
        "pair": name,
        "sample_size": n,
        "pearson_lag0": pearson0,
        "spearman_lag0": spearman0,
        "best_lag": lag,
        "volatility_transmission": {
            "vol_a_daily": vol_a,
            "vol_b_daily": vol_b,
            "vol_ratio_a_over_b": vol_ratio,
        },
        "confidence": _confidence(n, pearson0),
        "note": "lag>0 => A leads B" if lag.get("lag") else "",
    }


def build_cross_market_report() -> str:
    btc = _load_market_daily("BTC")
    eth = _load_market_daily("ETH")
    qqq = _load_market_daily("QQQ")
    tqqq = _load_market_daily("TQQQ")
    soxl = _load_market_daily("SOXL")
    funding = _load_funding_daily()
    gold = _load_gold_daily()
    pm = _load_pm_crypto_proxy()

    pairs = [
        _pair_analysis("BTC ↔ ETH", btc, eth),
        _pair_analysis("BTC ↔ Funding", btc, funding),
        _pair_analysis("BTC ↔ PM Crypto (live tape)", btc, pm, min_days=3),
        _pair_analysis("QQQ ↔ BTC", qqq, btc),
        _pair_analysis("TQQQ ↔ BTC", tqqq, btc),
        _pair_analysis("SOXL ↔ BTC", soxl, btc),
        _pair_analysis("Gold ↔ BTC", gold, btc),
    ]

    dxy: list[tuple[str, float]] = []
    try:
        from runtime.observation_backfill import load_dxy_daily

        dxy_series = load_dxy_daily(ROOT)
        for i in range(1, len(dxy_series)):
            prev = dxy_series[i - 1][1]
            cur = dxy_series[i][1]
            if prev:
                dxy.append((dxy_series[i][0], (cur - prev) / prev))
    except Exception:
        dxy = []
    if dxy:
        pairs.append(_pair_analysis("DXY ↔ BTC", dxy, btc))
    else:
        pairs.append({
            "pair": "DXY ↔ BTC",
            "sample_size": 0,
            "pearson_lag0": None,
            "spearman_lag0": None,
            "best_lag": {"lag": None, "pearson": None, "n": 0},
            "volatility_transmission": {},
            "confidence": "insufficient_data",
            "note": "dxy_daily.jsonl missing; see research/dxy_manual_input_spec.md",
        })

    lines = [
        "# Cross-Market Discovery Report (Phase 2 Observation)",
        "",
        f"**Generated:** {_now_iso()}  ",
        "**Type:** Read-only statistical research — no signals, no strategy/risk changes**  ",
        "**Principle:** Observation ≠ Experience",
        "",
        "## Scope",
        "",
        "Pairs studied: BTC↔ETH, BTC↔Funding, BTC↔PM Crypto, QQQ↔BTC, TQQQ↔BTC, SOXL↔BTC, DXY↔BTC, Gold↔BTC",
        "",
        "## Summary Table",
        "",
        "| Pair | n | Pearson (lag=0) | Spearman | Best lag | |r| lag | Confidence |",
        "|------|---|-----------------|----------|----------|---------|------------|",
    ]
    for p in pairs:
        bl = p.get("best_lag") or {}
        lines.append(
            f"| {p['pair']} | {p.get('sample_size', 0)} | "
            f"{p.get('pearson_lag0', 'n/a')} | {p.get('spearman_lag0', 'n/a')} | "
            f"{bl.get('lag', 'n/a')} | {bl.get('pearson', 'n/a')} | {p.get('confidence', '')} |"
        )

    lines.extend(["", "## Pair Details", ""])
    for p in pairs:
        lines.append(f"### {p['pair']}")
        lines.append("")
        lines.append(f"- Sample size: **{p.get('sample_size', 0)}**")
        lines.append(f"- Pearson (lag=0): **{p.get('pearson_lag0')}**")
        lines.append(f"- Spearman (lag=0): **{p.get('spearman_lag0')}**")
        bl = p.get("best_lag") or {}
        lines.append(f"- Best lag: **{bl.get('lag')}** (Pearson={bl.get('pearson')}, n={bl.get('n')})")
        vt = p.get("volatility_transmission") or {}
        if vt:
            lines.append(f"- Vol ratio (A/B daily): **{vt.get('vol_ratio_a_over_b')}**")
        if p.get("note"):
            lines.append(f"- Note: {p['note']}")
        lines.append("")

    lines.extend([
        "## Data Sources",
        "",
        "- `shared_intelligence/history/markets/{BTC,ETH,QQQ,TQQQ,SOXL}.json`",
        "- `data/historical/okx_BTC_USDT_SWAP_funding_rate_*.json`",
        "- `data/historical/commodities_march_april_2026.json` (gold hourly → daily)",
        "- `shared_intelligence/history/replay_dataset.jsonl` (PM crypto proxy)",
        "",
        "## Prohibited",
        "",
        "This report does NOT generate trading signals or modify agents/strategy/risk.",
        "",
    ])
    return "\n".join(lines)


def main() -> int:
    catalog = ObservationCatalog()
    okx = build_okx_summary(catalog)
    etf = build_us_etf_summary()
    report = build_cross_market_report()

    (RESEARCH / "okx_observation_summary.json").write_text(
        json.dumps(okx, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    (RESEARCH / "us_etf_observation_summary.json").write_text(
        json.dumps(etf, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    (RESEARCH / "cross_market_discovery_report.md").write_text(report, encoding="utf-8")

    print("Wrote research/okx_observation_summary.json")
    print("Wrote research/us_etf_observation_summary.json")
    print("Wrote research/cross_market_discovery_report.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
