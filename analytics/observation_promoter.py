#!/usr/bin/env python3
"""
Observation → Hypothesis → Insight promotion (read-only governance).

Does NOT modify trading systems. Writes markdown/json artifacts only.

Usage:
    PYTHONPATH=. python3 analytics/observation_promoter.py
"""

from __future__ import annotations

import argparse
import json
import math
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from analytics.metrics import expectancy, win_rate

_SHARED = Path("/Users/libo/shared_intelligence")
_DEFAULT_IN = _SHARED / "trades" / "event_attributed_trades.jsonl"
_OBS_DIR = _SHARED / "observations"
_HYP_DIR = _SHARED / "hypotheses"
_INS_DIR = _SHARED / "insights"

HYPOTHESIS_MIN = 10
INSIGHT_MIN = 30
INSIGHT_MIN_WIN_RATE_DELTA = 0.05  # descriptive threshold only


def _load_jsonl(path: Path) -> list[dict]:
    rows: list[dict] = []
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def _group_key(row: dict) -> str:
    themes = "+".join(row.get("themes") or ["UNTHEMED"])
    events = "+".join(row.get("events") or ["NO_EVENT"])
    return f"{themes}|{events}|{row.get('symbol')}"


def _significance_hint(n: int, wr: float, baseline_wr: float) -> bool:
    """Lightweight gate: n>=30 and |wr-baseline|>=5pp (not a formal test)."""
    return n >= INSIGHT_MIN and abs(wr - baseline_wr) >= INSIGHT_MIN_WIN_RATE_DELTA


def promote(rows: list[dict], generated_at: datetime) -> tuple[list[Path], list[Path]]:
    _HYP_DIR.mkdir(parents=True, exist_ok=True)
    _INS_DIR.mkdir(parents=True, exist_ok=True)

    groups: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        if row.get("event_count", 0) < 1:
            continue
        groups[_group_key(row)].append(row)

    baseline_wr = win_rate(rows) if rows else 0.0
    hyp_paths: list[Path] = []
    ins_paths: list[Path] = []

    for key, trades in sorted(groups.items(), key=lambda x: -len(x[1])):
        n = len(trades)
        if n < HYPOTHESIS_MIN:
            continue
        wr = win_rate(trades)
        exp = expectancy(trades)
        stamp = generated_at.strftime("%Y%m%d")
        safe = key.replace("|", "_").replace("+", "_")[:80]

        if n >= HYPOTHESIS_MIN:
            hyp_path = _HYP_DIR / f"HYP_{stamp}_{safe}.md"
            hyp_path.write_text("\n".join([
                f"# Hypothesis: {key}",
                "",
                f"**Status:** Candidate",
                f"**Generated:** {generated_at.isoformat()}",
                f"**Sample:** {n}",
                "",
                f"- Win rate: {wr:.2%} (baseline {baseline_wr:.2%})",
                f"- Expectancy: {exp:+.6f}%",
                "",
                "## Rule",
                "Hypothesis requires validation before Insight promotion.",
                "",
            ]), encoding="utf-8")
            hyp_paths.append(hyp_path)

        if _significance_hint(n, wr, baseline_wr):
            ins_path = _INS_DIR / f"INS_{stamp}_{safe}.json"
            payload = {
                "key": key,
                "status": "insight_candidate",
                "generated_at": generated_at.isoformat(),
                "sample_size": n,
                "win_rate": round(wr, 4),
                "baseline_win_rate": round(baseline_wr, 4),
                "expectancy": round(exp, 6),
                "note": "Not production-ready — human review required",
            }
            ins_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
            ins_paths.append(ins_path)

    return hyp_paths, ins_paths


def main() -> int:
    p = argparse.ArgumentParser(description="Promote observations to hypotheses/insights")
    p.add_argument("--in", dest="in_path", type=Path, default=_DEFAULT_IN)
    args = p.parse_args()

    if not args.in_path.exists():
        print(f"ERROR: missing {args.in_path}")
        return 1

    rows = _load_jsonl(args.in_path)
    hyp, ins = promote(rows, datetime.now(timezone.utc))
    print(f"Hypotheses: {len(hyp)} → {_HYP_DIR}")
    print(f"Insight candidates: {len(ins)} → {_INS_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
