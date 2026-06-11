#!/usr/bin/env python3
"""
Step 8: Learning Dashboard aggregator.

Output: shared_intelligence/learning/

Usage:
    PYTHONPATH=. python3 analytics/learning_dashboard.py
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from analytics.replay_common import load_json, load_jsonl
from research.history_paths import (
    DASHBOARD_SUMMARY,
    HISTORY_ROOT,
    HYPOTHESES_JSON,
    INSIGHTS_JSON,
    LEARNING_ROOT,
    OBSERVATIONS_JSON,
    OBSERVATIONS_ROOT,
    REPLAY_DATASET,
    THEME_PATTERNS,
)


def _observation_index() -> list[dict]:
    rows = []
    if not OBSERVATIONS_ROOT.exists():
        return rows
    for p in sorted(OBSERVATIONS_ROOT.glob("OBS_*.md")):
        rows.append({
            "id": p.stem,
            "path": str(p),
            "status": "Unverified",
        })
    return rows


def build_dashboard() -> dict:
    replay_rows = load_jsonl(REPLAY_DATASET)
    theme_patterns = load_json(THEME_PATTERNS)
    hypotheses = load_json(HYPOTHESES_JSON)
    insights = load_json(INSIGHTS_JSON)
    observations = _observation_index()

    return {
        "schema_version": "1.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "counts": {
            "replay_events": len(replay_rows),
            "theme_patterns": len(theme_patterns.get("patterns", [])),
            "hypotheses": len(hypotheses.get("hypotheses", [])),
            "insights": len(insights.get("insights", [])),
            "observations": len(observations),
        },
    }


def build_summary(dashboard: dict) -> str:
    c = dashboard["counts"]
    return "\n".join([
        "# Learning Dashboard Summary",
        "",
        f"**Generated:** {dashboard['generated_at']}",
        "",
        "## Pipeline Status",
        "",
        "| Layer | Count |",
        "|-------|-------|",
        f"| Historical Replay Events | {c['replay_events']} |",
        f"| Theme Patterns | {c['theme_patterns']} |",
        f"| Hypotheses (sample≥10) | {c['hypotheses']} |",
        f"| Insights (sample≥30, significant) | {c['insights']} |",
        f"| Live Observations (markdown) | {c['observations']} |",
        "",
        "## Artifacts",
        "",
        f"- `{REPLAY_DATASET}`",
        f"- `{THEME_PATTERNS}`",
        f"- `{HYPOTHESES_JSON}`",
        f"- `{INSIGHTS_JSON}`",
        f"- `{OBSERVATIONS_JSON}`",
        "",
        "## Success Criteria Check",
        "",
        "System answers **theme-level** questions with sample size + avg returns + confidence,",
        "not single-name event narratives (e.g. AVGO earnings → SOXL).",
        "",
        "> Learning Layer ≠ Trading Layer. No strategy/executor changes in this phase.",
        "",
    ])


def main() -> int:
    parser = argparse.ArgumentParser()
    args = parser.parse_args()

    LEARNING_ROOT.mkdir(parents=True, exist_ok=True)
    dashboard = build_dashboard()

    # Mirror artifacts into learning/ per PRD
    for src, dst_name in (
        (THEME_PATTERNS, "theme_patterns.json"),
        (HYPOTHESES_JSON, "hypotheses.json"),
        (INSIGHTS_JSON, "insights.json"),
    ):
        if src.exists():
            (LEARNING_ROOT / dst_name).write_text(
                src.read_text(encoding="utf-8"), encoding="utf-8",
            )

    obs_payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "observations": _observation_index(),
    }
    (LEARNING_ROOT / "observations.json").write_text(
        json.dumps(obs_payload, indent=2) + "\n", encoding="utf-8",
    )

    summary = build_summary(dashboard)
    DASHBOARD_SUMMARY.write_text(summary + "\n", encoding="utf-8")
    (LEARNING_ROOT / "dashboard_meta.json").write_text(
        json.dumps(dashboard, indent=2) + "\n", encoding="utf-8",
    )

    print(f"Learning dashboard → {LEARNING_ROOT}")
    print(f"Summary → {DASHBOARD_SUMMARY}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
