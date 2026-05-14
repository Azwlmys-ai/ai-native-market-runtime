#!/usr/bin/env python3
"""
Dump pm-trader history only after validating the CLI output as JSON.

This script is the safe replacement for shell redirects such as:
pm-trader history --format json > data/historical_trades_100.json
"""

import argparse
import json
import subprocess
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
from _paths import get_pm_trader, get_pm_trader_env

DEFAULT_OUTPUT = PROJECT_ROOT / "data" / "historical_trades_100.json"


def fetch_history(pm_trader, limit, timeout=30):
    result = subprocess.run(
        [pm_trader, "history", "--limit", str(limit)],
        capture_output=True,
        text=True,
        timeout=timeout,
        env=get_pm_trader_env(),
    )

    if result.returncode != 0:
        raise RuntimeError(f"pm-trader history failed: {result.stderr.strip()}")

    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        preview = result.stdout[:300].replace("\n", "\\n")
        raise ValueError(f"pm-trader history returned non-JSON output: {preview}") from exc


def write_validated_history(data, output_path):
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")


def main():
    parser = argparse.ArgumentParser(description="Safely dump pm-trader history JSON")
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument(
        "--pm-trader",
        default=get_pm_trader(),
        help="Path to pm-trader; can also be set with PM_TRADER_PATH",
    )
    args = parser.parse_args()

    data = fetch_history(args.pm_trader, args.limit)
    write_validated_history(data, Path(args.output))
    print(f"Wrote validated pm-trader history to {args.output}")


if __name__ == "__main__":
    main()
