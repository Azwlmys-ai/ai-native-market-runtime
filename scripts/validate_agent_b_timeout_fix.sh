#!/usr/bin/env bash
# 12-cycle validation for Agent B 180s timeout fix (dry-run only)
set -uo pipefail
cd "$(dirname "$0")/.." || exit 1
REPO="$(pwd)"
PY="$REPO/venv/bin/python"
LOG="$REPO/logs/agent_b_timeout_fix_validation_$(date '+%Y%m%d').log"

export EXECUTOR_DRY_RUN=1
export PA_SHADOW_DB=1
export PA_COINT_SIGNALS=1
export PA_ENFORCE_LEARNING="${PA_ENFORCE_LEARNING:-1}"

CYCLES="${PA_LOOP_CYCLES:-12}"
INTERVAL="${PA_LOOP_INTERVAL:-300}"

echo "[validate] Agent B timeout fix — $CYCLES cycles, interval=${INTERVAL}s" | tee -a "$LOG"
echo "[validate] closed_start=$("$PY" -c "
import json; from pathlib import Path
pp=json.loads(Path('data/paper_portfolio.json').read_text())
print(sum(1 for p in pp if p.get('closed_at')))
")" | tee -a "$LOG"

# mark validation window in runtime stats
MARKER="$REPO/data/agent_b_validation_marker.json"
echo "{\"validation_start\":\"$(date -Iseconds)\",\"cycles\":$CYCLES}" > "$MARKER"

i=0
while [ "$i" -lt "$CYCLES" ]; do
    i=$((i + 1))
    echo "================ validate cycle $i/$CYCLES $(date '+%F %T') ================" | tee -a "$LOG"
    "$PY" "$REPO/orchestrator.py" 2>&1 | tee -a "$LOG" || echo "[warn] cycle $i exit=$?" | tee -a "$LOG"
    if [ "$i" -lt "$CYCLES" ]; then
        sleep "$INTERVAL"
    fi
done

echo "[validate] done $(date '+%F %T')" | tee -a "$LOG"
"$PY" "$REPO/scripts/summarize_agent_b_validation.py" 2>&1 | tee -a "$LOG"
