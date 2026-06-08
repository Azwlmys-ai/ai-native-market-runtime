"""
observation_learning — Phase 3 只读 Observation 订阅（Learning Agent 观测入口）

原则：Share Observation, not Experience
- 只读 Phase 2 summaries、market_intelligence、runtime.db 观测表
- 输出 research/observation_learning_snapshot_*（不进 data/ 交易链路）
- 禁止写入 signals.json / review_results.json / learned_rules / rule_weights
"""

from __future__ import annotations

import json
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

SCHEMA_VERSION = "0.1.0-phase3-observation-learning"

_FORBIDDEN_WRITE_NAMES = frozenset({
    "signals.json",
    "review_results.json",
    "approved_signals.json",
    "learned_rules.json",
    "learning_knowledge_base.json",
    "rule_effectiveness.json",
    "model_effectiveness.json",
})

_HIGH_CONFIDENCE_MIN_N = 200
_HIGH_CONFIDENCE_MIN_R = 0.35


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_json(path: Path) -> Any:
    if not path.exists():
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _read_text(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def _assert_research_output(path: Path) -> None:
    name = path.name
    if name in _FORBIDDEN_WRITE_NAMES:
        raise PermissionError(f"forbidden write target: {name}")
    if "data" in path.parts and path.suffix == ".json":
        forbidden = {"signals", "review_results", "approved_signals", "learned_rules"}
        if any(x in path.name for x in forbidden):
            raise PermissionError(f"forbidden data/ write: {path}")


def parse_cross_market_report(md_text: str) -> list[dict]:
    """Parse summary table from cross_market_discovery_report.md."""
    pairs = []
    for raw in md_text.splitlines():
        line = raw.strip()
        if not line.startswith("|") or "Pair" in line or "---" in line:
            continue
        cols = [c.strip() for c in line.strip("|").split("|")]
        if len(cols) < 7:
            continue
        pair, n_s, pearson, spearman, best_lag = cols[:5]
        r_lag = cols[5] if len(cols) > 5 else None
        confidence = cols[-1]
        try:
            n = int(n_s)
        except ValueError:
            n = 0
        pearson_v = None if pearson in ("None", "n/a", "") else float(pearson)
        pairs.append({
            "pair": pair,
            "sample_size": n,
            "pearson_lag0": pearson_v,
            "spearman_lag0": None if spearman in ("None", "n/a") else _safe_float(spearman),
            "best_lag": _safe_int(best_lag),
            "best_lag_pearson": _safe_float(r_lag),
            "confidence": confidence,
        })
    return pairs


def _safe_float(v) -> Optional[float]:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _safe_int(v) -> Optional[int]:
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def _summarize_market_intelligence(mi: dict | None) -> dict:
    if not mi:
        return {"available": False}
    tiers = mi.get("tier_distribution") or {}
    profiles = mi.get("profiles") or []
    tradability = [p.get("tradability_score") for p in profiles if p.get("tradability_score") is not None]
    return {
        "available": True,
        "generated_at": mi.get("generated_at"),
        "markets_total": mi.get("markets_total", len(profiles)),
        "tier_distribution": tiers,
        "tier_s_count": tiers.get("S", 0),
        "tier_c_count": tiers.get("C", 0),
        "tradability_mean": sum(tradability) / len(tradability) if tradability else None,
        "shadow_only": mi.get("phase") == "shadow",
    }


def _read_runtime_observation(db_path: Path) -> dict:
    if not db_path.exists():
        return {"available": False}
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        mp_count = conn.execute("SELECT COUNT(*) FROM market_prices").fetchone()[0]
        mp_markets = conn.execute("SELECT COUNT(DISTINCT market_id) FROM market_prices").fetchone()[0]
        ev_count = conn.execute("SELECT COUNT(*) FROM runtime_events").fetchone()[0]
        ev_types = conn.execute(
            "SELECT type, COUNT(*) c FROM runtime_events GROUP BY type ORDER BY c DESC LIMIT 8"
        ).fetchall()
        recent = conn.execute(
            "SELECT type, agent, ts FROM runtime_events ORDER BY ts DESC LIMIT 5"
        ).fetchall()
        return {
            "available": True,
            "market_prices_rows": mp_count,
            "market_prices_distinct_markets": mp_markets,
            "runtime_events_rows": ev_count,
            "event_type_top": {t: c for t, c in ev_types},
            "recent_events": [{"type": t, "agent": a, "ts": ts} for t, a, ts in recent],
        }
    finally:
        conn.close()


def _classify_stable_correlations(pairs: list[dict]) -> list[dict]:
    stable = []
    for p in pairs:
        n = p.get("sample_size") or 0
        r = p.get("pearson_lag0")
        conf = p.get("confidence", "")
        if r is None or n < _HIGH_CONFIDENCE_MIN_N:
            continue
        if conf == "high" or (abs(r) >= _HIGH_CONFIDENCE_MIN_R and n >= _HIGH_CONFIDENCE_MIN_N):
            stable.append({
                "pair": p["pair"],
                "pearson_lag0": r,
                "sample_size": n,
                "confidence": conf or "medium",
                "note": "observation_only — not a trading rule",
            })
    return stable


def _insufficient_samples(
    pairs: list[dict],
    okx: dict | None,
    etf: dict | None,
    mi: dict,
    runtime: dict,
) -> list[dict]:
    gaps = []
    for p in pairs:
        n = p.get("sample_size") or 0
        conf = p.get("confidence", "")
        if n == 0 or conf in ("low", "insufficient_data"):
            gaps.append({
                "area": p["pair"],
                "sample_size": n,
                "reason": "cross_market_pair_underpowered",
            })
    if okx:
        fr_n = (okx.get("funding") or {}).get("btc_swap_observations") or 0
        if fr_n < 120:
            gaps.append({
                "area": "BTC funding series",
                "sample_size": fr_n,
                "reason": "funding_history_short_vs_daily_btc",
            })
    if etf:
        if (etf.get("record_counts") or {}).get("indicators_5m_research", 0) == 0:
            gaps.append({
                "area": "US ETF indicators_5m",
                "sample_size": 0,
                "reason": "research_db_indicators_empty",
            })
    if not mi.get("available"):
        gaps.append({"area": "market_intelligence.json", "sample_size": 0, "reason": "missing"})
    elif mi.get("tier_s_count", 0) == 0:
        gaps.append({
            "area": "market_intelligence tier-S",
            "sample_size": mi.get("markets_total", 0),
            "reason": "no_high_tradability_tier_markets",
        })
    if not runtime.get("available"):
        gaps.append({"area": "runtime.db", "sample_size": 0, "reason": "missing"})
    return gaps


def _continue_collecting(gaps: list[dict], mi: dict) -> list[dict]:
    items = []
    priority = {
        "BTC ↔ PM Crypto (replay proxy)": "pm_crypto_price_history + PM market match",
        "DXY ↔ BTC": "DXY daily series into catalog allowlist",
        "BTC funding series": "extend okx funding historical merge",
        "US ETF indicators_5m": "populate tsll_research.db indicators pipeline",
        "market_intelligence tier-S": "wire shadow MI to learning read path (still no trade)",
        "commodity_forex sidecar": "fix collector to fill commodity_forex_data.json",
    }
    for g in gaps:
        area = g["area"]
        items.append({
            "observation": area,
            "priority": "high" if g.get("sample_size", 0) == 0 else "medium",
            "action": priority.get(area, "extend_observation_sampling"),
            "experience_forbidden": True,
        })
    if mi.get("available") and mi.get("shadow_only"):
        items.append({
            "observation": "market_intelligence profiles",
            "priority": "medium",
            "action": "consume_shadow_profiles_in_observation_learning_only",
            "experience_forbidden": True,
        })
    return items


def _model_research_candidates(
    pairs: list[dict],
    okx: dict | None,
    etf: dict | None,
    runtime: dict,
) -> dict:
    btc_eth = next((p for p in pairs if "BTC" in p["pair"] and "ETH" in p["pair"]), None)
    etf_btc = [p for p in pairs if "BTC" in p["pair"] and any(x in p["pair"] for x in ("QQQ", "TQQQ", "SOXL"))]
    funding = next((p for p in pairs if "Funding" in p["pair"]), None)

    return {
        "garch": {
            "rationale": "Volatility transmission + OKX hold-time dispersion + runtime vol states",
            "signals": {
                "okx_hold_sec_p90": (okx or {}).get("holding_time", {}).get("memory_hold_sec_p90"),
                "high_vol_ratio_pairs": [
                    p["pair"] for p in pairs
                    if "SOXL" in p.get("pair", "") or "Funding" in p.get("pair", "")
                ],
                "runtime_volatility_states": runtime.get("available", False),
            },
            "priority": "high" if okx else "medium",
            "experience_forbidden": True,
        },
        "hmm": {
            "rationale": "Regime shifts across BTC/ETH/ETF; existing regime_states table",
            "signals": {
                "btc_eth_correlation": (btc_eth or {}).get("pearson_lag0"),
                "etf_btc_pairs": len(etf_btc),
                "runtime_regime_states": runtime.get("available", False),
            },
            "priority": "high" if btc_eth and (btc_eth.get("pearson_lag0") or 0) > 0.7 else "medium",
            "experience_forbidden": True,
        },
        "pca": {
            "rationale": "Co-movement among QQQ/TQQQ/SOXL/ETF candle universe",
            "signals": {
                "etf_symbols": list((etf or {}).get("candles_by_symbol", {}).keys()),
                "etf_candles_total": (etf or {}).get("record_counts", {}).get("candles"),
                "correlated_etf_btc_pairs": [
                    {"pair": p["pair"], "r": p.get("pearson_lag0")} for p in etf_btc
                ],
            },
            "priority": "medium",
            "experience_forbidden": True,
        },
        "cointegration": {
            "rationale": "BTC-ETH spread + ETF-BTC lead/lag; existing cointegration module",
            "signals": {
                "btc_eth_n": (btc_eth or {}).get("sample_size"),
                "btc_eth_r": (btc_eth or {}).get("pearson_lag0"),
                "funding_lag_signal": (funding or {}).get("best_lag"),
                "runtime_correlation_signals": runtime.get("available", False),
            },
            "priority": "high",
            "experience_forbidden": True,
        },
    }


def compute(
    base_dir: Optional[Path] = None,
    *,
    date_suffix: str = "20260607",
) -> dict:
    """
    Build observation learning snapshot (read-only inputs).
    Writes only to research/observation_learning_snapshot_{date_suffix}.*
    """
    base = Path(base_dir) if base_dir else Path(__file__).resolve().parent.parent
    research = base / "research"
    data = base / "data"

    okx = _load_json(research / "okx_observation_summary.json")
    etf = _load_json(research / "us_etf_observation_summary.json")
    cross_md = _read_text(research / "cross_market_discovery_report.md")
    pairs = parse_cross_market_report(cross_md)
    mi_raw = _load_json(data / "market_intelligence.json")
    mi = _summarize_market_intelligence(mi_raw)
    runtime = _read_runtime_observation(data / "runtime.db")

    stable = _classify_stable_correlations(pairs)
    gaps = _insufficient_samples(pairs, okx, etf, mi, runtime)
    collect = _continue_collecting(gaps, mi)
    models = _model_research_candidates(pairs, okx, etf, runtime)

    snapshot = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": _now_iso(),
        "principle": "Share Observation, not Experience",
        "learning_entry": "runtime.observation_learning.compute (parallel to model_effectiveness, not Agent G Experience)",
        "inputs": {
            "okx_observation_summary": str(research / "okx_observation_summary.json"),
            "us_etf_observation_summary": str(research / "us_etf_observation_summary.json"),
            "cross_market_discovery_report": str(research / "cross_market_discovery_report.md"),
            "market_intelligence": str(data / "market_intelligence.json"),
            "runtime_db": str(data / "runtime.db"),
        },
        "stable_correlations": stable,
        "insufficient_samples": gaps,
        "continue_collecting": collect,
        "model_research_candidates": models,
        "cross_market_pairs": pairs,
        "market_intelligence_summary": mi,
        "runtime_observation": runtime,
        "okx_observation_highlights": {
            "combined_records": (okx or {}).get("record_counts", {}).get("combined"),
            "funding_observations": (okx or {}).get("funding", {}).get("btc_swap_observations"),
            "top_exit_reasons": list(((okx or {}).get("exit_reason") or {}).keys())[:5],
        },
        "us_etf_observation_highlights": {
            "candles": (etf or {}).get("record_counts", {}).get("candles"),
            "trades": (etf or {}).get("record_counts", {}).get("trades"),
            "symbols": list((etf or {}).get("candles_by_symbol", {}).keys()),
        },
        "forbidden": {
            "experience_import": True,
            "write_trading_rules": True,
            "write_signals": True,
            "write_review_results": True,
            "okx_etf_source_mutation": True,
        },
    }

    json_path = research / f"observation_learning_snapshot_{date_suffix}.json"
    md_path = research / f"observation_learning_snapshot_{date_suffix}.md"
    _assert_research_output(json_path)
    _assert_research_output(md_path)

    json_path.write_text(json.dumps(snapshot, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    md_path.write_text(_render_markdown(snapshot), encoding="utf-8")

    snapshot["output_paths"] = {"json": str(json_path), "markdown": str(md_path)}
    return snapshot


def _render_markdown(snap: dict) -> str:
    lines = [
        "# Observation Learning Snapshot (Phase 3)",
        "",
        f"**Generated:** {snap.get('generated_at')}  ",
        f"**Principle:** {snap.get('principle')}  ",
        f"**Entry:** `{snap.get('learning_entry')}`",
        "",
        "## Stable Correlations (observation only)",
        "",
    ]
    for item in snap.get("stable_correlations", []):
        lines.append(f"- **{item['pair']}**: r={item.get('pearson_lag0')}, n={item.get('sample_size')} ({item.get('confidence')})")
    lines.extend(["", "## Insufficient Samples", ""])
    for g in snap.get("insufficient_samples", []):
        lines.append(f"- **{g['area']}**: n={g.get('sample_size')} — {g.get('reason')}")
    lines.extend(["", "## Continue Collecting", ""])
    for c in snap.get("continue_collecting", []):
        lines.append(f"- [{c.get('priority')}] **{c['observation']}** → {c.get('action')}")
    lines.extend(["", "## Model Research Candidates", ""])
    for name, body in (snap.get("model_research_candidates") or {}).items():
        lines.append(f"### {name.upper()}")
        lines.append(f"- Priority: **{body.get('priority')}**")
        lines.append(f"- Rationale: {body.get('rationale')}")
        lines.append(f"- Experience forbidden: **{body.get('experience_forbidden')}**")
        lines.append("")
    lines.extend([
        "## Runtime Observation",
        "",
        f"- market_prices rows: **{(snap.get('runtime_observation') or {}).get('market_prices_rows', 'n/a')}**",
        f"- runtime_events rows: **{(snap.get('runtime_observation') or {}).get('runtime_events_rows', 'n/a')}**",
        "",
        "## Prohibited",
        "",
        "No trading signals. No writes to signals.json / review_results.json / learned_rules / rule_weights.",
        "",
    ])
    return "\n".join(lines)
