#!/usr/bin/env python3
"""CLI: Phase 3b model research sandbox (read-only, research outputs only)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from runtime.model_sandbox import compute  # noqa: E402


def main() -> int:
    result = compute(base_dir=ROOT)
    summary = result["summary"]
    models = summary["models"]
    print(f"Wrote {result['output_paths']['garch_json']}")
    print(f"Wrote {result['output_paths']['regime_json']}")
    print(f"Wrote {result['output_paths']['coint_json']}")
    print(f"garch_sufficient={models['garch']['n_sufficient']}")
    print(f"regime_sufficient={models['hmm_regime']['n_sufficient']}")
    print(f"coint_sufficient={models['cointegration']['data_sufficient']}")
    print(f"pca={models['pca']['status']} ({models['pca']['reason']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
