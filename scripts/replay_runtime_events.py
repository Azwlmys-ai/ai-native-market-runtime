#!/usr/bin/env python3
"""
Replay / statistics over the append-only runtime event log.

Reads data/events/runtime_events.jsonl and prints aggregate counts.
"""

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from event_logger import get_events_file  # noqa: E402


def load_events() -> list[dict]:
    events_file = get_events_file()
    if not events_file.exists():
        print(f"[replay] events file not found: {events_file}")
        return []

    events = []
    with open(events_file, "r") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return events


def compute_stats(events: list[dict]) -> dict:
    cycles: set[str] = set()
    signals: list[dict] = []
    approved = 0
    rejected = 0
    dry_run = 0
    skipped = 0
    agent_counts: Counter[str] = Counter()
    type_counts: Counter[str] = Counter()

    for ev in events:
        ev_type = ev.get("type", "")
        agent = ev.get("agent", "")
        cycle_id = ev.get("cycle_id", "")
        payload = ev.get("payload", {})

        if cycle_id:
            cycles.add(cycle_id)
        if agent:
            agent_counts[agent] += 1
        if ev_type:
            type_counts[ev_type] += 1

        if ev_type == "signal.generated":
            signals.append(payload)
        elif ev_type == "signal.reviewed":
            decision = str(payload.get("decision", "")).upper()
            if decision == "APPROVE":
                approved += 1
            else:
                rejected += 1
        elif ev_type == "execution.dry_run":
            dry_run += 1
        elif ev_type == "execution.skipped":
            skipped += 1

    return {
        "cycles": len(cycles),
        "signals_generated": len(signals),
        "approved": approved,
        "rejected": rejected,
        "dry_run_count": dry_run,
        "execution_skipped": skipped,
        "agent_activity": dict(agent_counts.most_common()),
        "event_type_counts": dict(type_counts.most_common()),
        "total_events": len(events),
    }


def main():
    events = load_events()
    if not events:
        print("No events to replay.")
        return

    stats = compute_stats(events)

    print("=" * 50)
    print("Runtime Event Replay Statistics")
    print("=" * 50)
    print(f"Total events:       {stats['total_events']}")
    print(f"Unique cycles:      {stats['cycles']}")
    print(f"Signals generated:  {stats['signals_generated']}")
    print(f"Approved:           {stats['approved']}")
    print(f"Rejected:           {stats['rejected']}")
    print(f"Dry-run executions: {stats['dry_run_count']}")
    print(f"Execution skipped:  {stats['execution_skipped']}")
    print()
    print("Agent activity counts:")
    for agent, count in sorted(stats["agent_activity"].items()):
        print(f"  {agent}: {count}")
    print()
    print("Event type counts:")
    for ev_type, count in sorted(stats["event_type_counts"].items()):
        print(f"  {ev_type}: {count}")
    print("=" * 50)


if __name__ == "__main__":
    main()