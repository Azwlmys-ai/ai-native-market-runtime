#!/usr/bin/env python3
"""Collect per-cycle stats for final 24-cycle validation (read-only)."""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DATA = REPO / "data"
SHARED = Path("/Users/libo/shared_intelligence")
CM_STATUS = SHARED / "research" / "cross_market_v0" / "brief_cron_status.json"
BETA_DIR = SHARED / "research" / "crypto_ecosystem_v0" / "beta_attribution"
OUT = DATA / "final_validation_cycles.jsonl"


def _read_json(path: Path) -> dict | list | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _count_jsonl(path: Path) -> int:
    if not path.exists():
        return 0
    return sum(1 for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip())


def _closed_count() -> int:
    pp = _read_json(DATA / "paper_portfolio.json")
    if isinstance(pp, list):
        return sum(1 for p in pp if p.get("closed_at"))
    return 0


def _parse_log_signals(log_path: Path, cycle_n: int) -> int | None:
    if not log_path.exists():
        return None
    text = log_path.read_text(errors="replace")
    blocks = re.split(r"parallel cycle \d+/", text)
    if len(blocks) <= cycle_n:
        return None
    block = blocks[cycle_n]
    m = re.search(r"汇总 (\d+) 个新信号", block)
    return int(m.group(1)) if m else None


def collect(
    cycle: int,
    started_at: str,
    completed_at: str,
    duration_sec: float,
    paper_exit: int,
    cm_exit: int,
    beta_exit: int,
    log_file: Path,
) -> dict:
    orch_status = _read_json(DATA / "orchestrator_status.json") or {}
    review = _read_json(DATA / "review_results.json") or {}
    exec_res = _read_json(DATA / "execution_results.json") or {}
    race_runs = (_read_json(DATA / "agent_b_race_stats.json") or {}).get("runs", [])
    runtime_runs = (_read_json(DATA / "agent_b_runtime_stats.json") or {}).get("runs", [])

    cycle_id = orch_status.get("cycle_id") or review.get("generated_cycle_id", "")
    race = race_runs[-1] if race_runs else {}
    runtime = runtime_runs[-1] if runtime_runs else {}

    cm = _read_json(CM_STATUS) or {}
    us_cn = cm.get("us-cn") or cm.get("us_cn") or {}
    cn_us = cm.get("cn-us") or cm.get("cn_us") or {}
    touched = list(us_cn.get("touched_trading_paths") or []) + list(
        cn_us.get("touched_trading_paths") or []
    )
    touched = [t for t in touched if t]

    beta_files = {
        "beta_report": BETA_DIR / "beta_attribution_report.md",
        "mstr_report": BETA_DIR / "mstr_special.md",
        "coin_report": BETA_DIR / "coin_special.md",
        "cp00048_report": BETA_DIR / "cp00048_special.md",
    }
    beta_mtime = {k: p.stat().st_mtime if p.exists() else None for k, p in beta_files.items()}

    opened = sum(
        1
        for r in (exec_res.get("results") or [])
        if r.get("status") in ("success", "dry_run", "simulated", "opened")
    )
    errors = []
    if paper_exit != 0:
        errors.append(f"paper_exit={paper_exit}")
    if cm_exit != 0:
        errors.append(f"cross_market_exit={cm_exit}")
    if beta_exit != 0:
        errors.append(f"crypto_beta_exit={beta_exit}")
    if orch_status.get("state") not in (None, "completed", "running"):
        errors.append(f"orchestrator_state={orch_status.get('state')}")

    return {
        "cycle": cycle,
        "cycle_id": cycle_id,
        "started_at": started_at,
        "completed_at": completed_at,
        "duration_sec": round(duration_sec, 1),
        "exit_code": 0 if paper_exit == 0 and cm_exit == 0 and beta_exit == 0 else 1,
        "paper_exit": paper_exit,
        "cross_market_exit": cm_exit,
        "crypto_beta_exit": beta_exit,
        "paper": {
            "signals": _parse_log_signals(log_file, cycle) or review.get("total"),
            "approved": review.get("approved"),
            "rejected": review.get("rejected"),
            "opened": opened,
            "closed": _closed_count(),
            "postmortems": _count_jsonl(DATA / "postmortems.jsonl"),
            "errors": errors,
            "orchestrator_state": orch_status.get("state"),
        },
        "agent_b": {
            "elapsed_sec": race.get("elapsed_sec") or runtime.get("duration_sec"),
            "winner": race.get("winner"),
            "grok_started": race.get("grok_started"),
            "deepseek_started": race.get("deepseek_started"),
            "hedge_triggered": race.get("hedge_triggered"),
            "timeout": race.get("timeout") or runtime.get("status") == "timeout",
            "signals_generated": race.get("signals_generated"),
        },
        "cross_market": {
            "us_cn_brief_generated": bool(us_cn.get("success")),
            "cn_us_brief_generated": bool(cn_us.get("success")),
            "archive_written": bool(us_cn.get("archive_path") or cn_us.get("archive_path")),
            "health_status": "ok" if us_cn.get("success") and cn_us.get("success") else "degraded",
            "touched_trading_paths": touched,
        },
        "crypto_beta": {
            "beta_report_generated": beta_mtime["beta_report"] is not None,
            "mstr_report_generated": beta_mtime["mstr_report"] is not None,
            "coin_report_generated": beta_mtime["coin_report"] is not None,
            "cp00048_report_generated": beta_mtime["cp00048_report"] is not None,
            "exit_code": beta_exit,
        },
        "isolation": {
            "touched_trading_paths": touched,
        },
    }


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--cycle", type=int, required=True)
    p.add_argument("--started-at", required=True)
    p.add_argument("--completed-at", required=True)
    p.add_argument("--duration-sec", type=float, required=True)
    p.add_argument("--paper-exit", type=int, default=0)
    p.add_argument("--cm-exit", type=int, default=0)
    p.add_argument("--beta-exit", type=int, default=0)
    p.add_argument("--log-file", required=True)
    args = p.parse_args()

    entry = collect(
        cycle=args.cycle,
        started_at=args.started_at,
        completed_at=datetime.now().isoformat() if not args.completed_at else args.completed_at,
        duration_sec=args.duration_sec,
        paper_exit=args.paper_exit,
        cm_exit=args.cm_exit,
        beta_exit=args.beta_exit,
        log_file=Path(args.log_file),
    )
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    print(json.dumps(entry, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
