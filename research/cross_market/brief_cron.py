#!/usr/bin/env python3
"""Independent Research Cron — Cross Market Research Brief only."""

from __future__ import annotations

import argparse
import json
import os
import sys
import traceback
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from research.cross_market.paths import (
    BRIEF_STATUS_FILE,
    CHINA_DIR,
    CRON_LOG_DIR,
    FLOWS_DIR,
    PM_ROOT,
    RESEARCH_ROOT,
    TRADING_GUARD_PATHS,
)
from research.cross_market.reports import write_brief


def _guard_mtimes() -> dict[str, float]:
    out = {}
    for p in TRADING_GUARD_PATHS:
        if p.exists():
            out[str(p)] = p.stat().st_mtime
    return out


def _data_freshness() -> dict:
    checks = {}
    for label, path in [
        ("china_000001", CHINA_DIR / "000001.json"),
        ("northbound", FLOWS_DIR / "northbound.json"),
    ]:
        if not path.exists():
            checks[label] = {"exists": False}
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        checks[label] = {
            "exists": True,
            "updated_at": data.get("updated_at"),
            "end": data.get("end"),
            "rows": len(data.get("bars") or []),
        }
    return checks


def run_brief(brief_type: str) -> dict:
    """Generate one research brief; never touch trading layer."""
    started = datetime.now().isoformat()
    log_path = CRON_LOG_DIR / f"brief_{brief_type}_{datetime.now().strftime('%Y%m%d')}.log"
    CRON_LOG_DIR.mkdir(parents=True, exist_ok=True)
    RESEARCH_ROOT.mkdir(parents=True, exist_ok=True)

    guard_before = _guard_mtimes()
    status: dict = {
        "brief_type": brief_type,
        "started_at": started,
        "success": False,
        "research_only": True,
        "touched_trading_paths": [],
        "written_paths": [],
        "pm_root": str(PM_ROOT),
    }

    try:
        result = write_brief(brief_type)
        status["written_paths"] = [result["archive"], result["latest"]]
        status["archive_path"] = result["archive"]
        status["latest_path"] = result["latest"]
        status["success"] = True
        status["completed_at"] = datetime.now().isoformat()
        status["data_freshness"] = _data_freshness()

        guard_after = _guard_mtimes()
        touched = []
        for k, t0 in guard_before.items():
            t1 = guard_after.get(k)
            if t1 is not None and t1 != t0:
                touched.append(k)
        status["touched_trading_paths"] = touched
        # 与 paper loop 并行时 orchestrator 会更新 status/lock，非 brief 写入
        parallel_paper = os.environ.get("CROSS_MARKET_PARALLEL_PAPER") == "1"
        if parallel_paper:
            external = {str(PM_ROOT / "data" / "orchestrator_status.json"), str(PM_ROOT / "orchestrator.lock")}
            touched = [p for p in touched if p not in external]
            status["parallel_paper_mode"] = True
        if touched:
            status["success"] = False
            status["error"] = "TRADING_PATH_MODIFIED"
            raise RuntimeError(f"Trading path modified: {touched}")

        # merge into status file (per-brief keys)
        all_status: dict = {}
        if BRIEF_STATUS_FILE.exists():
            try:
                all_status = json.loads(BRIEF_STATUS_FILE.read_text(encoding="utf-8"))
            except Exception:
                pass
        all_status[brief_type] = status
        all_status["last_run_at"] = status["completed_at"]
        BRIEF_STATUS_FILE.write_text(json.dumps(all_status, ensure_ascii=False, indent=2), encoding="utf-8")

        line = f"[{status['completed_at']}] OK {brief_type} archive={result['archive']}\n"
        with log_path.open("a", encoding="utf-8") as f:
            f.write(line)
        print(line.strip())
        return status

    except Exception as exc:
        status["completed_at"] = datetime.now().isoformat()
        status["error"] = str(exc)
        status["traceback"] = traceback.format_exc()
        all_status: dict = {}
        if BRIEF_STATUS_FILE.exists():
            try:
                all_status = json.loads(BRIEF_STATUS_FILE.read_text(encoding="utf-8"))
            except Exception:
                pass
        all_status[brief_type] = status
        BRIEF_STATUS_FILE.write_text(json.dumps(all_status, ensure_ascii=False, indent=2), encoding="utf-8")
        with log_path.open("a", encoding="utf-8") as f:
            f.write(f"[{status['completed_at']}] FAIL {brief_type}: {exc}\n")
        raise


def main():
    parser = argparse.ArgumentParser(description="Cross Market Research Brief Cron")
    parser.add_argument("brief", choices=["us-cn", "cn-us", "all"], help="which brief to generate")
    args = parser.parse_args()
    if args.brief == "all":
        run_brief("us-cn")
        run_brief("cn-us")
    else:
        run_brief(args.brief)


if __name__ == "__main__":
    main()
