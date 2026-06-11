#!/bin/sh
# Cross Market Research Brief — independent research cron (NOT trading).
# Usage: cross_market_brief_cron.sh [us-cn|cn-us|all]

set -eu

ROOT="/Users/libo/.hermes/polymarket_arbitrage"
BRIEF_TYPE="${1:-all}"
LOG_DIR="/Users/libo/shared_intelligence/research/cross_market_v0/logs"
TODAY="$(date '+%Y%m%d')"
LOG_FILE="$LOG_DIR/brief_cron_${TODAY}.log"

mkdir -p "$LOG_DIR"
cd "$ROOT"

export PYTHONUNBUFFERED=1
export PATH="/usr/bin:/bin:/usr/sbin:/sbin:$PATH"
export PYTHONPATH="$ROOT${PYTHONPATH:+:$PYTHONPATH}"
# Research-only: do NOT set EXECUTOR_DRY_RUN or touch orchestrator
unset EXECUTOR_DRY_RUN PA_SHADOW_DB 2>/dev/null || true
# 与 paper loop 并行时由调用方设置 CROSS_MARKET_PARALLEL_PAPER=1
export CROSS_MARKET_PARALLEL_PAPER="${CROSS_MARKET_PARALLEL_PAPER:-0}"

{
  echo "============================================================"
  echo "[cross_market_brief] start $(date '+%Y-%m-%d %H:%M:%S') type=$BRIEF_TYPE"
  echo "[cross_market_brief] RESEARCH ONLY — no trading scheduler"
  python3 research/cross_market/brief_cron.py "$BRIEF_TYPE"
  code=$?
  echo "[cross_market_brief] exit=$code $(date '+%Y-%m-%d %H:%M:%S')"
  exit "$code"
} >> "$LOG_FILE" 2>&1
