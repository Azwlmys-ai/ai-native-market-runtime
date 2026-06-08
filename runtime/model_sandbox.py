"""
model_sandbox — Phase 3b 模型研究沙盒（只读，不接交易链）
==========================================================
只读订阅 Observation Layer + runtime.db + 历史价格，产出 research/model_sandbox/ 报告。
不写 signals.json / review_results.json / correlation_signals.json / 任何执行产物。

复用 runtime.garch / runtime.regime_hmm / runtime.cointegration 的**分析核**，
但绕过 datastore 落盘与信号组装。
"""

from __future__ import annotations

import json
import math
import sqlite3
import statistics
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import numpy as np

from runtime import cointegration as _coint
from runtime import garch as _garch
from runtime import price_history as _ph

SCHEMA_VERSION = "0.1.0-phase3b-model-sandbox"
SANDBOX_DIR = "research/model_sandbox"
CRYPTO_SYMBOLS = ("BTC", "ETH", "SOL")
OKX_SYMBOL_MAP = {"BTC-USDT": "BTC", "ETH-USDT": "ETH", "SOL-USDT": "SOL", "BNB-USDT": "BNB"}
HISTORY_MARKETS = Path("/Users/libo/shared_intelligence/history/markets")
MIN_REGIME_OBS = 30
REGIME_WINDOW = 24
REGIME_LABELS = ("calm", "trend", "turbulent", "illiquid")

try:
    from hmmlearn.hmm import GaussianHMM  # type: ignore

    _HAS_HMMLEARN = True
except ImportError:
    _HAS_HMMLEARN = False


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sandbox_dir(base_dir: Path) -> Path:
    d = base_dir / SANDBOX_DIR
    d.mkdir(parents=True, exist_ok=True)
    return d


def _confidence_from_n(n: int, medium: int = 25, high: int = 200) -> tuple[str, float]:
    if n < medium:
        return "low", round(20.0 + 30.0 * n / max(medium, 1), 1)
    if n < high:
        return "medium", round(50.0 + 30.0 * (n - medium) / max(high - medium, 1), 1)
    return "high", round(min(90.0, 70.0 + 20.0 * min(n / high, 1.0)), 1)


def _clustering_window(persistence: float) -> Optional[float]:
    """波动冲击半衰期（周期数）：persistence 越高衰减越慢。"""
    if persistence <= 0 or persistence >= 1:
        return None
    return round(math.log(0.5) / math.log(persistence), 2)


def _load_okx_klines(base_dir: Path) -> dict[str, dict]:
    p = base_dir / "data" / "historical" / "okx_klines_march_april_may_2026.json"
    if not p.exists():
        return {}
    raw = json.loads(p.read_text(encoding="utf-8"))
    out: dict[str, dict] = {}
    for key, sym in OKX_SYMBOL_MAP.items():
        block = raw.get(key, {})
        rows = block.get("data") or []
        if not rows:
            continue
        prices, volumes, ts_list = [], [], []
        for row in rows:
            close = row.get("close")
            if close is None:
                continue
            prices.append(float(close))
            volumes.append(float(row.get("volume") or 0))
            ts_list.append(row.get("timestamp", ""))
        if prices:
            out[sym] = {"prices": prices, "volumes": volumes, "ts": ts_list, "source": "okx_klines_hourly"}
    return out


def _load_daily_closes(symbol: str, base_dir: Optional[Path] = None) -> list[float]:
    candidates = []
    if base_dir is not None:
        candidates.append(base_dir / "data" / "historical" / "markets" / f"{symbol}.json")
    candidates.append(HISTORY_MARKETS / f"{symbol}.json")
    for p in candidates:
        if not p.exists():
            continue
        data = json.loads(p.read_text(encoding="utf-8"))
        closes = [float(b["close"]) for b in data.get("bars", []) if b.get("close") is not None]
        if closes:
            return closes
    return []


def load_crypto_series(base_dir: Path, symbol: str) -> dict:
    """加载 crypto 价格序列（优先 OKX 小时线，其次日频 shared_intelligence，最后 asset 滚动）。"""
    okx = _load_okx_klines(base_dir)
    if symbol in okx:
        row = okx[symbol]
        return {"symbol": symbol, "sample_size": len(row["prices"]), **row}

    daily = _load_daily_closes(symbol, base_dir=base_dir)
    if len(daily) >= _garch.MIN_OBS + 1:
        return {
            "symbol": symbol,
            "prices": daily,
            "volumes": [],
            "ts": [],
            "source": "shared_intelligence_daily",
            "sample_size": len(daily),
        }

    asset_hist = _ph.load_asset_history(base_dir)
    prices = _ph.asset_series_for(asset_hist, symbol)
    if len(prices) >= _garch.MIN_OBS + 1:
        return {
            "symbol": symbol,
            "prices": prices,
            "volumes": [],
            "ts": [],
            "source": "asset_price_history",
            "sample_size": len(prices),
        }

    return {
        "symbol": symbol,
        "prices": [],
        "volumes": [],
        "ts": [],
        "source": None,
        "sample_size": 0,
        "status": "insufficient_data",
    }


def read_runtime_db_readonly(base_dir: Path) -> dict:
    db = base_dir / "data" / "runtime.db"
    if not db.exists():
        return {"available": False, "reason": "runtime.db_missing"}
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        mp_rows = conn.execute("SELECT COUNT(*) FROM market_prices").fetchone()[0]
        mp_markets = conn.execute("SELECT COUNT(DISTINCT market_id) FROM market_prices").fetchone()[0]
        ev_rows = conn.execute("SELECT COUNT(*) FROM runtime_events").fetchone()[0]
        return {
            "available": True,
            "market_prices_rows": mp_rows,
            "market_prices_distinct_markets": mp_markets,
            "runtime_events_rows": ev_rows,
            "read_only": True,
        }
    finally:
        conn.close()


def _garch_volatility_state(risk_state: str) -> str:
    return {"elevated": "elevated_vol", "calm": "calm_vol", "normal": "normal_vol"}.get(
        risk_state, risk_state
    )


def run_garch_research(base_dir: Path) -> dict:
    series_results = []
    for sym in CRYPTO_SYMBOLS:
        loaded = load_crypto_series(base_dir, sym)
        n = loaded.get("sample_size", 0)
        if n < _garch.MIN_OBS + 1:
            suff, conf = _confidence_from_n(n)
            series_results.append({
                "symbol": sym,
                "status": "insufficient_data",
                "sample_size": n,
                "source": loaded.get("source"),
                "confidence": conf,
                "data_sufficiency": suff,
            })
            continue

        st = _garch.analyze_series(sym, loaded["prices"])
        if st is None:
            suff, conf = _confidence_from_n(n)
            series_results.append({
                "symbol": sym,
                "status": "insufficient_data",
                "sample_size": n,
                "source": loaded.get("source"),
                "confidence": conf,
                "data_sufficiency": suff,
                "reason": "garch_analyze_rejected",
            })
            continue

        suff = "medium" if st["n_obs"] >= _garch.DATA_SUFFICIENCY_MEDIUM else "low"
        conf = _garch._confidence(st)  # noqa: SLF001 — reuse research confidence kernel
        series_results.append({
            "symbol": sym,
            "status": "ok",
            "source": loaded.get("source"),
            "sample_size": st["n_obs"],
            "volatility_state": _garch_volatility_state(st["risk_state"]),
            "risk_state": st["risk_state"],
            "vol_trend": st["vol_trend"],
            "clustering": st["clustering"],
            "clustering_window_periods": _clustering_window(st["persistence"]),
            "persistence": st["persistence"],
            "current_vol": st["current_vol"],
            "forecast_vol": st["forecast_vol"],
            "vol_spike": st["vol_spike"],
            "confidence": conf,
            "data_sufficiency": suff,
        })

    sufficient = [r for r in series_results if r.get("status") == "ok"]
    return {
        "schema_version": SCHEMA_VERSION,
        "model": "garch",
        "method": _garch.METHOD,
        "generated_at": _now_iso(),
        "principle": "research_only_no_trading_signals",
        "symbols_requested": list(CRYPTO_SYMBOLS),
        "n_sufficient": len(sufficient),
        "n_insufficient": len(series_results) - len(sufficient),
        "series": series_results,
        "forbidden": {"write_signals": True, "write_trading_rules": True},
    }


def _markov_regime_bucket(
    prices: np.ndarray,
    volumes: Optional[np.ndarray] = None,
    window: int = REGIME_WINDOW,
) -> list[str]:
    """简单 regime 分桶：calm / trend / turbulent / illiquid。"""
    n = len(prices)
    if n < 2:
        return ["illiquid"]

    returns = np.diff(prices)
    vol_full = float(np.std(returns)) if len(returns) else 0.0
    vols = []
    trends = []
    for i in range(n):
        start = max(0, i - window)
        seg_p = prices[start : i + 1]
        seg_r = np.diff(seg_p) if len(seg_p) > 1 else np.array([0.0])
        vols.append(float(np.std(seg_r)))
        if len(seg_p) >= 3:
            x = np.arange(len(seg_p), dtype=float)
            slope = float(np.polyfit(x, seg_p, 1)[0])
            trends.append(abs(slope) / max(float(np.mean(seg_p)), 1e-9))
        else:
            trends.append(0.0)

    vol_arr = np.array(vols)
    vol_p10, vol_p75 = np.percentile(vol_arr, 10), np.percentile(vol_arr, 75)
    trend_med = float(np.median(trends))

    vol_low = 0.0
    if volumes is not None and len(volumes) == n:
        vol_low = float(np.percentile(volumes, 20))

    labels = []
    for i in range(n):
        v = vols[i]
        t = trends[i]
        illiquid = v <= vol_p10 * 1.05 and vol_full < 1e-6 * max(float(np.mean(prices)), 1.0)
        if volumes is not None and len(volumes) == n and volumes[i] <= vol_low and v <= vol_p10:
            illiquid = True
        if illiquid:
            labels.append("illiquid")
        elif v >= vol_p75:
            labels.append("turbulent")
        elif t >= trend_med * 1.25:
            labels.append("trend")
        else:
            labels.append("calm")
    return labels


def _label_hmmlearn_states(model, features: np.ndarray) -> dict[int, str]:
    """按各态 |均值收益| 与方差映射到四 regime。"""
    means = model.means_
    vars_ = model.covars_.reshape(-1) if model.covars_.ndim > 1 else model.covars_
    scored = []
    for i in range(len(means)):
        m_abs = abs(float(means[i][0])) if means.ndim > 1 else abs(float(means[i]))
        v = float(vars_[i]) if i < len(vars_) else 1.0
        scored.append((i, m_abs, v))
    scored.sort(key=lambda x: x[2])
    mapping: dict[int, str] = {}
    if len(scored) >= 4:
        mapping[scored[0][0]] = "illiquid"
        mapping[scored[1][0]] = "calm"
        mapping[scored[2][0]] = "trend"
        mapping[scored[3][0]] = "turbulent"
    elif len(scored) == 3:
        mapping[scored[0][0]] = "calm"
        mapping[scored[1][0]] = "trend"
        mapping[scored[2][0]] = "turbulent"
    else:
        for i, (_, m_abs, v) in enumerate(scored):
            mapping[i] = "turbulent" if v > np.median([s[2] for s in scored]) else "calm"
    return mapping


def _analyze_regime_series(symbol: str, loaded: dict) -> dict:
    prices = loaded.get("prices") or []
    n = len(prices)
    if n < MIN_REGIME_OBS:
        suff, conf = _confidence_from_n(n)
        return {
            "symbol": symbol,
            "status": "insufficient_data",
            "sample_size": n,
            "source": loaded.get("source"),
            "confidence": conf,
            "data_sufficiency": suff,
        }

    p = np.asarray(prices, dtype=float)
    volumes = loaded.get("volumes") or []
    vol_arr = np.asarray(volumes, dtype=float) if volumes else None

    method = "markov_regime_bucket"
    regime_path: list[str]

    if _HAS_HMMLEARN and n >= 80:
        returns = np.diff(p)
        if vol_arr is not None and len(vol_arr) == n:
            vol_z = (vol_arr[1:] - np.mean(vol_arr[1:])) / max(np.std(vol_arr[1:]), 1e-9)
            features = np.column_stack([returns, np.abs(returns), vol_z])
        else:
            features = np.column_stack([returns, np.abs(returns)])
        try:
            model = GaussianHMM(n_components=4, covariance_type="diag", n_iter=50, random_state=42)
            model.fit(features)
            states = model.predict(features)
            state_map = _label_hmmlearn_states(model, features)
            regime_path = ["illiquid"] + [state_map.get(int(s), "calm") for s in states]
            method = "hmmlearn_gaussian_hmm_4state"
        except Exception:
            regime_path = _markov_regime_bucket(p, vol_arr)
    else:
        regime_path = _markov_regime_bucket(p, vol_arr)

    dist = Counter(regime_path)
    total = len(regime_path)
    transitions: Counter = Counter()
    for i in range(1, len(regime_path)):
        transitions[(regime_path[i - 1], regime_path[i])] += 1

    current = regime_path[-1]
    suff, conf = _confidence_from_n(n, medium=80, high=500)
    if method == "markov_regime_bucket" and n < 80:
        suff = "low" if suff == "medium" else suff
        conf = min(conf, 55.0)

    return {
        "symbol": symbol,
        "status": "ok",
        "source": loaded.get("source"),
        "sample_size": n,
        "method": method,
        "hmmlearn_available": _HAS_HMMLEARN,
        "current_regime": current,
        "regime_distribution": {k: round(v / total, 4) for k, v in dist.items()},
        "regime_labels": list(REGIME_LABELS),
        "transition_top": [
            {"from": a, "to": b, "count": c}
            for (a, b), c in transitions.most_common(5)
        ],
        "confidence": conf,
        "data_sufficiency": suff,
    }


def run_regime_research(base_dir: Path) -> dict:
    series_results = [_analyze_regime_series(sym, load_crypto_series(base_dir, sym)) for sym in CRYPTO_SYMBOLS]
    sufficient = [r for r in series_results if r.get("status") == "ok"]
    return {
        "schema_version": SCHEMA_VERSION,
        "model": "hmm_regime",
        "generated_at": _now_iso(),
        "principle": "research_only_no_trading_signals",
        "fallback": "markov_regime_bucket" if not _HAS_HMMLEARN else "hmmlearn_or_bucket",
        "hmmlearn_available": _HAS_HMMLEARN,
        "regime_labels": list(REGIME_LABELS),
        "n_sufficient": len(sufficient),
        "n_insufficient": len(series_results) - len(sufficient),
        "series": series_results,
        "forbidden": {"write_signals": True, "write_trading_rules": True},
    }


def _load_funding_daily(base_dir: Path, symbol: str = "BTC") -> list[tuple[str, float]]:
    """Daily-mean funding — prefer Phase 3d unified funding_rates.jsonl."""
    unified = base_dir / "data" / "historical" / "funding_rates.jsonl"
    if unified.exists():
        try:
            from runtime.observation_backfill import funding_daily_from_jsonl

            series = funding_daily_from_jsonl(base_dir, symbol=symbol)
            if series:
                return series
        except Exception:
            pass
    by_day: dict[str, list[float]] = {}
    hist = base_dir / "data" / "historical"
    for p in sorted(hist.glob(f"okx_{symbol}_USDT_SWAP_funding_rate_*.json")):
        data = json.loads(p.read_text(encoding="utf-8"))
        if not isinstance(data, list):
            continue
        for item in data:
            ts = (item.get("timestamp") or "")[:10]
            fr = item.get("funding_rate")
            if ts and fr is not None:
                by_day.setdefault(ts, []).append(float(fr))
    return [(d, statistics.mean(v)) for d, v in sorted(by_day.items())]


def _load_all_funding_daily(base_dir: Path) -> dict[str, list[tuple[str, float]]]:
    return {sym: _load_funding_daily(base_dir, sym) for sym in CRYPTO_SYMBOLS}


def _daily_returns_from_prices(prices: list[float], dates: Optional[list[str]] = None) -> list[tuple[str, float]]:
    if len(prices) < 2:
        return []
    if dates and len(dates) == len(prices):
        by_day: dict[str, list[float]] = {}
        for i, p in enumerate(prices):
            day = (dates[i] or "")[:10]
            if day:
                by_day.setdefault(day, []).append(float(p))
        days = sorted(by_day)
        out = []
        for i in range(1, len(days)):
            prev_p = by_day[days[i - 1]][-1]
            cur_p = by_day[days[i]][-1]
            if prev_p == 0:
                continue
            out.append((days[i], (cur_p - prev_p) / prev_p))
        return out

    out = []
    for i in range(1, len(prices)):
        prev, cur = prices[i - 1], prices[i]
        if prev == 0:
            continue
        d = dates[i] if dates and i < len(dates) else str(i)
        out.append((d[:10] if len(d) >= 10 else d, (cur - prev) / prev))
    return out


def _align_series_by_date(
    a: list[tuple[str, float]],
    b: list[tuple[str, float]],
) -> tuple[list[float], list[float], int]:
    am = {d: v for d, v in a}
    bm = {d: v for d, v in b}
    common = sorted(set(am) & set(bm))
    if not common:
        return [], [], 0
    return [am[d] for d in common], [bm[d] for d in common], len(common)


def _funding_lag_scan(btc_daily: list[tuple[str, float]], funding_daily: list[tuple[str, float]]) -> dict:
    btc_ret, fund, n = _align_series_by_date(btc_daily, funding_daily)
    if n < 10:
        return {"status": "insufficient_data", "sample_size": n, "best_lag": None, "best_corr": None}

    best_lag, best_corr = 0, None
    for lag in range(-3, 4):
        xs, ys = [], []
        for i in range(n):
            j = i + lag
            if 0 <= j < n:
                xs.append(fund[j])
                ys.append(btc_ret[i])
        if len(xs) < 10:
            continue
        corr = float(np.corrcoef(xs, ys)[0, 1]) if np.std(xs) > 0 and np.std(ys) > 0 else None
        if corr is not None and (best_corr is None or abs(corr) > abs(best_corr)):
            best_corr, best_lag = corr, lag

    suff, conf = _confidence_from_n(n, medium=60, high=180)
    return {
        "status": "ok" if best_corr is not None else "insufficient_data",
        "sample_size": n,
        "best_lag_days": best_lag,
        "best_corr": round(best_corr, 4) if best_corr is not None else None,
        "interpretation": "funding_leads_btc" if (best_lag or 0) < 0 else "funding_lags_btc_or_contemporaneous",
        "confidence": conf,
        "data_sufficiency": suff,
    }


def run_cointegration_research(base_dir: Path) -> dict:
    btc = load_crypto_series(base_dir, "BTC")
    eth = load_crypto_series(base_dir, "ETH")

    pair_result: dict
    n_align = min(len(btc.get("prices", [])), len(eth.get("prices", [])))
    if n_align < _coint.MIN_POINTS:
        suff, conf = _confidence_from_n(n_align)
        pair_result = {
            "pair": "BTC-ETH",
            "status": "insufficient_data",
            "sample_size": n_align,
            "confidence": conf,
            "data_sufficiency": suff,
        }
    else:
        st = _coint.analyze_pair("BTC", btc["prices"], "ETH", eth["prices"])
        if st is None:
            suff, conf = _confidence_from_n(n_align)
            pair_result = {
                "pair": "BTC-ETH",
                "status": "insufficient_data",
                "sample_size": n_align,
                "confidence": conf,
                "data_sufficiency": suff,
                "reason": "cointegration_analyze_rejected",
            }
        else:
            is_candidate = _coint._is_candidate(st)  # noqa: SLF001
            suff = "medium" if st["n_points"] >= _coint.DATA_SUFFICIENCY_MEDIUM else "low"
            conf = _coint._confidence(st)  # noqa: SLF001
            pair_result = {
                "pair": "BTC-ETH",
                "status": "ok",
                "sample_size": st["n_points"],
                "spread": {
                    "beta": st["beta"],
                    "corr": st["corr"],
                    "zscore": st["zscore"],
                    "half_life": st["half_life"],
                    "ar1_phi": st["ar1_phi"],
                    "spread_std": st["spread_std"],
                },
                "research_candidate": is_candidate,
                "trading_signal": False,
                "confidence": conf,
                "data_sufficiency": suff,
                "note": "observation_only — not promoted to signals.json",
            }

    btc_daily = _daily_returns_from_prices(
        btc.get("prices", []) or _load_daily_closes("BTC", base_dir=base_dir),
        dates=btc.get("ts") or None,
    )
    funding_by_symbol = _load_all_funding_daily(base_dir)
    funding_lag = {
        sym: _funding_lag_scan(btc_daily, series)
        for sym, series in funding_by_symbol.items()
    }
    funding_lag["BTC"] = funding_lag.get("BTC") or _funding_lag_scan(
        btc_daily, funding_by_symbol.get("BTC", [])
    )

    return {
        "schema_version": SCHEMA_VERSION,
        "model": "cointegration",
        "method": _coint.METHOD,
        "generated_at": _now_iso(),
        "principle": "research_only_no_trading_signals",
        "btc_eth_spread": pair_result,
        "funding_lag": funding_lag.get("BTC", {}),
        "funding_lag_by_symbol": funding_lag,
        "funding_sample_sizes": {s: len(v) for s, v in funding_by_symbol.items()},
        "candidates": [pair_result] if pair_result.get("research_candidate") else [],
        "forbidden": {"write_signals": True, "write_correlation_signals": True},
    }


def _etf_indicators_available(base_dir: Path) -> bool:
    p = base_dir / "research" / "us_etf_observation_summary.json"
    if not p.exists():
        return False
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return int(data.get("record_counts", {}).get("indicators_5m_research", 0)) > 0
    except Exception:
        return False


def _write_json(path: Path, obj: dict) -> None:
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _write_garch_md(report: dict) -> str:
    lines = [
        "# GARCH Volatility Research (Phase 3b Sandbox)",
        "",
        f"**Generated:** {report['generated_at']}",
        f"**Principle:** {report['principle']}",
        "",
        "## Series",
        "",
    ]
    for s in report.get("series", []):
        if s.get("status") == "insufficient_data":
            lines.append(f"- **{s['symbol']}**: insufficient_data (n={s.get('sample_size', 0)})")
        else:
            lines.append(
                f"- **{s['symbol']}**: volatility_state={s.get('volatility_state')}, "
                f"clustering={s.get('clustering')}, window={s.get('clustering_window_periods')}, "
                f"n={s.get('sample_size')}, confidence={s.get('confidence')}"
            )
    lines.extend(["", "## Prohibited", "", "No trading signals. No writes to signals.json."])
    return "\n".join(lines) + "\n"


def _write_regime_md(report: dict) -> str:
    lines = [
        "# HMM Regime Research (Phase 3b Sandbox)",
        "",
        f"**Generated:** {report['generated_at']}",
        f"**Method:** {report.get('fallback')}",
        f"**hmmlearn:** {report.get('hmmlearn_available')}",
        "",
        "## Series",
        "",
    ]
    for s in report.get("series", []):
        if s.get("status") == "insufficient_data":
            lines.append(f"- **{s['symbol']}**: insufficient_data (n={s.get('sample_size', 0)})")
        else:
            lines.append(
                f"- **{s['symbol']}**: regime={s.get('current_regime')}, "
                f"method={s.get('method')}, n={s.get('sample_size')}, confidence={s.get('confidence')}"
            )
            dist = s.get("regime_distribution") or {}
            if dist:
                lines.append(f"  - distribution: {dist}")
    lines.extend(["", "## Prohibited", "", "No trading signals."])
    return "\n".join(lines) + "\n"


def _write_coint_md(report: dict) -> str:
    spread = report.get("btc_eth_spread", {})
    fl = report.get("funding_lag", {})
    lines = [
        "# Cointegration Research (Phase 3b Sandbox)",
        "",
        f"**Generated:** {report['generated_at']}",
        "",
        "## BTC-ETH Spread",
        "",
    ]
    if spread.get("status") == "insufficient_data":
        lines.append(f"- insufficient_data (n={spread.get('sample_size', 0)})")
    else:
        sp = spread.get("spread", {})
        lines.append(
            f"- corr={sp.get('corr')}, z={sp.get('zscore')}, half_life={sp.get('half_life')}, "
            f"candidate={spread.get('research_candidate')}, n={spread.get('sample_size')}"
        )
    lines.extend(["", "## Funding Lag", ""])
    if fl.get("status") == "insufficient_data":
        lines.append(f"- insufficient_data (n={fl.get('sample_size', 0)})")
    else:
        lines.append(
            f"- best_lag={fl.get('best_lag_days')}d, corr={fl.get('best_corr')}, "
            f"n={fl.get('sample_size')}, confidence={fl.get('confidence')}"
        )
    lines.extend(["", "## Prohibited", "", "No correlation_signals.json. No trading signals."])
    return "\n".join(lines) + "\n"


def compute(base_dir: Optional[Path] = None) -> dict:
    """运行 Phase 3b 模型沙盒，仅写 research/model_sandbox/。"""
    root = Path(base_dir) if base_dir else Path(__file__).resolve().parent.parent
    out_dir = _sandbox_dir(root)

    garch_rep = run_garch_research(root)
    regime_rep = run_regime_research(root)
    coint_rep = run_cointegration_research(root)
    runtime_obs = read_runtime_db_readonly(root)

    pca_status = "deferred"
    pca_reason = "etf_indicators_5m_unavailable"
    if _etf_indicators_available(root):
        pca_status = "deferred"
        pca_reason = "pca_not_in_phase3b_scope"

    outputs = {
        "garch_json": out_dir / "garch_volatility_report.json",
        "garch_md": out_dir / "garch_volatility_report.md",
        "regime_json": out_dir / "regime_hmm_report.json",
        "regime_md": out_dir / "regime_hmm_report.md",
        "coint_json": out_dir / "cointegration_report.json",
        "coint_md": out_dir / "cointegration_report.md",
    }

    _write_json(outputs["garch_json"], garch_rep)
    outputs["garch_md"].write_text(_write_garch_md(garch_rep), encoding="utf-8")
    _write_json(outputs["regime_json"], regime_rep)
    outputs["regime_md"].write_text(_write_regime_md(regime_rep), encoding="utf-8")
    _write_json(outputs["coint_json"], coint_rep)
    outputs["coint_md"].write_text(_write_coint_md(coint_rep), encoding="utf-8")

    summary = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": _now_iso(),
        "principle": "research_only_no_trading_signals",
        "models": {
            "garch": {
                "data_sufficient": garch_rep["n_sufficient"] > 0,
                "n_sufficient": garch_rep["n_sufficient"],
                "symbols_ok": [s["symbol"] for s in garch_rep["series"] if s.get("status") == "ok"],
            },
            "hmm_regime": {
                "data_sufficient": regime_rep["n_sufficient"] > 0,
                "n_sufficient": regime_rep["n_sufficient"],
                "symbols_ok": [s["symbol"] for s in regime_rep["series"] if s.get("status") == "ok"],
            },
            "cointegration": {
                "data_sufficient": coint_rep["btc_eth_spread"].get("status") == "ok",
                "funding_lag_sufficient": coint_rep["funding_lag"].get("status") == "ok",
            },
            "pca": {"status": pca_status, "reason": pca_reason},
        },
        "observation_gaps": [
            {"model": "funding_lag", "gap": "BTC funding n~60; extend historical funding series"}
            if coint_rep["funding_lag"].get("sample_size", 0) < 60
            else None,
            {"model": "pca", "gap": "ETF indicators_5m empty; populate tsll_research.db"}
            if not _etf_indicators_available(root)
            else None,
            {"model": "hmm_regime", "gap": "SOL daily-only fallback if OKX missing"}
            if not any(s["symbol"] == "SOL" and s.get("status") == "ok" for s in regime_rep["series"])
            else None,
        ],
        "runtime_observation": runtime_obs,
        "output_paths": {k: str(v) for k, v in outputs.items()},
        "forbidden": {
            "write_signals": True,
            "write_review_results": True,
            "write_correlation_signals": True,
            "write_trading_rules": True,
        },
    }
    summary["observation_gaps"] = [g for g in summary["observation_gaps"] if g]

    return {
        "garch": garch_rep,
        "regime": regime_rep,
        "cointegration": coint_rep,
        "summary": summary,
        "output_paths": summary["output_paths"],
    }
