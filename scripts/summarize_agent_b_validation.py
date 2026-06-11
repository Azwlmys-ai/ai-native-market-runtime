#!/usr/bin/env python3
"""Summarize Agent B validation run from logs + runtime/race stats."""

from __future__ import annotations

import argparse
import json
import re
import statistics
from collections import Counter
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
LOGS = REPO / "logs"
DATA = REPO / "data"


def _parse_orchestrator_agent_b(log_path: Path) -> list[dict]:
    lines = log_path.read_text(errors="replace").splitlines() if log_path.exists() else []
    events = []
    start = None
    for line in lines:
        if "步骤 5/16: 情报研究 (Agent B)" in line:
            m = re.match(r"\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\]", line)
            start = m.group(1) if m else None
        elif start and ("agent_b 执行成功" in line or "agent_b 执行超时" in line):
            m = re.match(r"\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\]", line)
            if m:
                s = datetime.strptime(start, "%Y-%m-%d %H:%M:%S")
                e = datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S")
                events.append({
                    "start": start,
                    "duration_sec": (e - s).total_seconds(),
                    "status": "timeout" if "超时" in line else "success",
                })
                start = None
    return events


def _pct(xs: list[float], p: float) -> float:
    s = sorted(xs)
    return s[min(int(len(s) * p / 100), len(s) - 1)] if s else 0.0


def _load_race_runs(validation_start: str | None) -> list[dict]:
    path = DATA / "agent_b_race_stats.json"
    if not path.exists():
        return []
    runs = json.loads(path.read_text(encoding="utf-8")).get("runs", [])
    if validation_start:
        cutoff = validation_start[:19]
        runs = [r for r in runs if r.get("timestamp", "") >= cutoff]
    return runs


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", default="timeout_fix", choices=["timeout_fix", "hedged_race"])
    args = parser.parse_args()

    marker = DATA / "agent_b_validation_marker.json"
    validation_start = None
    mode = args.mode
    if marker.exists():
        marker_data = json.loads(marker.read_text())
        validation_start = marker_data.get("validation_start")
        mode = marker_data.get("mode", mode)

    stats_path = DATA / "agent_b_runtime_stats.json"
    stats_runs = []
    if stats_path.exists():
        stats_runs = json.loads(stats_path.read_text()).get("runs", [])

    if validation_start:
        stats_runs = [r for r in stats_runs if r.get("started_at", "") >= validation_start[:19]]

    today = datetime.now().strftime("%Y%m%d")
    orch_log = LOGS / f"orchestrator_{today}.log"
    orch_events = _parse_orchestrator_agent_b(orch_log)

    log_glob = (
        "agent_b_hedged_race_validation_*.log"
        if mode == "hedged_race"
        else "agent_b_timeout_fix_validation_*.log"
    )
    val_logs = sorted(LOGS.glob(log_glob))
    val_log = val_logs[-1] if val_logs else None
    signal_totals = []
    if val_log and val_log.exists():
        for line in val_log.read_text().splitlines():
            m = re.search(r"汇总 (\d+) 个新信号", line)
            if m:
                signal_totals.append(int(m.group(1)))

    runs = stats_runs if stats_runs else orch_events[-12:]
    n = len(runs)
    timeouts = sum(1 for r in runs if r.get("status") == "timeout" or r.get("timed_out"))
    durs = [r.get("duration_sec") for r in runs if r.get("duration_sec") is not None]
    if not durs and orch_events:
        durs = [e["duration_sec"] for e in orch_events[-12:]]

    race_runs = _load_race_runs(validation_start)
    race_elapsed = [r["elapsed_sec"] for r in race_runs if r.get("elapsed_sec")]
    hedge_triggered = sum(1 for r in race_runs if r.get("hedge_triggered"))
    winner_dist = dict(Counter(r.get("winner") for r in race_runs if r.get("winner")))
    race_signals = [r.get("signals_generated", 0) for r in race_runs]
    b_nonzero = sum(1 for s in race_signals if s > 0)
    race_timeouts = sum(1 for r in race_runs if r.get("timeout"))

    pp = json.loads((DATA / "paper_portfolio.json").read_text())
    closed = sum(1 for p in pp if p.get("closed_at"))

    postmortems = 0
    for pm_path in (DATA / "postmortems.json", DATA / "model_effectiveness.json"):
        if pm_path.exists():
            pm = json.loads(pm_path.read_text())
            if isinstance(pm, list):
                postmortems = max(postmortems, len(pm))
            elif isinstance(pm, dict):
                postmortems = max(
                    postmortems,
                    len(pm.get("entries", [])),
                    pm.get("total_postmortems", 0) or 0,
                    len(pm.get("postmortems", [])),
                )

    timeout_rate = round(timeouts / n * 100, 1) if n else None
    signals_mean = round(statistics.mean(signal_totals), 1) if signal_totals else None
    if signals_mean is None and race_signals:
        signals_mean = round(statistics.mean(race_signals), 1)
    b_nonzero_rate = round(b_nonzero / len(race_runs) * 100, 1) if race_runs else None

    passed = False
    pass_reasons = []
    if timeout_rate is not None and timeout_rate < 15:
        passed = True
        pass_reasons.append("timeout_rate<15%")
    if signals_mean is not None and signals_mean > 11:
        passed = True
        pass_reasons.append("signals_per_cycle>11")
    if b_nonzero_rate is not None and b_nonzero_rate > 85:
        passed = True
        pass_reasons.append("b_nonzero_rate>85%")

    summary = {
        "mode": mode,
        "validation_start": validation_start,
        "cycles": n,
        "race_cycles": len(race_runs),
        "timeout_count": timeouts,
        "timeout_rate_pct": timeout_rate,
        "race_timeout_count": race_timeouts,
        "duration_mean_sec": round(statistics.mean(durs), 1) if durs else None,
        "duration_p50_sec": round(_pct(durs, 50), 1) if durs else None,
        "duration_p90_sec": round(_pct(durs, 90), 1) if durs else None,
        "race_elapsed_p50_sec": round(_pct(race_elapsed, 50), 1) if race_elapsed else None,
        "race_elapsed_p90_sec": round(_pct(race_elapsed, 90), 1) if race_elapsed else None,
        "signals_per_cycle_mean": signals_mean,
        "signals_per_cycle_samples": signal_totals or race_signals,
        "hedge_triggered_count": hedge_triggered,
        "winner_distribution": winner_dist,
        "b_nonzero_output_rate_pct": b_nonzero_rate,
        "validation_passed": passed,
        "pass_reasons": pass_reasons,
        "closed_end": closed,
        "postmortems_count": postmortems,
        "timeout_limit_sec": stats_runs[-1].get("timeout_limit_sec", 180) if stats_runs else 180,
        "errors_in_validation_log": 0,
        "baseline_comparison": {
            "pre_fix_timeout_rate_pct": 83.0,
            "pre_fix_signals_per_cycle": 8.1,
            "note": "parallel 24-cycle pre-fix baseline from RCA audit",
        },
    }

    if val_log and val_log.exists():
        text = val_log.read_text()
        summary["errors_in_validation_log"] = text.count("执行失败") + text.count("fatal")

    out = DATA / "agent_b_validation_summary.json"
    out.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
