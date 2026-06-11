#!/usr/bin/env bash
# =============================================================================
# run_live_probe_loop.sh — Phase 4 小额 live probe（真实下单，独立脚本）
# -----------------------------------------------------------------------------
# ⚠ 与 run_host_loop.sh（dry-run）分离。仅在用户显式授权 Phase 4 后使用。
# ⚠ 必须在【你自己的终端】运行；确保 pm-trader 已配置且余额可承受 probe 上限。
#
# 安全默认：
#   - 必须 PA_LIVE_PROBE=1（本脚本强制）
#   - 不设 EXECUTOR_DRY_RUN（真实下单）
#   - 仅 paper_probe / exploration / 小仓协整信号
#   - 单笔 ≤ $25，每周期 ≤ 2 笔，每日 ≤ $100 买入
#   - 日亏损 ≥ $50 → 写 data/STOP_TRADING（阻断新买入，urgent 止损仍可卖）
#
# 用法：
#   bash scripts/run_live_probe_loop.sh
#   PA_LIVE_PROBE_MAX_USD=15 PA_LOOP_CYCLES=6 bash scripts/run_live_probe_loop.sh
#
# 紧急停机：
#   touch data/STOP_TRADING   # 或 echo reason > data/STOP_TRADING
# =============================================================================
set -uo pipefail
cd "$(dirname "$0")/.." || exit 1
REPO="$(pwd)"
PY="$REPO/venv/bin/python"
DEPS='import numpy,requests,aiohttp,openai,pandas'

if ! "$PY" -c "$DEPS" >/dev/null 2>&1; then
    echo "[fatal] venv 不可用，请先 bash scripts/run_host_loop.sh 一次完成 venv 自检"
    exit 1
fi

# --- Phase 4 live probe env（真实下单）---
unset EXECUTOR_DRY_RUN
export PA_LIVE_PROBE=1
export PA_SHADOW_DB="${PA_SHADOW_DB:-1}"
export PA_COINT_SIGNALS="${PA_COINT_SIGNALS:-1}"
export PA_COINT_EXPLORE="${PA_COINT_EXPLORE:-1}"
export PA_ENFORCE_LEARNING="${PA_ENFORCE_LEARNING:-1}"
export PA_LIVE_PROBE_ONLY_PROBE="${PA_LIVE_PROBE_ONLY_PROBE:-1}"
export PA_LIVE_RISK_ENFORCE="${PA_LIVE_RISK_ENFORCE:-1}"
export PA_LIVE_STOP_LOSS_ALLOW="${PA_LIVE_STOP_LOSS_ALLOW:-1}"
export PA_LIVE_PROBE_MAX_USD="${PA_LIVE_PROBE_MAX_USD:-25}"
export PA_LIVE_PROBE_MAX_PER_CYCLE="${PA_LIVE_PROBE_MAX_PER_CYCLE:-2}"
export PA_LIVE_PROBE_MAX_DAILY_USD="${PA_LIVE_PROBE_MAX_DAILY_USD:-100}"
export PA_LIVE_PROBE_MAX_DAILY_LOSS_USD="${PA_LIVE_PROBE_MAX_DAILY_LOSS_USD:-50}"

if [ -f "$REPO/data/STOP_TRADING" ]; then
    echo "[warn] STOP_TRADING 已存在 — 新买入将被阻断，urgent 止损仍可执行"
    head -1 "$REPO/data/STOP_TRADING" || true
fi

INTERVAL="${PA_LOOP_INTERVAL:-300}"
CYCLES="${PA_LOOP_CYCLES:-0}"
echo "[live] Phase 4 probe｜max_usd=$PA_LIVE_PROBE_MAX_USD/cycle=$PA_LIVE_PROBE_MAX_PER_CYCLE interval=${INTERVAL}s"
trap 'echo; echo "[live] 中断退出"; exit 0' INT TERM

i=0
while :; do
    i=$((i + 1))
    echo "================ LIVE cycle $i  $(date '+%F %T') ================"
    "$PY" "$REPO/orchestrator.py" || echo "[warn] cycle $i 非零退出，继续"
    if [ -f "$REPO/data/live_probe_audit.json" ]; then
        "$PY" -c "
import json
from pathlib import Path
p=Path('$REPO/data/live_probe_audit.json')
if p.exists():
    d=json.loads(p.read_text())
    print('  [live_probe] allowed=%s blocked=%s' % (d.get('allowed_count'), d.get('blocked_count')))
" 2>/dev/null || true
    fi
    if [ "$CYCLES" != "0" ] && [ "$i" -ge "$CYCLES" ]; then
        echo "[live] 完成 $CYCLES 周期"; break
    fi
    sleep "$INTERVAL"
done
