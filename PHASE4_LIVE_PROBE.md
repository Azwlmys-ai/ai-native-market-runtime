# Phase 4 — 小额 Live Probe + Live 风控 + 自动止损

> 用户已授权 Phase 4（2026-06-05）。本阶段在 **显式 env 门控** 下接通真实 pm-trader 下单，
> 严格限定为 probe 级小仓，并与 Agent P 止损链路联动。

---

## 1. 定位

| 能力 | 模块 | 说明 |
|---|---|---|
| Live probe 门控 | `runtime/live_probe.py` | 双重授权、probe 过滤、USD 硬上限 |
| 买入执行 | `executors/signal_executor.py` | 无 `PA_LIVE_PROBE` 绝不真实下单 |
| 止损卖出 | `executors/sell_executor.py` + `agents/agent_p.py` | STOP_TRADING 下仍放行 `urgent` |
| 风控快照 | `risk/risk_engine.py` → `risk_snapshot.json` | `PA_LIVE_RISK_ENFORCE=1` 时违规阻断新买入 |
| 主机循环 | `scripts/run_live_probe_loop.sh` | 与 dry-run `run_host_loop.sh` **分离** |

## 2. 安全纪律

1. **默认全关**：未设 `PA_LIVE_PROBE=1` → 即使去掉 `EXECUTOR_DRY_RUN` 也返回 `blocked_no_live_gate`。
2. **仅 probe**：默认 `PA_LIVE_PROBE_ONLY_PROBE=1` — `grade=paper_probe` / `probe=true` / `tier=exploration` / 小仓协整。
3. **硬上限**（可调）：

| 变量 | 默认 | 含义 |
|---|---|---|
| `PA_LIVE_PROBE_MAX_USD` | 25 | 单笔最大 USD |
| `PA_LIVE_PROBE_MAX_PER_CYCLE` | 2 | 每周期最多真实买入 |
| `PA_LIVE_PROBE_MAX_DAILY_USD` | 100 | 每日累计买入 USD |
| `PA_LIVE_PROBE_MAX_DAILY_LOSS_USD` | 50 | 日亏损熔断 → `STOP_TRADING` |

4. **止损优先**：`STOP_TRADING` 阻断新买入；`PA_LIVE_STOP_LOSS_ALLOW=1`（默认）时 **urgent** 卖单仍执行。
5. **审计**：`data/live_probe_audit.json` + `data/live_probe_state.json`。

## 3. 启动（真实下单）

```bash
cd /Users/libo/.hermes/polymarket_arbitrage

# 建议先确认 pm-trader 与余额
pm-trader balance

# Phase 4 循环（与 dry-run 脚本分开）
bash scripts/run_live_probe_loop.sh

# 或单周期
unset EXECUTOR_DRY_RUN
PA_LIVE_PROBE=1 PA_SHADOW_DB=1 PA_COINT_SIGNALS=1 python3 orchestrator.py
```

**紧急停机**：

```bash
echo "manual halt" > data/STOP_TRADING
```

## 3b. 受控首跑 runbook（最小暴露，主机执行）

> 沙箱无法真实下单（无 pm-trader/账户/网络），故此为主机分阶段流程。**每阶段过关再进下一阶段**，
> 首跑用最小可能暴露（单笔上限 $1、每周期 1 笔、每日 $2）。

**阶段 0 — 前置确认**
```bash
cd /Users/libo/.hermes/polymarket_arbitrage
pytest tests/test_live_probe.py tests/test_smoke.py -q   # 安全逻辑回归全过
pm-trader balance                                        # 确认账户/余额可用
ls data/STOP_TRADING 2>/dev/null && echo "⚠ 存在 STOP_TRADING，先处理" || echo "ok 无停机标志"
```

**阶段 1 — dry-run 彩排**（确认有 probe 信号产出、success=0、无真实下单）
```bash
EXECUTOR_DRY_RUN=1 PA_SHADOW_DB=1 PA_COINT_SIGNALS=1 \
  python3 -c "from orchestrator import Orchestrator; Orchestrator().run_once()"
python3 - <<'PY'
import json
r=json.load(open("data/execution_results.json"))
print("success=",r["success"],"dry_run=",r["dry_run"])   # 期望 success=0
assert r["success"]==0
PY
```

**阶段 2 — 单周期 live，最小上限**（**真实下单**，最小暴露）
```bash
unset EXECUTOR_DRY_RUN
PA_LIVE_PROBE=1 PA_LIVE_PROBE_ONLY_PROBE=1 \
PA_LIVE_PROBE_MAX_USD=1 PA_LIVE_PROBE_MAX_PER_CYCLE=1 PA_LIVE_PROBE_MAX_DAILY_USD=2 \
PA_LIVE_PROBE_MAX_DAILY_LOSS_USD=2 PA_SHADOW_DB=1 PA_COINT_SIGNALS=1 \
  python3 -c "from orchestrator import Orchestrator; Orchestrator().run_once()"
```
立即核对：
```bash
cat data/live_probe_audit.json     # 每笔决策 + reason（被上限拦的应有记录）
cat data/live_probe_state.json     # daily_buy_usd / daily_orders 累计
python3 -c "import json;r=json.load(open('data/execution_results.json'));print('live success=',r['success'],'笔', [x['status'] for x in r['results']])"
```
**过关判据**：真实买入笔数 ≤ 1、单笔 ≤ $1、无非 probe 信号成交、audit 有完整记录。

**阶段 3 — 小循环观察**（确认日上限/熔断生效后再放宽）
```bash
bash scripts/run_live_probe_loop.sh   # 内置上限；先跑几周期看 state/audit 累计与日熔断
```

**回滚 / 急停**（任何异常立即执行）
```bash
echo "manual halt $(date)" > data/STOP_TRADING   # 阻断新买入；urgent 止损仍放行
pkill -f run_live_probe_loop.sh                   # 停循环
# 恢复纯研究：去掉 PA_LIVE_PROBE，回到 EXECUTOR_DRY_RUN=1
```

**放宽顺序**（每步观察 ≥1 日）：MAX_USD $1→$5→$25；MAX_PER_CYCLE 1→2；MAX_DAILY_USD $2→$25→$100。**改一个、看一日**，不要一次放开多个。

## 4. 与 Phase 5 的关系

- dry-run 主机循环（`run_host_loop.sh`）仍默认 `EXECUTOR_DRY_RUN=1` + `PA_ENFORCE_LEARNING=1`。
- live probe 循环可同时开 `PA_ENFORCE_LEARNING=1`，learning 产物继续调 `position_size`（再经 live 上限截断）。

## 5. 验证

```bash
pytest tests/test_live_probe.py -v
```

## 6. 未做 / 后续

- 真实成交与 postmortem 的 `models_used` 自动对齐（依赖 pm-trader 回报字段）。
- 更精细的日亏损核算（当前用 probe 名义本金 × pnl% 估算）。
- Phase 5 全量 auto-live（非 probe 过滤）— 需更多 paper/live 反馈后评审。
