#!/usr/bin/env python3
"""CLI: Phase 3d observation backfill (funding + PM crypto tape + DXY template)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from runtime.observation_continuity import run_phase3e  # noqa: E402


def main() -> int:
    rep = run_phase3e(base_dir=ROOT)
    print(f"Funding total: {rep['funding'].get('total_rows')} appended={rep['funding'].get('appended_rows')}")
    print(f"PM crypto total: {rep['pm_crypto_tape'].get('total_rows')} appended={rep['pm_crypto_tape'].get('appended_rows')}")
    print(f"DXY status: {rep['dxy'].get('status')}")
    for k, v in rep.get("continuity_reports", {}).items():
        print(f"Report {k}: {v}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
