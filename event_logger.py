"""
Append-only runtime event logger for the Polymarket Arbitrage system.
 
Writes JSONL records to data/events/runtime_events.jsonl.
All writes are crash-safe (atomic append) and failures never propagate.
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

from _paths import get_base_dir


def get_events_file() -> Path:
    base = get_base_dir()
    events_dir = base / "data" / "events"
    events_dir.mkdir(parents=True, exist_ok=True)
    return events_dir / "runtime_events.jsonl"


def write_event(
    *,
    cycle_id: str,
    type: str,
    agent: str,
    payload: dict | None = None,
    trace_id: str | None = None,
    ts: str | None = None,
) -> None:
    """Atomically append a single JSON-line event to the runtime log.

    Failures are logged to stderr but *never* raised — the orchestrator
    must not crash because of event-log I/O.
    """
    if ts is None:
        ts = datetime.now(timezone.utc).isoformat()
    if trace_id is None:
        trace_id = f"{cycle_id}::{agent}::{uuid.uuid4().hex[:8]}"

    record = {
        "ts": ts,
        "cycle_id": cycle_id,
        "type": type,
        "agent": agent,
        "trace_id": trace_id,
        "payload": payload or {},
    }

    events_file = get_events_file()
    line = json.dumps(record, ensure_ascii=False) + "\n"

    try:
        with open(events_file, "a") as f:
            f.write(line)
            f.flush()
            os.fsync(f.fileno())
    except Exception as exc:
        print(f"[event_logger] write failure (non-fatal): {exc}", flush=True)