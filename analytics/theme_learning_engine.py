#!/usr/bin/env python3
"""
Step 4: Learn Theme → Market Reaction patterns.

Output: shared_intelligence/learning/theme_patterns.json

Usage:
    PYTHONPATH=. python3 analytics/theme_learning_engine.py
"""

from __future__ import annotations

import argparse
import json
import statistics
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from analytics.replay_common import (
    MARKET_SYMBOLS,
    confidence_from_sample,
    load_jsonl,
    market_bucket,
)
from research.history_paths import LEARNING_ROOT, REPLAY_DATASET, THEME_PATTERNS


def _collect_returns(rows: list[dict], theme: str, asset: str, horizon: int) -> list[float]:
    key = f"{asset}_{horizon}D"
    out = []
    for row in rows:
        if row.get("theme") != theme:
            continue
        val = row.get(key)
        if val is not None:
            out.append(float(val))
    return out


def learn_patterns(rows: list[dict]) -> dict:
    patterns = []
    themes = sorted({r.get("theme") for r in rows if r.get("theme")})

    for theme in themes:
        for asset in MARKET_SYMBOLS:
            for horizon in (1, 3, 5, 10):
                vals = _collect_returns(rows, theme, asset, horizon)
                if len(vals) < 3:
                    continue
                mean = statistics.mean(vals)
                std = statistics.pstdev(vals) if len(vals) > 1 else 0.0
                patterns.append({
                    "theme": theme,
                    "asset": asset,
                    "market": market_bucket(asset),
                    "horizon_days": horizon,
                    "sample_size": len(vals),
                    f"avg_return_{horizon}d": round(mean, 4),
                    "std_return": round(std, 4),
                    "confidence": confidence_from_sample(len(vals), std, mean),
                })

    patterns.sort(key=lambda p: (-p["sample_size"], -abs(p.get("avg_return_3d", p.get("avg_return_1d", 0)))))
    return {
        "schema_version": "1.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "n_events": len(rows),
        "patterns": patterns,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--in", dest="inp", type=Path, default=REPLAY_DATASET)
    parser.add_argument("--out", type=Path, default=THEME_PATTERNS)
    args = parser.parse_args()

    rows = load_jsonl(args.inp)
    report = learn_patterns(rows)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote {len(report['patterns'])} theme patterns → {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
