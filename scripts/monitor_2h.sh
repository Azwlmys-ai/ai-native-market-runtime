#!/usr/bin/env bash
# monitor_2h.sh — 2 小时稳定性监控（8 周期 × 15 分钟）
# 严格 dry-run，绝不真实下单
# 用法：bash scripts/monitor_2h.sh

set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV="$ROOT/venv"
MONITOR_LOG="$ROOT/logs/monitor_2h_$(date +%Y%m%d_%H%M%S).log"
TOTAL_CYCLES=8
INTERVAL_SECS=900   # 15 分钟

export EXECUTOR_DRY_RUN=1
export PM_TRADER_PATH="/tmp/mock_pm_trader.sh"
export PATH="$VENV/bin:$PATH"
export PYTHONPATH="$ROOT${PYTHONPATH:+:$PYTHONPATH}"

mkdir -p "$ROOT/logs"

log() {
    local msg="[$(date '+%Y-%m-%d %H:%M:%S')] $*"
    echo "$msg"
    echo "$msg" >> "$MONITOR_LOG"
}

log "════════════════════════════════════════════════════"
log "  2h Monitor START  CYCLES=$TOTAL_CYCLES  INTERVAL=${INTERVAL_SECS}s"
log "  EXECUTOR_DRY_RUN=$EXECUTOR_DRY_RUN"
log "  LOG=$MONITOR_LOG"
log "════════════════════════════════════════════════════"

# 初始化 metrics 文件
echo "" > "$ROOT/data/monitor_metrics.jsonl"

# 确保 mock pm-trader 存在
if [ ! -x "$PM_TRADER_PATH" ]; then
    cat > "$PM_TRADER_PATH" <<'EOF'
#!/bin/sh
case "$1" in
  balance) printf '{"ok":true,"data":{"total_value":0,"pnl":0}}\n' ;;
  *)       printf '{"ok":true,"dry_run":true}\n' ;;
esac
EOF
    chmod +x "$PM_TRADER_PATH"
fi

CYCLE_EXIT=0

for CYCLE in $(seq 1 $TOTAL_CYCLES); do
    CYCLE_START="$(date -u '+%Y-%m-%dT%H:%M:%SZ')"
    log "──── Cycle $CYCLE/$TOTAL_CYCLES  start=$CYCLE_START ────"

    # 1. 写入 paper signal
    log "[C$CYCLE] write_paper_signal..."
    python3 "$ROOT/scripts/write_paper_signal.py" >> "$MONITOR_LOG" 2>&1 || true

    # 2. 跑 main.py --mode once（同 run_local_dryrun.sh 核心步骤）
    log "[C$CYCLE] running main.py --mode once..."
    cd "$ROOT"
    python3 main.py --mode once >> "$MONITOR_LOG" 2>&1
    CYCLE_EXIT=$?
    log "[C$CYCLE] main.py exit=$CYCLE_EXIT"

    # 3. 采集指标
    log "[C$CYCLE] collecting metrics..."
    python3 "$ROOT/scripts/collect_metrics.py" \
        --cycle "$CYCLE" \
        --cycle-start "$CYCLE_START" 2>&1 | tee -a "$MONITOR_LOG"

    # 4. 安全断言：success 必须为 0
    SUCCESS_COUNT=$(python3 - <<'PYEOF' 2>/dev/null || echo 0
import json, os
f = os.environ.get("PYTHONPATH","").split(":")[0] + "/data/execution_results.json"
try:
    d = json.load(open(f))
    print(sum(1 for r in d.get("results",[]) if r.get("status")=="success"))
except Exception:
    print(0)
PYEOF
)
    if [ "$SUCCESS_COUNT" -gt 0 ]; then
        log "🚨 ABORT: success=$SUCCESS_COUNT 检测到真实下单！立即停止！"
        exit 1
    fi
    log "[C$CYCLE] safety OK: success=$SUCCESS_COUNT dry_run enforced"

    log "──── Cycle $CYCLE/$TOTAL_CYCLES DONE ────"

    # 5. 等待，最后一轮不等
    if [ "$CYCLE" -lt "$TOTAL_CYCLES" ]; then
        log "Sleeping ${INTERVAL_SECS}s until cycle $((CYCLE+1))..."
        sleep "$INTERVAL_SECS"
    fi
done

log "════════════════════════════════════════════════════"
log "  2h Monitor COMPLETE  all $TOTAL_CYCLES cycles done"
log "════════════════════════════════════════════════════"

# 输出最终汇总
python3 - <<'PYEOF' 2>&1 | tee -a "$MONITOR_LOG"
import json, os
base = os.environ.get("PYTHONPATH","").split(":")[0]
mf = base + "/data/monitor_metrics.jsonl"
lines = [json.loads(l) for l in open(mf) if l.strip()]
if not lines:
    print("No metrics collected.")
else:
    print("\n=== 8-Cycle Summary ===")
    total_sigs = sum(r["signals"] for r in lines)
    total_approved = sum(r["approved"] for r in lines)
    total_rejected = sum(r["rejected"] for r in lines)
    total_tokens = sum(r["estimated_tokens"]["total"] for r in lines)
    total_fallback = sum(r["fallback_triggered"] for r in lines)
    total_retry = sum(r["retry_count"] for r in lines)
    total_dry = sum(r["execution"]["dry_run"] for r in lines)
    total_success = sum(r["execution"]["success"] for r in lines)
    print(f"  cycles         : {len(lines)}")
    print(f"  total signals  : {total_sigs}")
    print(f"  total approved : {total_approved}")
    print(f"  total rejected : {total_rejected}")
    print(f"  total tokens~  : {total_tokens}")
    print(f"  fallback total : {total_fallback}")
    print(f"  retry total    : {total_retry}")
    print(f"  dry_run total  : {total_dry}")
    print(f"  success total  : {total_success}  (MUST=0)")
    print()
    for r in lines:
        print(f"  C{r['cycle']:02d} | sig={r['signals']} ap={r['approved']} rej={r['rejected']} "
              f"tok~{r['estimated_tokens']['total']} fb={r['fallback_triggered']} "
              f"dry={r['execution']['dry_run']} ok={r['execution']['success']}")
PYEOF

unset EXECUTOR_DRY_RUN PM_TRADER_PATH
