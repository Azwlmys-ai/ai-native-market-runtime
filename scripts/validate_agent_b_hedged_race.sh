#!/usr/bin/env bash
# 12-cycle validation for Agent B hedged race (dry-run only)
set -uo pipefail
cd "$(dirname "$0")/.." || exit 1
REPO="$(pwd)"
PY="$REPO/venv/bin/python"
LOG="$REPO/logs/agent_b_hedged_race_validation_$(date '+%Y%m%d').log"

export EXECUTOR_DRY_RUN=1
export PA_SHADOW_DB=1
export PA_COINT_SIGNALS=1
export PA_ENFORCE_LEARNING="${PA_ENFORCE_LEARNING:-1}"

CYCLES="${PA_LOOP_CYCLES:-12}"
INTERVAL="${PA_LOOP_INTERVAL:-300}"

echo "[validate] Agent B hedged race — $CYCLES cycles, interval=${INTERVAL}s" | tee -a "$LOG"
echo "[validate] closed_start=$("$PY" -c "
import json; from pathlib import Path
pp=json.loads(Path('data/paper_portfolio.json').read_text())
print(sum(1 for p in pp if p.get('closed_at')))
")" | tee -a "$LOG"

MARKER="$REPO/data/agent_b_validation_marker.json"
echo "{\"validation_start\":\"$(date -Iseconds)\",\"cycles\":$CYCLES,\"mode\":\"hedged_race\"}" > "$MARKER"

# reset race stats window marker (append-only file; filter by validation_start in summarize)
RACE_MARKER="$REPO/data/agent_b_race_validation_marker.json"
echo "{\"validation_start\":\"$(date -Iseconds)\"}" > "$RACE_MARKER"

i=0
while [ "$i" -lt "$CYCLES" ]; do
    i=$((i + 1))
    echo "================ hedged race cycle $i/$CYCLES $(date '+%F %T') ================" | tee -a "$LOG"
    "$PY" "$REPO/orchestrator.py" 2>&1 | tee -a "$LOG" || echo "[warn] cycle $i exit=$?" | tee -a "$LOG"
    if [ "$i" -lt "$CYCLES" ]; then
        sleep "$INTERVAL"
    fi
done

echo "[validate] done $(date '+%F %T')" | tee -a "$LOG"
"$PY" "$REPO/scripts/summarize_agent_b_validation.py" --mode hedged_race 2>&1 | tee -a "$LOG"
