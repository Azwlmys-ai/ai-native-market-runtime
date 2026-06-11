#!/usr/bin/env python3
"""Summarize 24-cycle final validation and write checkpoint report."""

from __future__ import annotations

import json
import statistics
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DATA = REPO / "data"
REPORTS = REPO / "reports"
CYCLES_FILE = DATA / "final_validation_cycles.jsonl"
MARKER = DATA / "final_validation_marker.json"
OUT_JSON = DATA / "final_validation_summary.json"
OUT_MD = REPORTS / "final_validation_24_report.md"


def _load_cycles() -> list[dict]:
    if not CYCLES_FILE.exists():
        return []
    cycles = []
    for ln in CYCLES_FILE.read_text(encoding="utf-8").splitlines():
        if ln.strip():
            cycles.append(json.loads(ln))
    marker = {}
    if MARKER.exists():
        marker = json.loads(MARKER.read_text(encoding="utf-8"))
    start = (marker.get("validation_start") or "")[:19]
    if start:
        cycles = [c for c in cycles if c.get("started_at", "") >= start]
    return cycles


def _pct(xs: list[float], p: float) -> float:
    s = sorted(xs)
    return s[min(int(len(s) * p / 100), len(s) - 1)] if s else 0.0


def main() -> int:
    cycles = _load_cycles()
    marker = json.loads(MARKER.read_text()) if MARKER.exists() else {}
    n = len(cycles)

    paper_ok = sum(1 for c in cycles if c.get("paper_exit") == 0)
    cm_ok = sum(1 for c in cycles if c.get("cross_market_exit") == 0)
    beta_ok = sum(1 for c in cycles if c.get("crypto_beta_exit") == 0)
    exit_ok = sum(1 for c in cycles if c.get("exit_code") == 0)

    b_timeouts = sum(1 for c in cycles if c.get("agent_b", {}).get("timeout"))
    b_timeout_rate = round(b_timeouts / n * 100, 1) if n else None

    winners: dict[str, int] = {}
    hedge_count = 0
    b_elapsed = []
    for c in cycles:
        ab = c.get("agent_b", {})
        w = ab.get("winner")
        if w:
            winners[w] = winners.get(w, 0) + 1
        if ab.get("hedge_triggered"):
            hedge_count += 1
        if ab.get("elapsed_sec") is not None:
            b_elapsed.append(float(ab["elapsed_sec"]))

    signals = [c.get("paper", {}).get("signals") for c in cycles if c.get("paper", {}).get("signals") is not None]
    signals = [int(s) for s in signals]

    postmortems_start = marker.get("postmortems_start", 0)
    closed_start = marker.get("closed_start", 0)
    postmortems_end = cycles[-1]["paper"]["postmortems"] if cycles else postmortems_start
    closed_end = cycles[-1]["paper"]["closed"] if cycles else closed_start

    all_touched = []
    for c in cycles:
        all_touched.extend(c.get("isolation", {}).get("touched_trading_paths") or [])

    cm_brief_ok = sum(
        1
        for c in cycles
        if c.get("cross_market", {}).get("us_cn_brief_generated")
        and c.get("cross_market", {}).get("cn_us_brief_generated")
    )
    beta_report_ok = sum(
        1
        for c in cycles
        if c.get("crypto_beta", {}).get("beta_report_generated")
    )

    total_errors = sum(len(c.get("paper", {}).get("errors") or []) for c in cycles)

    passed = (
        n >= 24
        and exit_ok == n
        and (b_timeout_rate is not None and b_timeout_rate < 15)
        and cm_ok == n
        and beta_ok == n
        and len(all_touched) == 0
        and postmortems_end >= 25
    )

    status = "STABLE OBSERVATION PHASE" if passed else "NEEDS FIX"

    summary = {
        "generated_at": datetime.now().isoformat(),
        "validation_start": marker.get("validation_start"),
        "cycles_recorded": n,
        "status": status,
        "paper_loop": {
            "success_rate": f"{exit_ok}/{n}",
            "paper_exit_ok": f"{paper_ok}/{n}",
        },
        "agent_b": {
            "timeout_rate_pct": b_timeout_rate,
            "timeout_count": b_timeouts,
            "winner_distribution": winners,
            "hedge_triggered_count": hedge_count,
            "elapsed_p50_sec": round(_pct(b_elapsed, 50), 1) if b_elapsed else None,
            "elapsed_p90_sec": round(_pct(b_elapsed, 90), 1) if b_elapsed else None,
        },
        "cross_market": {
            "brief_pairs_ok": f"{cm_brief_ok}/{n}",
            "success_rate_pct": round(cm_ok / n * 100, 1) if n else None,
        },
        "crypto_beta": {
            "report_ok": f"{beta_report_ok}/{n}",
            "success_rate_pct": round(beta_ok / n * 100, 1) if n else None,
        },
        "signals": {
            "mean": round(statistics.mean(signals), 1) if signals else None,
            "median": round(statistics.median(signals), 1) if signals else None,
            "max": max(signals) if signals else None,
            "min": min(signals) if signals else None,
            "samples": signals,
        },
        "closed": {
            "start": closed_start,
            "end": closed_end,
            "delta": closed_end - closed_start,
        },
        "postmortems": {
            "start": postmortems_start,
            "end": postmortems_end,
            "delta": postmortems_end - postmortems_start,
        },
        "errors_total": total_errors,
        "touched_trading_paths": all_touched,
        "checkpoint": {
            "paper_loop_stable": exit_ok == n if n else False,
            "agent_b_fixed": b_timeout_rate is not None and b_timeout_rate < 15,
            "cross_market_stable": cm_ok == n if n else False,
            "crypto_beta_stable": beta_ok == n if n else False,
            "postmortems_target_met": postmortems_end >= 25,
            "stable_observation_phase": passed,
        },
        "cycles": cycles,
    }

    OUT_JSON.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    REPORTS.mkdir(parents=True, exist_ok=True)

    md = f"""# Final Validation — 24 Cycle Report

**Generated:** {summary['generated_at']}
**STATUS:** {status}

## 1. Paper Loop
- Success rate: **{exit_ok}/{n}**
- Paper exit OK: **{paper_ok}/{n}**

## 2. Agent B (Hedged Race)
- Timeout rate: **{b_timeout_rate}%** ({b_timeouts}/{n})
- Winner distribution: {json.dumps(winners)}
- Hedge triggered: **{hedge_count}**
- p50: **{summary['agent_b']['elapsed_p50_sec']}s** | p90: **{summary['agent_b']['elapsed_p90_sec']}s**

## 3. Cross Market
- Brief pairs OK: **{cm_brief_ok}/{n}**
- Success rate: **{summary['cross_market']['success_rate_pct']}%**

## 4. Crypto Beta
- Reports OK: **{beta_report_ok}/{n}**
- Success rate: **{summary['crypto_beta']['success_rate_pct']}%**

## 5. Signals
- Mean: **{summary['signals']['mean']}** | Median: **{summary['signals']['median']}**
- Max: **{summary['signals']['max']}** | Min: **{summary['signals']['min']}**

## 6. Closed
- Start: {closed_start} → End: {closed_end} (**Δ{closed_end - closed_start}**)

## 7. Postmortems
- Start: {postmortems_start} → End: {postmortems_end} (**Δ{postmortems_end - postmortems_start}**)

## 8. Errors
- Total: **{total_errors}**
- touched_trading_paths: **{all_touched or '[]'}**

## Final Checkpoint

| Question | Answer |
|----------|--------|
| Paper Loop stable? | {'Yes' if summary['checkpoint']['paper_loop_stable'] else 'No'} |
| Agent B fixed? | {'Yes' if summary['checkpoint']['agent_b_fixed'] else 'No'} |
| Cross Market stable? | {'Yes' if summary['checkpoint']['cross_market_stable'] else 'No'} |
| Crypto Beta stable? | {'Yes' if summary['checkpoint']['crypto_beta_stable'] else 'No'} |
| Postmortems ≥ 25? | {'Yes' if summary['checkpoint']['postmortems_target_met'] else 'No'} ({postmortems_end}) |
| Stable Observation Phase? | **{status}** |
"""
    OUT_MD.write_text(md, encoding="utf-8")
    print(json.dumps({k: v for k, v in summary.items() if k != "cycles"}, indent=2, ensure_ascii=False))
    print(f"\nReport: {OUT_MD}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
