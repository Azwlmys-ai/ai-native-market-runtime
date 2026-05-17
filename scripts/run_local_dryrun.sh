#!/usr/bin/env bash
# run_local_dryrun.sh — 本地全链路 dry-run 安全启动脚本
# 约束：EXECUTOR_DRY_RUN=1 全程，绝不真实下单
# 用法：bash scripts/run_local_dryrun.sh

set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV="$ROOT/venv"

# ── 1. 安全护栏（最优先，不可覆盖）────────────────────────────────
export EXECUTOR_DRY_RUN=1
export PM_TRADER_PATH="/tmp/mock_pm_trader.sh"

# ── 2. venv Python 优先：确保 orchestrator subprocess ["python3",...] 也走 venv ──
export PATH="$VENV/bin:$PATH"

# ── 3. 项目根加入 PYTHONPATH（兼容直接调用场景）──────────────────
export PYTHONPATH="$ROOT${PYTHONPATH:+:$PYTHONPATH}"

# ── 4. 写入 mock pm-trader（每次覆盖，避免旧坏文件污染 dry-run） ──────────
cat > "$PM_TRADER_PATH" <<'EOF'
#!/bin/sh
case "$1" in
  balance)
    printf '{"ok":true,"data":{"total_value":0,"cash":0,"pnl":0}}\n'
    ;;
  portfolio)
    printf '{"ok":true,"data":[]}\n'
    ;;
  *)
    printf '{"ok":true,"dry_run":true}\n'
    ;;
esac
EOF
chmod +x "$PM_TRADER_PATH"
echo "[run_local_dryrun] Refreshed mock pm-trader at $PM_TRADER_PATH"

# ── 5. 打印运行环境摘要 ───────────────────────────────────────────
echo "============================================================"
echo "  polymarket_arbitrage local dry-run"
echo "  $(date '+%Y-%m-%d %H:%M:%S')"
echo "============================================================"
echo "  ROOT              = $ROOT"
echo "  EXECUTOR_DRY_RUN  = $EXECUTOR_DRY_RUN"
echo "  PM_TRADER_PATH    = $PM_TRADER_PATH"
echo "  python3           = $(which python3)"
echo "  python3 version   = $(python3 --version 2>&1)"
echo "============================================================"
echo ""

# ── 6. 跑单周期 ──────────────────────────────────────────────────
cd "$ROOT"
python3 main.py --mode once
EXITCODE=$?

echo ""
echo "============================================================"
echo "  run_once 退出码: $EXITCODE"
echo "============================================================"

# ── 7. 验证关键输出 ───────────────────────────────────────────────
echo ""
echo "── 验证 data/latest_data.json ──"
if [ -f "$ROOT/data/latest_data.json" ]; then
    python3 - <<'PYEOF'
import json, sys, os
root = os.environ.get("PYTHONPATH", "").split(":")[0]
f = os.path.join(root, "data", "latest_data.json")
d = json.load(open(f))
status = d.get("polymarket_status", "MISSING")
markets = d.get("polymarket_markets", [])
print(f"  polymarket_status : {status}")
print(f"  polymarket_markets: {len(markets)} 条")
if status == "ok" and len(markets) > 0:
    print("  ✅ Polymarket 采集成功")
else:
    print("  ⚠️  Polymarket 采集失败或数据为空")
PYEOF
else
    echo "  ❌ latest_data.json 不存在"
fi

echo ""
echo "── 验证 data/signals.json ──"
if [ -f "$ROOT/data/signals.json" ]; then
    python3 - <<'PYEOF'
import json, os
root = os.environ.get("PYTHONPATH", "").split(":")[0]
f = os.path.join(root, "data", "signals.json")
sigs = json.load(open(f))
print(f"  信号数量: {len(sigs)}")
ok = 0
for s in sigs:
    if s.get("generated_at") or s.get("timestamp"):
        ok += 1
print(f"  有 generated_at/timestamp: {ok}/{len(sigs)}")
if ok == len(sigs) and len(sigs) > 0:
    print("  ✅ signals.json 结构正常")
elif len(sigs) == 0:
    print("  ℹ️  signals.json 为空（当前市场无套利机会属正常）")
else:
    print("  ⚠️  部分信号缺少时间戳")
PYEOF
else
    echo "  ℹ️  signals.json 不存在（无信号生成，属正常）"
fi

echo ""
echo "── 验证 execution_results.json ──"
if [ -f "$ROOT/data/execution_results.json" ]; then
    python3 - <<'PYEOF'
import json, os
root = os.environ.get("PYTHONPATH", "").split(":")[0]
f = os.path.join(root, "data", "execution_results.json")
d = json.load(open(f))
results = d.get("results", [])
live_orders = [r for r in results if r.get("status") == "success"]
dry = [r for r in results if r.get("status") == "dry_run"]
skipped = [r for r in results if r.get("status") == "skipped"]
print(f"  dry_run : {len(dry)}")
print(f"  skipped : {len(skipped)}")
print(f"  success (真实下单!): {len(live_orders)}")
if len(live_orders) == 0:
    print("  ✅ 无真实下单")
else:
    print("  🚨 发现真实下单记录！请立即检查！")
PYEOF
else
    echo "  ℹ️  execution_results.json 不存在（无执行，属正常）"
fi

echo ""
echo "── 清理 ──"
unset EXECUTOR_DRY_RUN
unset PM_TRADER_PATH
echo "  已 unset 环境变量"
echo "============================================================"
echo "  dry-run 完成"
echo "============================================================"
