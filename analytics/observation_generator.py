#!/usr/bin/env python3
"""
Auto-generate observation notes (Unverified) from event-attributed trades.

Output: shared_intelligence/observations/OBS_YYYY_MM_DD_NNN.md

Observation ≠ Knowledge. No production promotion.

Usage:
    PYTHONPATH=. python3 analytics/observation_generator.py
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

_SHARED = Path("/Users/libo/shared_intelligence")
_DEFAULT_IN = _SHARED / "trades" / "event_attributed_trades.jsonl"
_DEFAULT_OBS_DIR = _SHARED / "observations"

# Thresholds for auto-observation (descriptive only)
_NOTABLE_PNL_PCT = 0.01


def _load_jsonl(path: Path) -> list[dict]:
    rows: list[dict] = []
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def _next_obs_id(obs_dir: Path, day: str) -> str:
    """day = YYYY_MM_DD"""
    prefix = f"OBS_{day}_"
    existing = list(obs_dir.glob(f"{prefix}*.md"))
    seq = len(existing) + 1
    return f"{prefix}{seq:03d}"


def _candidate_rows(rows: list[dict]) -> list[dict]:
    """Multi-event first; then single-event moves above noise threshold."""
    multi: list[dict] = []
    single: list[dict] = []
    for row in rows:
        n_ev = row.get("event_count") or 0
        if n_ev < 1:
            continue
        pnl = float(row.get("pnl_pct") or 0)
        if n_ev >= 2:
            multi.append(row)
        elif abs(pnl) >= _NOTABLE_PNL_PCT:
            single.append(row)
    combined = multi + single
    return sorted(combined, key=lambda r: (-(r.get("event_count") or 0), float(r.get("pnl_pct") or 0)))


def _render_obs(obs_id: str, row: dict, generated_at: datetime) -> str:
    events = row.get("events") or []
    pnl = float(row.get("pnl_pct") or 0)
    impact_dir = "loss" if pnl < 0 else "gain"
    return "\n".join([
        f"# {obs_id}",
        "",
        f"**Status:** Unverified",
        f"**Generated:** {generated_at.isoformat()}",
        "",
        "## Observation",
        "",
        " + ".join(events),
        "",
        "## Trade",
        "",
        f"- Source: `{row.get('source')}`",
        f"- Symbol: `{row.get('symbol')}`",
        f"- Strategy: `{row.get('strategy')}`",
        f"- Entry: {row.get('entry_time')}",
        f"- Exit: {row.get('exit_time')}",
        f"- PnL: **{pnl:+.4f}%**",
        "",
        "## Impact",
        "",
        f"{row.get('symbol')} {impact_dir} {pnl:+.4f}% during event window",
        "",
        "## Sample Size",
        "",
        str(len(events)),
        "",
        "## Rule",
        "",
        "Observation ≠ Knowledge. Do not wire into agents, executors, or risk.",
        "",
    ])


def generate_observations(
    rows: list[dict],
    obs_dir: Path,
    generated_at: datetime,
    *,
    max_files: int = 20,
) -> list[Path]:
    obs_dir.mkdir(parents=True, exist_ok=True)
    day = generated_at.strftime("%Y_%m_%d")
    written: list[Path] = []

    for row in _candidate_rows(rows)[:max_files]:
        obs_id = _next_obs_id(obs_dir, day)
        path = obs_dir / f"{obs_id}.md"
        path.write_text(_render_obs(obs_id, row, generated_at), encoding="utf-8")
        written.append(path)
    return written


def main() -> int:
    p = argparse.ArgumentParser(description="Generate observation markdown files")
    p.add_argument("--in", dest="in_path", type=Path, default=_DEFAULT_IN)
    p.add_argument("--obs-dir", type=Path, default=_DEFAULT_OBS_DIR)
    p.add_argument("--max", type=int, default=20)
    args = p.parse_args()

    if not args.in_path.exists():
        print(f"ERROR: run event_joiner.py first — missing {args.in_path}")
        return 1

    rows = _load_jsonl(args.in_path)
    paths = generate_observations(rows, args.obs_dir, datetime.now(timezone.utc), max_files=args.max)
    print(f"Wrote {len(paths)} observations → {args.obs_dir}")
    for path in paths[:5]:
        print(f"  {path.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
