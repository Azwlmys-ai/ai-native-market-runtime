#!/usr/bin/env python3
"""
Step 7: Hypothesis → Insight promotion (Historical Replay).

Rule: sample >= 30 AND statistically significant → Insight.

Output:
  - shared_intelligence/learning/insights.json
  - shared_intelligence/insights/INSIGHT_*.md

Usage:
    PYTHONPATH=. python3 analytics/insight_promoter.py
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from analytics.replay_common import load_json
from research.history_paths import HYPOTHESES_JSON, INSIGHTS_JSON, INSIGHTS_ROOT

INSIGHT_MIN = 30


def promote(hypotheses: list[dict]) -> list[dict]:
    insights = []
    seq = 1
    for hyp in hypotheses:
        n = hyp.get("sample_size", 0)
        if n < INSIGHT_MIN:
            continue
        if not hyp.get("significant_vs_baseline"):
            continue
        iid = f"INSIGHT_{seq:03d}"
        seq += 1
        insights.append({
            "id": iid,
            "hypothesis_id": hyp.get("id"),
            "theme": hyp.get("theme"),
            "asset": hyp.get("asset"),
            "market": hyp.get("market"),
            "sample_size": n,
            "avg_return_1d": hyp.get("avg_return_1d"),
            "baseline_return_1d": hyp.get("baseline_return_1d"),
            "confidence": hyp.get("confidence"),
            "status": "Insight",
            "summary": hyp.get("statement"),
        })
    return insights


def _write_markdown(ins: dict, patterns_path: Path) -> Path:
    INSIGHTS_ROOT.mkdir(parents=True, exist_ok=True)
    path = INSIGHTS_ROOT / f"{ins['id']}.md"

    # Pull 3D pattern if available for richer insight card
    extra_lines = []
    if patterns_path.exists():
        pats = json.loads(patterns_path.read_text()).get("patterns", [])
        for p in pats:
            if p.get("theme") == ins["theme"] and p.get("asset") == ins["asset"] and p.get("horizon_days") == 3:
                extra_lines.append(f"- Avg 3D return: {p.get('avg_return_3d'):+.2f}%")
                break

    path.write_text("\n".join([
        f"# {ins['id']}",
        "",
        f"**Status:** Insight (promoted from {ins.get('hypothesis_id')})",
        f"**Theme:** {ins['theme']}",
        f"**Asset:** {ins['asset']} ({ins['market']})",
        "",
        "## Insight",
        "",
        ins["summary"],
        "",
        "## Historical Sample",
        "",
        f"- Sample size: {ins['sample_size']}",
        f"- Avg 1D: {ins['avg_return_1d']:+.2f}%",
        f"- Baseline 1D: {ins['baseline_return_1d']:+.2f}%",
        f"- Confidence: {ins['confidence']}",
        *extra_lines,
        "",
        "> Knowledge artifact — not a trading instruction.",
        "",
    ]) + "\n", encoding="utf-8")
    return path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--hypotheses", type=Path, default=HYPOTHESES_JSON)
    parser.add_argument("--out", type=Path, default=INSIGHTS_JSON)
    args = parser.parse_args()

    payload = load_json(args.hypotheses)
    hyps = payload.get("hypotheses", [])
    insights = promote(hyps)

    from research.history_paths import THEME_PATTERNS

    out_payload = {
        "schema_version": "1.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "min_sample": INSIGHT_MIN,
        "insights": insights,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(out_payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    for ins in insights:
        _write_markdown(ins, THEME_PATTERNS)

    print(f"Promoted {len(insights)} insights → {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
