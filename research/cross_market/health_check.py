#!/usr/bin/env python3
"""Health check for Cross Market Research Brief cron (research-only)."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from research.cross_market.paths import (
    BRIEF_INDEX_FILE,
    BRIEF_STATUS_FILE,
    CRON_LOG_DIR,
    PM_ROOT,
    REPORTS_ARCHIVE_DIR,
    REPORTS_DIR,
    RESEARCH_ROOT,
    TRADING_GUARD_PATHS,
)
from research.cross_market.brief_cron import _data_freshness


def run_health_check(max_stale_hours: int = 36) -> dict:
    issues: list[str] = []
    checks: dict = {"healthy": True, "issues": issues, "checked_at": datetime.now().isoformat()}

    # 1. last run time
    status: dict = {}
    if BRIEF_STATUS_FILE.exists():
        status = json.loads(BRIEF_STATUS_FILE.read_text(encoding="utf-8"))
    checks["last_run_at"] = status.get("last_run_at")
    for key in ("us-cn", "cn-us"):
        sub = status.get(key, {})
        checks[f"{key}_last_success"] = sub.get("success")
        checks[f"{key}_last_completed"] = sub.get("completed_at")
        if not sub.get("success"):
            issues.append(f"{key}: last run not successful")
        elif sub.get("completed_at"):
            try:
                completed = datetime.fromisoformat(sub["completed_at"])
                if datetime.now() - completed > timedelta(hours=max_stale_hours):
                    issues.append(f"{key}: stale (>{max_stale_hours}h)")
            except ValueError:
                pass

    # 2. latest report paths
    latest = {
        "us-cn": REPORTS_DIR / "us_close_cn_open_latest.md",
        "cn-us": REPORTS_DIR / "cn_close_us_open_latest.md",
    }
    checks["latest_paths"] = {}
    for k, p in latest.items():
        checks["latest_paths"][k] = str(p)
        if not p.exists():
            issues.append(f"latest missing: {p}")

    # 3. archive writable
    try:
        REPORTS_ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
        probe = REPORTS_ARCHIVE_DIR / ".health_probe"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        checks["archive_writable"] = True
        checks["archive_count"] = len(list(REPORTS_ARCHIVE_DIR.glob("*.md")))
    except Exception as exc:
        checks["archive_writable"] = False
        issues.append(f"archive not writable: {exc}")

    # 4. data freshness
    checks["data_freshness"] = _data_freshness()
    for label, info in checks["data_freshness"].items():
        if not info.get("exists"):
            issues.append(f"data missing: {label}")

    # 5. trading DB / signals not touched by brief
    for key in ("us-cn", "cn-us"):
        sub = status.get(key, {})
        touched = sub.get("touched_trading_paths") or []
        if touched:
            issues.append(f"{key} touched trading paths: {touched}")
    checks["trading_guard_paths"] = [str(p) for p in TRADING_GUARD_PATHS]

    # 6. no trading module in brief logs
    checks["cron_log_dir"] = str(CRON_LOG_DIR)
    forbidden = ("orchestrator.run_once", "signal_executor", "approved_signals", "EXECUTOR_DRY_RUN=0")
    if CRON_LOG_DIR.exists():
        for log in CRON_LOG_DIR.glob("brief_*.log"):
            text = log.read_text(encoding="utf-8", errors="replace")
            for token in forbidden:
                if token in text:
                    issues.append(f"log {log.name} contains forbidden token: {token}")

    # index
    checks["index_exists"] = BRIEF_INDEX_FILE.exists()
    if BRIEF_INDEX_FILE.exists():
        checks["index"] = json.loads(BRIEF_INDEX_FILE.read_text(encoding="utf-8"))

    checks["research_root"] = str(RESEARCH_ROOT)
    checks["pm_root_readonly"] = str(PM_ROOT)
    checks["healthy"] = len(issues) == 0
    checks["issues"] = issues
    return checks


def main():
    parser = argparse.ArgumentParser(description="Cross Market Brief health check")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--max-stale-hours", type=int, default=36)
    args = parser.parse_args()
    result = run_health_check(args.max_stale_hours)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"healthy: {result['healthy']}")
        print(f"last_run: {result.get('last_run_at')}")
        for issue in result.get("issues", []):
            print(f"  ISSUE: {issue}")
    sys.exit(0 if result["healthy"] else 1)


if __name__ == "__main__":
    main()
