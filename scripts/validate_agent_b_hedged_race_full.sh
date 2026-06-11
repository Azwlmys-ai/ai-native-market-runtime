#!/usr/bin/env bash
# 12-cycle hedged race validation; on pass → 24-cycle parallel (paper + cross market + crypto beta)
set -uo pipefail
cd "$(dirname "$0")/.." || exit 1
REPO="$(pwd)"
PY="$REPO/venv/bin/python"

export EXECUTOR_DRY_RUN=1
export PA_SHADOW_DB=1
export PA_COINT_SIGNALS=1
export PA_ENFORCE_LEARNING="${PA_ENFORCE_LEARNING:-1}"

CYCLES_12="${PA_LOOP_CYCLES:-12}"
INTERVAL="${PA_LOOP_INTERVAL:-300}"

echo "[hedged_race_full] phase1: $CYCLES_12 cycles"
bash "$REPO/scripts/validate_agent_b_hedged_race.sh"

SUMMARY="$REPO/data/agent_b_validation_summary.json"
if [ ! -f "$SUMMARY" ]; then
    echo "[hedged_race_full] missing summary — abort phase2"
    exit 1
fi

PASSED=$("$PY" -c "import json; print(json.load(open('$SUMMARY')).get('validation_passed', False))")
if [ "$PASSED" != "True" ]; then
    echo "[hedged_race_full] phase1 did not pass criteria — skip 24-cycle parallel"
    exit 0
fi

echo "[hedged_race_full] phase1 PASSED — starting 24-cycle parallel validation"
MARKER="$REPO/data/agent_b_validation_marker.json"
echo "{\"validation_start\":\"$(date -Iseconds)\",\"cycles\":24,\"mode\":\"hedged_race_parallel\"}" > "$MARKER"

PA_LOOP_CYCLES=24 PA_LOOP_INTERVAL="$INTERVAL" bash "$REPO/scripts/parallel_paper_cross_market_24.sh"

# Crypto beta reports (research-only)
if [ -x "$PY" ] && [ -f "$REPO/research/crypto_ecosystem/run_beta_audit.py" ]; then
    echo "[hedged_race_full] crypto beta audit"
    "$PY" "$REPO/research/crypto_ecosystem/run_beta_audit.py" >> "$REPO/logs/agent_b_hedged_race_validation_$(date '+%Y%m%d').log" 2>&1 || true
fi

"$PY" "$REPO/scripts/summarize_agent_b_validation.py" --mode hedged_race_parallel
