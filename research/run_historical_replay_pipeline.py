#!/usr/bin/env python3
"""
Run full Phase 3 Historical Replay Learning pipeline (learning-only).

Steps:
  1–2 build_history_datasets
  3   historical_replay_joiner
  4   theme_learning_engine
  5   cross_market_theme_report
  6   hypothesis_generator
  7   insight_promoter
  8   learning_dashboard

Usage:
    PYTHONPATH=. python3 research/run_historical_replay_pipeline.py
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_VENV_PY = _ROOT / "venv" / "bin" / "python"


def _python() -> str:
    """Prefer project venv (certifi for macOS SSL)."""
    return str(_VENV_PY) if _VENV_PY.exists() else sys.executable


def _run(script: str, *extra: str) -> None:
    import os

    cmd = [_python(), str(_ROOT / script), *extra]
    print(f"\n>>> {' '.join(cmd)}")
    env = os.environ.copy()
    env["PYTHONPATH"] = str(_ROOT)
    subprocess.run(cmd, cwd=str(_ROOT), check=True, env=env)


def main() -> int:
    import os
    os.environ["PYTHONPATH"] = str(_ROOT)

    _run("research/build_history_datasets.py")
    _run("analytics/historical_replay_joiner.py")
    _run("analytics/theme_learning_engine.py")
    _run("analytics/cross_market_theme_report.py")
    _run("analytics/hypothesis_generator.py")
    _run("analytics/insight_promoter.py")
    _run("analytics/learning_dashboard.py")
    print("\n✅ Historical Replay Learning pipeline complete.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
