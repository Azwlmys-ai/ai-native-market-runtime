#!/usr/bin/env python3
"""CLI: Phase 3c observation gap audits → research/*_gap_*.md"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from runtime.observation_gaps import build_gap_reports  # noqa: E402


def main() -> int:
    rep = build_gap_reports(base_dir=ROOT, date_suffix="20260607")
    for k, v in rep["output_paths"].items():
        print(f"Wrote {v}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
