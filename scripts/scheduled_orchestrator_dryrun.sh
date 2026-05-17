#!/bin/sh
# Scheduled safety heartbeat for the Polymarket orchestrator.
# Runs one full cycle in EXECUTOR_DRY_RUN mode. It must not place real orders.

set -eu

ROOT="/Users/libo/.hermes/polymarket_arbitrage"
VENV="$ROOT/venv"
LOG_DIR="$ROOT/logs"
TODAY="$(date '+%Y%m%d')"
LOG_FILE="$LOG_DIR/scheduled_orchestrator_dryrun_${TODAY}.log"

mkdir -p "$LOG_DIR"
cd "$ROOT"

export PA_BASE_DIR="$ROOT"
export EXECUTOR_DRY_RUN=1
export PYTHONUNBUFFERED=1
export PATH="$VENV/bin:/usr/bin:/bin:/usr/sbin:/sbin:$PATH"
export PYTHONPATH="$ROOT${PYTHONPATH:+:$PYTHONPATH}"

{
  echo "============================================================"
  echo "[scheduled_dryrun] start $(date '+%Y-%m-%d %H:%M:%S')"
  echo "[scheduled_dryrun] root=$ROOT"
  echo "[scheduled_dryrun] python=$(command -v python3)"
  python3 main.py --mode once
  code=$?
  echo "[scheduled_dryrun] exit=$code $(date '+%Y-%m-%d %H:%M:%S')"
  exit "$code"
} >> "$LOG_FILE" 2>&1
