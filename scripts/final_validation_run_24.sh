#!/usr/bin/env bash
# Final 24-cycle validation: Paper Loop + Cross Market + Crypto Beta (no code changes)
set -uo pipefail
cd "$(dirname "$0")/.." || exit 1
REPO="$(pwd)"
PY="$REPO/venv/bin/python"
CYCLES="${PA_LOOP_CYCLES:-24}"
INTERVAL="${PA_LOOP_INTERVAL:-300}"
LOG="$REPO/logs/final_validation_24_$(date '+%Y%m%d').log"
MARKER="$REPO/data/final_validation_marker.json"
CYCLES_FILE="$REPO/data/final_validation_cycles.jsonl"

export EXECUTOR_DRY_RUN=1
export PA_SHADOW_DB=1
export PA_COINT_SIGNALS=1
export PA_COINT_EXPLORE="${PA_COINT_EXPLORE:-1}"
export PA_ENFORCE_LEARNING="${PA_ENFORCE_LEARNING:-1}"
export CROSS_MARKET_PARALLEL_PAPER=1

# clear stale orchestrator lock
if [ -f "$REPO/data/orchestrator.lock" ]; then
    LOCK_PID="$(grep '^pid=' "$REPO/data/orchestrator.lock" 2>/dev/null | cut -d= -f2)"
    if [ -n "$LOCK_PID" ] && ! kill -0 "$LOCK_PID" 2>/dev/null; then
        rm -f "$REPO/data/orchestrator.lock"
        echo "[final] removed stale lock pid=$LOCK_PID" | tee -a "$LOG"
    fi
fi

POSTMORTEMS_START=$("$PY" -c "print(sum(1 for l in open('$REPO/data/postmortems.jsonl') if l.strip()) if __import__('pathlib').Path('$REPO/data/postmortems.jsonl').exists() else 0)")
CLOSED_START=$("$PY" -c "
import json; from pathlib import Path
p=Path('$REPO/data/paper_portfolio.json')
pp=json.loads(p.read_text()) if p.exists() else []
print(sum(1 for x in pp if x.get('closed_at')))
")

echo "{\"validation_start\":\"$(date -Iseconds)\",\"cycles\":$CYCLES,\"postmortems_start\":$POSTMORTEMS_START,\"closed_start\":$CLOSED_START}" > "$MARKER"
: > "$CYCLES_FILE"

echo "[final] start $CYCLES cycles interval=${INTERVAL}s postmortems=$POSTMORTEMS_START closed=$CLOSED_START" | tee -a "$LOG"

i=0
while [ "$i" -lt "$CYCLES" ]; do
    i=$((i + 1))
    STARTED_AT="$(date -Iseconds)"
    T0=$(date +%s)
    echo "================ final cycle $i/$CYCLES $STARTED_AT ================" | tee -a "$LOG"

    (
        "$PY" "$REPO/orchestrator.py" >> "$LOG" 2>&1
        echo $? > "/tmp/final_paper_exit_$$"
    ) &
    PID_PAPER=$!

    (
        /bin/sh "$REPO/scripts/cross_market_brief_cron.sh" all >> "$LOG" 2>&1
        echo $? > "/tmp/final_cm_exit_$$"
    ) &
    PID_CM=$!

    (
        "$PY" "$REPO/research/crypto_ecosystem/run_beta_audit.py" >> "$LOG" 2>&1
        echo $? > "/tmp/final_beta_exit_$$"
    ) &
    PID_BETA=$!

    wait "$PID_PAPER" || true
    wait "$PID_CM" || true
    wait "$PID_BETA" || true

    PAPER_EXIT=$(cat "/tmp/final_paper_exit_$$" 2>/dev/null || echo 1)
    CM_EXIT=$(cat "/tmp/final_cm_exit_$$" 2>/dev/null || echo 1)
    BETA_EXIT=$(cat "/tmp/final_beta_exit_$$" 2>/dev/null || echo 1)
    rm -f "/tmp/final_paper_exit_$$" "/tmp/final_cm_exit_$$" "/tmp/final_beta_exit_$$"

    T1=$(date +%s)
    DURATION=$((T1 - T0))
    COMPLETED_AT="$(date -Iseconds)"

    "$PY" "$REPO/scripts/collect_final_validation_cycle.py" \
        --cycle "$i" \
        --started-at "$STARTED_AT" \
        --completed-at "$COMPLETED_AT" \
        --duration-sec "$DURATION" \
        --paper-exit "$PAPER_EXIT" \
        --cm-exit "$CM_EXIT" \
        --beta-exit "$BETA_EXIT" \
        --log-file "$LOG" >> "$LOG" 2>&1 || true

    echo "[final] cycle $i done duration=${DURATION}s paper=$PAPER_EXIT cm=$CM_EXIT beta=$BETA_EXIT" | tee -a "$LOG"

    if [ "$i" -lt "$CYCLES" ]; then
        sleep "$INTERVAL"
    fi
done

echo "[final] done $(date '+%F %T')" | tee -a "$LOG"
"$PY" "$REPO/scripts/summarize_final_validation.py" | tee -a "$LOG"
