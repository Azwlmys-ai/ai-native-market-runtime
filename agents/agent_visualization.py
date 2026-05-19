#!/usr/bin/env python3
"""Minimal read-only Visualization Agent for dashboard state snapshots.

Allowed reads:
- data/signals.json
- data/review_results.json
- data/execution_results.json
- logs/*.log

Allowed write:
- data/visualization_state.json
"""

from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
LOGS_DIR = ROOT / "logs"

SIGNALS_PATH = DATA_DIR / "signals.json"
REVIEW_PATH = DATA_DIR / "review_results.json"
EXECUTION_PATH = DATA_DIR / "execution_results.json"
OUTPUT_PATH = DATA_DIR / "visualization_state.json"
ALLOWED_READS = {SIGNALS_PATH.resolve(), REVIEW_PATH.resolve(), EXECUTION_PATH.resolve()}
ALLOWED_WRITE = OUTPUT_PATH.resolve()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def ensure_allowed_read(path: Path) -> None:
    resolved = path.resolve()
    is_allowed_log = (
        resolved.parent == LOGS_DIR.resolve()
        and resolved.suffix == ".log"
        and resolved.is_file()
    )
    if resolved not in ALLOWED_READS and not is_allowed_log:
        raise PermissionError(f"Visualization agent read denied: {resolved}")


def ensure_allowed_write(path: Path) -> None:
    resolved = path.resolve()
    if resolved != ALLOWED_WRITE:
        raise PermissionError(f"Visualization agent write denied: {resolved}")


def read_json(path: Path, default: Any) -> Any:
    ensure_allowed_read(path)
    if not path.exists():
        return default
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except json.JSONDecodeError as exc:
        return {"error": f"invalid_json: {exc}", "path": str(path.relative_to(ROOT))}


def read_recent_lines(path: Path, limit: int = 40) -> list[str]:
    ensure_allowed_read(path)
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError as exc:
        return [f"read_error: {exc}"]
    return lines[-limit:]


def as_list(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    return []


def summarize_signals(raw: Any) -> dict[str, Any]:
    signals = as_list(raw)
    source_counts = Counter(str(item.get("source", "unknown")) for item in signals)
    direction_counts = Counter(str(item.get("direction", "unknown")) for item in signals)
    confidences = [float(item["confidence"]) for item in signals if isinstance(item.get("confidence"), (int, float))]
    expected_values = [
        float(item["expected_value"])
        for item in signals
        if isinstance(item.get("expected_value"), (int, float))
    ]
    timestamps = [
        str(item.get("timestamp") or item.get("generated_at"))
        for item in signals
        if item.get("timestamp") or item.get("generated_at")
    ]
    top_signals = sorted(
        signals,
        key=lambda item: float(item.get("expected_value") or 0),
        reverse=True,
    )[:5]

    return {
        "total": len(signals),
        "by_source": dict(source_counts),
        "by_direction": dict(direction_counts),
        "average_confidence": round(sum(confidences) / len(confidences), 2) if confidences else None,
        "average_expected_value": round(sum(expected_values) / len(expected_values), 2) if expected_values else None,
        "latest_signal_timestamp": max(timestamps) if timestamps else None,
        "top_markets": [
            {
                "market_id": item.get("market_id"),
                "market_name": item.get("market_name") or item.get("market"),
                "direction": item.get("direction"),
                "expected_value": item.get("expected_value"),
                "confidence": item.get("confidence"),
            }
            for item in top_signals
        ],
    }


def detail_signals(raw: Any) -> list[dict[str, Any]]:
    signals = as_list(raw)
    return [
        {
            "market_id": item.get("market_id"),
            "market_name": item.get("market_name") or item.get("market"),
            "market_slug": item.get("market_slug"),
            "direction": item.get("direction"),
            "price": item.get("price"),
            "position_size": item.get("position_size"),
            "expected_value": item.get("expected_value"),
            "confidence": item.get("confidence"),
            "source": item.get("source"),
            "generated_at": item.get("generated_at") or item.get("timestamp"),
            "reason": item.get("reason"),
            "risk_notes": item.get("risk_notes"),
        }
        for item in signals
    ]


def summarize_review(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        return {"total": 0, "approved": 0, "rejected": 0}

    return {
        "timestamp": raw.get("timestamp"),
        "total": raw.get("total", 0),
        "real_signals": raw.get("real_signals", 0),
        "paper_signals": raw.get("paper_signals", 0),
        "approved": raw.get("approved", 0),
        "rejected": raw.get("rejected", 0),
        "approved_real": raw.get("approved_real", 0),
        "approved_paper": raw.get("approved_paper", 0),
        "rejected_real": raw.get("rejected_real", 0),
        "rejected_paper": raw.get("rejected_paper", 0),
    }


def detail_review(raw: Any) -> dict[str, list[dict[str, Any]]]:
    if not isinstance(raw, dict):
        return {"approved_signals": [], "rejected_signals": []}

    def normalize(items: Any) -> list[dict[str, Any]]:
        rows = []
        for item in as_list(items):
            signal = item.get("signal") if isinstance(item.get("signal"), dict) else {}
            rows.append(
                {
                    "market_id": item.get("market_id") or signal.get("market_id"),
                    "market_name": item.get("market_name") or signal.get("market_name") or signal.get("market"),
                    "direction": signal.get("direction"),
                    "expected_value": signal.get("expected_value"),
                    "confidence": signal.get("confidence"),
                    "decision": item.get("decision"),
                    "review": item.get("review"),
                    "reason": item.get("reason"),
                    "source": signal.get("source"),
                }
            )
        return rows

    return {
        "approved_signals": normalize(raw.get("approved_signals")),
        "rejected_signals": normalize(raw.get("rejected_signals")),
    }


def summarize_execution(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        return {"total": 0, "status_counts": {}}

    results = as_list(raw.get("results"))
    status_counts = Counter(str(item.get("status", "unknown")) for item in results)
    timestamps = [str(item.get("timestamp")) for item in results if item.get("timestamp")]

    return {
        "timestamp": raw.get("timestamp"),
        "total": raw.get("total", len(results)),
        "success": raw.get("success", status_counts.get("success", 0)),
        "dry_run": raw.get("dry_run", status_counts.get("dry_run", 0)),
        "simulated": raw.get("simulated", status_counts.get("simulated", 0)),
        "failed": raw.get("failed", status_counts.get("failed", 0)),
        "status_counts": dict(status_counts),
        "latest_execution_timestamp": max(timestamps) if timestamps else raw.get("timestamp"),
    }


def detail_execution(raw: Any) -> list[dict[str, Any]]:
    if not isinstance(raw, dict):
        return []

    rows = []
    for item in as_list(raw.get("results")):
        signal = item.get("signal") if isinstance(item.get("signal"), dict) else {}
        rows.append(
            {
                "status": item.get("status"),
                "timestamp": item.get("timestamp"),
                "market_id": signal.get("market_id"),
                "market_name": signal.get("market_name") or signal.get("market"),
                "direction": signal.get("direction"),
                "expected_value": signal.get("expected_value"),
                "confidence": signal.get("confidence"),
                "source": signal.get("source"),
            }
        )
    return rows


def summarize_logs() -> tuple[dict[str, Any], list[dict[str, Any]]]:
    log_files = sorted(LOGS_DIR.glob("*.log"), key=lambda item: item.stat().st_mtime, reverse=True)
    summaries: list[dict[str, Any]] = []
    events: list[dict[str, Any]] = []

    for path in log_files[:8]:
        lines = read_recent_lines(path)
        level_counts = Counter()
        for line in lines:
            upper = line.upper()
            if "ERROR" in upper or "FAIL" in upper or "ABORT" in upper:
                level_counts["error"] += 1
            elif "WARN" in upper:
                level_counts["warning"] += 1
            elif "SUCCESS" in upper or "COMPLETE" in upper or "OK" in upper:
                level_counts["success"] += 1
            else:
                level_counts["info"] += 1

        stat = path.stat()
        recent_lines = [line.strip()[:300] for line in lines[-8:] if line.strip()]
        summaries.append(
            {
                "file": str(path.relative_to(ROOT)),
                "size_bytes": stat.st_size,
                "modified_at": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(),
                "recent_line_count": len(lines),
                "level_counts": dict(level_counts),
                "recent_lines": recent_lines,
            }
        )
        for line in lines[-5:]:
            if line.strip():
                events.append({"file": str(path.relative_to(ROOT)), "message": line.strip()[:300]})

    return {"files": summaries, "files_scanned": len(summaries)}, events[-20:]


def build_state() -> dict[str, Any]:
    signals = read_json(SIGNALS_PATH, [])
    review = read_json(REVIEW_PATH, {})
    execution = read_json(EXECUTION_PATH, {})
    log_summary, recent_events = summarize_logs()

    return {
        "timestamp": utc_now(),
        "signals_summary": summarize_signals(signals),
        "signal_details": detail_signals(signals),
        "review_summary": summarize_review(review),
        "review_details": detail_review(review),
        "execution_summary": summarize_execution(execution),
        "execution_details": detail_execution(execution),
        "agent_log_summary": log_summary,
        "recent_runtime_events": recent_events,
    }


def main() -> int:
    state = build_state()
    ensure_allowed_write(OUTPUT_PATH)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with OUTPUT_PATH.open("w", encoding="utf-8") as handle:
        json.dump(state, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    print(json.dumps(state, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
