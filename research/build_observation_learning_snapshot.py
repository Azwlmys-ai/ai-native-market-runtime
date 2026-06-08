#!/usr/bin/env python3
"""CLI: Phase 3 observation learning snapshot (read-only)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from runtime.observation_learning import compute  # noqa: E402


def main() -> int:
    snap = compute(base_dir=ROOT, date_suffix="20260607")
    paths = snap.get("output_paths", {})
    print(f"Wrote {paths.get('json')}")
    print(f"Wrote {paths.get('markdown')}")
    print(f"stable_correlations={len(snap.get('stable_correlations', []))}")
    print(f"insufficient_samples={len(snap.get('insufficient_samples', []))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
