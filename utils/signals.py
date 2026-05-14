"""Helpers for signal JSON handoffs."""

from datetime import datetime


def ensure_signal_timestamps(signals, generated_at=None):
    """Return signal copies with generated_at/timestamp populated.

    This keeps strategy payloads unchanged while making freshness checks depend
    on per-signal metadata instead of the signals.json file mtime.
    """
    if generated_at is None:
        generated_at = datetime.now().isoformat()

    stamped = []
    for signal in signals:
        item = dict(signal)
        signal_time = item.get("generated_at") or item.get("timestamp") or generated_at
        item["generated_at"] = signal_time
        item.setdefault("timestamp", signal_time)
        stamped.append(item)

    return stamped
