#!/bin/sh
# Health check for Cross Market Research Brief cron.

set -eu

ROOT="/Users/libo/.hermes/polymarket_arbitrage"
cd "$ROOT"
export PYTHONPATH="$ROOT${PYTHONPATH:+:$PYTHONPATH}"
python3 research/cross_market/health_check.py --json
