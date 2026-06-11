#!/usr/bin/env bash
# =============================================================================
# parallel_paper_cross_market_24.sh
# Paper loop (dry-run) 与 Cross Market Research Brief 平行跑 N 周期
#
# Paper:    orchestrator.run_once (EXECUTOR_DRY_RUN=1)
# Research: cross_market brief cron (us-cn + cn-us)，不写交易层
#
# 用法:
#   PA_LOOP_CYCLES=24 PA_LOOP_INTERVAL=300 bash scripts/parallel_paper_cross_market_24.sh
#
# 日志:
#   logs/parallel_paper_cross_market_YYYYMMDD.log
#   shared_intelligence/research/cross_market_v0/logs/
# =============================================================================
set -uo pipefail
cd "$(dirname "$0")/.." || exit 1
REPO="$(pwd)"
PY="${REPO}/venv/bin/python"
if [ ! -x "$PY" ]; then
    PY="$(command -v python3)"
fi

export EXECUTOR_DRY_RUN=1
export PA_SHADOW_DB=1
export PA_COINT_SIGNALS=1
export PA_COINT_EXPLORE="${PA_COINT_EXPLORE:-1}"
export PA_ENFORCE_LEARNING="${PA_ENFORCE_LEARNING:-1}"
export CROSS_MARKET_PARALLEL_PAPER=1

INTERVAL="${PA_LOOP_INTERVAL:-300}"
CYCLES="${PA_LOOP_CYCLES:-24}"
LOG_DIR="$REPO/logs"
mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/parallel_paper_cross_market_$(date '+%Y%m%d').log"
STATUS_FILE="/Users/libo/shared_intelligence/research/cross_market_v0/parallel_run_24.json"

echo "[parallel] start cycles=$CYCLES interval=${INTERVAL}s $(date '+%F %T')" | tee -a "$LOG_FILE"
trap 'echo "[parallel] interrupted $(date)" | tee -a "$LOG_FILE"; exit 0' INT TERM

i=0
while :; do
    i=$((i + 1))
    echo "================ parallel cycle $i/$CYCLES  $(date '+%F %T') ================" | tee -a "$LOG_FILE"

    # --- Paper loop (background) ---
    (
        echo "[paper] cycle $i start" >> "$LOG_FILE"
        "$PY" "$REPO/orchestrator.py" >> "$LOG_FILE" 2>&1
        echo "[paper] cycle $i exit=$?" >> "$LOG_FILE"
    ) &
    PID_PAPER=$!

    # --- Cross Market Research Brief (background, research-only) ---
    (
        echo "[cross_market] cycle $i start" >> "$LOG_FILE"
        /bin/sh "$REPO/scripts/cross_market_brief_cron.sh" all >> "$LOG_FILE" 2>&1
        echo "[cross_market] cycle $i exit=$?" >> "$LOG_FILE"
    ) &
    PID_CM=$!

    wait "$PID_PAPER" || echo "[warn] paper cycle $i non-zero" | tee -a "$LOG_FILE"
    wait "$PID_CM" || echo "[warn] cross_market cycle $i non-zero" | tee -a "$LOG_FILE"

    # status snapshot
    "$PY" - <<PYEOF >> "$LOG_FILE" 2>&1 || true
import json
from datetime import datetime
from pathlib import Path

repo = Path("$REPO")
status = {
    "cycle": $i,
    "total_cycles": $CYCLES,
    "updated_at": datetime.now().isoformat(),
}
for name, p in [
    ("closed_registry", repo / "data" / "positions_closed_registry.json"),
    ("postmortems", repo / "data" / "postmortems.jsonl"),
    ("orchestrator", repo / "data" / "orchestrator_status.json"),
]:
    path = p
    if path.exists():
        if path.suffix == ".jsonl":
            status[name + "_rows"] = sum(1 for _ in path.open() if _.strip())
        elif name == "closed_registry":
            data = json.loads(path.read_text())
            status[name + "_rows"] = len(data) if isinstance(data, list) else len(data)
        else:
            status[name] = json.loads(path.read_text()).get("state")
Path("$STATUS_FILE").write_text(json.dumps(status, ensure_ascii=False, indent=2))
print(f"  [status] cycle={$i} snapshot -> $STATUS_FILE")
PYEOF

    if [ "$i" -ge "$CYCLES" ]; then
        echo "[parallel] 完成 $CYCLES 周期 $(date '+%F %T')" | tee -a "$LOG_FILE"
        break
    fi
    echo "[parallel] sleep ${INTERVAL}s until cycle $((i + 1))..." | tee -a "$LOG_FILE"
    sleep "$INTERVAL"
done

echo "[parallel] done" | tee -a "$LOG_FILE"
