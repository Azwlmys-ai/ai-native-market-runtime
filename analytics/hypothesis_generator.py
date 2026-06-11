#!/usr/bin/env python3
"""
Step 6: Observation → Hypothesis (Historical Replay).

Rule: grouped replay sample >= 10 → auto-generate Hypothesis (Pending Validation).

Output:
  - shared_intelligence/learning/hypotheses.json
  - shared_intelligence/hypotheses/HYP_*.md

Usage:
    PYTHONPATH=. python3 analytics/hypothesis_generator.py
"""

from __future__ import annotations

import argparse
import json
import statistics
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from analytics.replay_common import (
    confidence_from_sample,
    is_significant,
    load_jsonl,
    market_bucket,
)
from research.history_paths import HYPOTHESES_JSON, HYPOTHESES_ROOT, REPLAY_DATASET

HYPOTHESIS_MIN = 10


def _baseline_1d(rows: list[dict], asset: str) -> float:
    vals = [float(r[f"{asset}_1D"]) for r in rows if r.get(f"{asset}_1D") is not None]
    return statistics.mean(vals) if vals else 0.0


def generate_hypotheses(rows: list[dict]) -> list[dict]:
    groups: dict[tuple, list[float]] = defaultdict(list)
    for row in rows:
        theme = row.get("theme")
        if not theme:
            continue
        for asset in ("QQQ", "SOXL", "SOXS", "TQQQ", "BTC", "ETH"):
            key = f"{asset}_1D"
            if row.get(key) is not None:
                groups[(theme, asset)].append(float(row[key]))

    baselines = {a: _baseline_1d(rows, a) for a in ("QQQ", "SOXL", "SOXS", "TQQQ", "BTC", "ETH")}
    hyps: list[dict] = []
    seq = 1

    for (theme, asset), vals in sorted(groups.items(), key=lambda x: -len(x[1])):
        n = len(vals)
        if n < HYPOTHESIS_MIN:
            continue
        mean = statistics.mean(vals)
        std = statistics.pstdev(vals) if n > 1 else 0.0
        baseline = baselines.get(asset, 0.0)
        direction = "weaker" if mean < baseline else "stronger"
        hid = f"HYP_{seq:03d}"
        seq += 1
        hyps.append({
            "id": hid,
            "theme": theme,
            "asset": asset,
            "market": market_bucket(asset),
            "statement": (
                f"{theme} Theme → {asset} average 1D return {direction} than baseline "
                f"({mean:+.2f}% vs {baseline:+.2f}%)"
            ),
            "sample_size": n,
            "avg_return_1d": round(mean, 4),
            "baseline_return_1d": round(baseline, 4),
            "std_return_1d": round(std, 4),
            "confidence": confidence_from_sample(n, std, mean),
            "status": "Pending Validation",
            "significant_vs_baseline": is_significant(mean, std, n, baseline, min_n=HYPOTHESIS_MIN),
        })
    return hyps


def _write_markdown(hyp: dict, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{hyp['id']}.md"
    path.write_text("\n".join([
        f"# {hyp['id']}",
        "",
        f"**Status:** {hyp['status']}",
        f"**Theme:** {hyp['theme']}",
        f"**Asset:** {hyp['asset']} ({hyp['market']})",
        "",
        "## Hypothesis",
        "",
        hyp["statement"],
        "",
        "## Evidence (Historical Replay)",
        "",
        f"- Sample: {hyp['sample_size']}",
        f"- Avg 1D return: {hyp['avg_return_1d']:+.2f}%",
        f"- Baseline 1D: {hyp['baseline_return_1d']:+.2f}%",
        f"- Confidence: {hyp['confidence']}",
        f"- Significant vs baseline: {hyp['significant_vs_baseline']}",
        "",
        "> Learning-only. Not promoted to trading.",
        "",
    ]) + "\n", encoding="utf-8")
    return path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--in", dest="inp", type=Path, default=REPLAY_DATASET)
    parser.add_argument("--out", type=Path, default=HYPOTHESES_JSON)
    args = parser.parse_args()

    rows = load_jsonl(args.inp)
    hyps = generate_hypotheses(rows)
    payload = {
        "schema_version": "1.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "min_sample": HYPOTHESIS_MIN,
        "hypotheses": hyps,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    for hyp in hyps:
        _write_markdown(hyp, HYPOTHESES_ROOT)

    print(f"Wrote {len(hyps)} hypotheses → {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
