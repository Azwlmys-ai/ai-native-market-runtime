#!/usr/bin/env python3
"""Run Crypto Ecosystem Beta Attribution audit (one-shot, read-only)."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from research.crypto_ecosystem.beta_attribution import run_beta_attribution


def main() -> int:
    report = run_beta_attribution()
    ans = report.get("answers", {})
    print(f"Beta attribution complete. Strongest amplifier: {ans.get('q1_strongest_amplifier')}")
    print(f"Reports: /Users/libo/shared_intelligence/research/crypto_ecosystem_v0/beta_attribution/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
