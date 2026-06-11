#!/usr/bin/env bash
# =============================================================================
# run_host_loop.sh — 主机真跑：累积真实价格历史 + 喂协整闭环（全程 dry-run，无真金）
# -----------------------------------------------------------------------------
# ⚠ 必须在【你自己的终端】(Terminal.app / iTerm) 跑，不要在 Cursor agent 里跑——
#   agent 的 shell 被强制走代理(127.0.0.1:61275)，外部行情/数据 API 不可达；
#   你的终端没有这个代理，网络正常。
#
# 做什么（PRD §7 闭环 + Phase 5 纸面强制层）：
#   每周期 orchestrator.run_once → 采集真实行情 → 记录价格历史 → 协整重算
#   （含探索层）→ PA_COINT_SIGNALS 把候选转 probe → PA_ENFORCE_LEARNING 调 position_size
#   → Agent M → executor(dry-run) → postmortem(models_used) → model_effectiveness.by_model。
#
# 用法：
#   bash scripts/run_host_loop.sh                 # 无限循环，每 300s 一周期
#   PA_LOOP_INTERVAL=600 PA_LOOP_CYCLES=12 bash scripts/run_host_loop.sh  # 12 周期、间隔 600s
#   PA_COINT_EXPLORE=0 bash scripts/run_host_loop.sh   # 关探索层，只要研究层严格候选
#
# 安全：EXECUTOR_DRY_RUN=1 恒定 → 绝不真实下单。
# Phase 5：PA_ENFORCE_LEARNING 默认开（纸面强制层，只改 position_size；关：PA_ENFORCE_LEARNING=0）。
# =============================================================================
set -uo pipefail
cd "$(dirname "$0")/.." || exit 1
REPO="$(pwd)"
PY="$REPO/venv/bin/python"
DEPS='import numpy,requests,aiohttp,openai,pandas'

# --- venv 自检/重建（原 venv 指向旧部署路径 /opt/... 已失效）---
if ! "$PY" -c "$DEPS" >/dev/null 2>&1; then
    echo "[setup] venv 不可用或缺依赖，重建中…"
    rm -rf "$REPO/venv"
    python3 -m venv "$REPO/venv" || { echo "[fatal] 无法建 venv，请确认 python3"; exit 1; }
    "$PY" -m pip install -q --upgrade pip
    if ! "$PY" -m pip install -q -r "$REPO/requirements.txt"; then
        echo "[setup] 常规安装失败，尝试 --trusted-host（macOS SSL）…"
        "$PY" -m pip install -q --trusted-host pypi.org --trusted-host files.pythonhosted.org \
            -r "$REPO/requirements.txt" || { echo "[fatal] 依赖安装失败"; exit 1; }
    fi
    "$PY" -c "$DEPS" >/dev/null 2>&1 || { echo "[fatal] 依赖仍缺失"; exit 1; }
    echo "[setup] venv 就绪。"
fi

# --- 闭环 env 门控（全程 dry-run + 喂协整 + 探索层冷启动加速）---
export EXECUTOR_DRY_RUN=1
export PA_SHADOW_DB=1
export PA_COINT_SIGNALS=1
export PA_COINT_EXPLORE="${PA_COINT_EXPLORE:-1}"
# 探索阈值可调：export PA_COINT_EXPLORE_CORR=0.5 PA_COINT_EXPLORE_Z=1.5
# Phase 5 纸面强制层（PRD §13 learning→仓位）；仅 dry-run 下默认开，可显式关
export PA_ENFORCE_LEARNING="${PA_ENFORCE_LEARNING:-1}"
# Phase 3c 模型沙盒定时快照（默认关；只写 research/model_sandbox/，不写 signals/review）
# export PA_MODEL_SANDBOX_SNAPSHOT=1
# Phase 3e Observation 增量导出（默认关；只写 data/historical + research）
# export PA_OBSERVATION_BACKFILL=1

INTERVAL="${PA_LOOP_INTERVAL:-300}"
CYCLES="${PA_LOOP_CYCLES:-0}"   # 0 = 无限
echo "[run] dry-run 闭环启动｜explore=$PA_COINT_EXPLORE enforce=$PA_ENFORCE_LEARNING interval=${INTERVAL}s cycles=${CYCLES:-∞}"
trap 'echo; echo "[run] 收到中断，退出。"; exit 0' INT TERM

i=0
while :; do
    i=$((i + 1))
    echo "================ cycle $i  $(date '+%F %T') ================"
    "$PY" "$REPO/orchestrator.py" || echo "[warn] cycle $i orchestrator 非零退出，继续"
    # 周期末协整候选概况（喂闭环是否出货）
    "$PY" - <<'PYEOF' 2>/dev/null || true
from runtime import cointegration as c
r = c.find_candidates()
print("  [coint] " + ", ".join(f"{k}={r.get(k)}" for k in
      ("explore_enabled","n_candidates","n_candidates_research","n_candidates_exploration")))
PYEOF
    if [ "${PA_ENFORCE_LEARNING:-0}" != "0" ]; then
        PA_ENFORCE_LEARNING=1 "$PY" "$REPO/scripts/verify_enforcement_live.py" 2>/dev/null | \
            "$PY" -c "import sys,json; d=json.load(sys.stdin); print('  [enforce] applied=%s net_change=%s sizing=%s weight=%s' % (d.get('applied_count'), d.get('net_position_changes'), d.get('n_sizing_applied'), d.get('n_weight_applied')))" 2>/dev/null || true
    fi
    if [ "${PA_MODEL_SANDBOX_SNAPSHOT:-0}" != "0" ]; then
        PA_MODEL_SANDBOX_SNAPSHOT=1 "$PY" -c "from runtime.model_sandbox_snapshot import maybe_refresh; r=maybe_refresh(); print('  [sandbox] enabled=%s ok=%s' % (r.get('enabled'), r.get('ok')))" 2>/dev/null || true
    fi
    if [ "${PA_OBSERVATION_BACKFILL:-0}" != "0" ]; then
        PA_OBSERVATION_BACKFILL=1 "$PY" -c "from runtime.observation_backfill_gate import maybe_run; r=maybe_run(); print('  [obs] enabled=%s ok=%s pm=%s fund=%s' % (r.get('enabled'), r.get('ok'), r.get('pm_appended'), r.get('funding_appended')))" 2>/dev/null || true
    fi
    if [ "$CYCLES" != "0" ] && [ "$i" -ge "$CYCLES" ]; then
        echo "[run] 完成 $CYCLES 周期，退出。"; break
    fi
    sleep "$INTERVAL"
done
