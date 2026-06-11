#!/usr/bin/env python3
"""Run Crypto Ecosystem data availability audit (one-shot, read-only)."""

from __future__ import annotations

import sys
from pathlib import Path

# allow `python run_audit.py` from repo root or module dir
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from research.crypto_ecosystem.audit import run_full_audit


def main() -> int:
    report = run_full_audit()
    rec = report.get("recommendation", {})
    print(f"Audit complete. Verdict: {rec.get('verdict')} — {rec.get('label')}")
    print(f"Reports: /Users/libo/shared_intelligence/research/crypto_ecosystem_v0/reports/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
