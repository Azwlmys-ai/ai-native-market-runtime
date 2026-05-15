#!/usr/bin/env python3
"""Write one reviewable paper signal for dry-run pipeline validation only."""

import json
import os
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from _paths import get_base_dir
from utils.signals import ensure_signal_timestamps


def main():
    if os.environ.get("EXECUTOR_DRY_RUN", "").lower() not in ("1", "true", "yes"):
        raise SystemExit("Refusing to write paper signal unless EXECUTOR_DRY_RUN=1")

    base_dir = get_base_dir()
    data_dir = base_dir / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    signal = {
        "market_id": "paper-smoke-nhl-no",
        "market_name": "Will the Anaheim Ducks win the NHL Stanley Cup?",
        "market": "Will the Anaheim Ducks win the NHL Stanley Cup?",
        "direction": "NO",
        "price": 0.9,
        "position_size": 0.01,
        "expected_value": 0.12,
        "confidence": 75,
        "market_type": "NHL Stanley Cup",
        "data_sources": ["NHL.com standings", "ESPN power rankings"],
        "logic_chain": [
            "Paper-only dry-run smoke signal",
            "Weak long-shot NHL champion market at extreme NO price",
            "Small 1% paper position used to exercise Agent M and executor plumbing",
        ],
        "source": "paper_smoke",
        "paper": True,
        "synthetic": True,
    }
    stamped = ensure_signal_timestamps([signal], generated_at=datetime.now().isoformat())
    output_file = data_dir / "signals.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(stamped, f, indent=2, ensure_ascii=False)
    print(f"Wrote {len(stamped)} paper signal to {output_file}")


if __name__ == "__main__":
    main()
