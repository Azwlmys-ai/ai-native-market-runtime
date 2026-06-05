# Phase 3c — Agent B → Research/Hypothesis（分两步）

> 日期：2026-06-03
> Phase 3 第三步。两步走：**3c-1 加法派生（本轮，沙箱验证通过）** + **3c-2 扩 B prompt（后续，主机验证）**。
> 闭环目标：`hypotheses(signal_uid) → signals → paper_positions → postmortems(signal_uid)`，让「当初的假设」可与「实际结果/复盘」对照。

---

## 3c-1 加法派生（已完成，零 live 风险）

### 做什么

把每个 Agent B 信号确定性派生成结构化研究假设，写 `data/hypotheses.jsonl`（事实源）+ 影子 `hypotheses` 表。**不改 agent_b、不改 LLM prompt、不改交易决策。**

PRD hypothesis 五要素：

| 字段 | 来源 |
|---|---|
| direction / confidence / expected_edge | 信号现成字段（真值） |
| holding_horizon_days | 从 risk_notes 的 `time_risk: end_date` 派生到期天数 |
| thesis | 信号 reason / logic_chain |
| risk_summary | 信号 risk_notes 汇总 |
| failure_conditions | 从 risk_notes 的 strategy/correlation 风险项派生（偏样板） |

**前向兼容 3c-2**：`build_hypothesis` 对 `holding_horizon_days` / `failure_conditions` **原生字段优先** —— 一旦 agent_b prompt 开始输出这俩，提取器自动采用真值，`source` 从 `derived` 变 `agent_b`，无需再改提取器。

### 新增/改动

| 文件 | 改动 |
|---|---|
| `runtime/hypothesis.py` | 新增：build_hypothesis（派生+原生优先）+ generate（读 signals.json，jsonl 去重幂等） |
| `runtime/schema.sql` | 加 `hypotheses` 表；版本 → `0.3.2-phase3c` |
| `runtime/_shadow.py` | upsert_hypothesis / query_hypotheses |
| `runtime/datastore.py` | append_hypothesis（jsonl 事实源 + 影子） |
| `runtime/api.py` | `GET /hypotheses` |
| `orchestrator.py` | 步骤 12.5b：consolidation 后无条件派生（best-effort，不改交易决策） |

### 验证（沙箱，全过）

- **派生 vs 原生**：信号无原生字段 → hold_days 从 end_date 算（90 天）、source=derived；信号带原生 holding_horizon_days=14 + failure_conditions → 自动采用、source=agent_b。
- **幂等**：再 generate=0，jsonl 不重复。
- **闭环 join**：`hypothesis.signal_uid == postmortem.signal_uid`（同一信号的假设与复盘可对照）。
- **API** `GET /hypotheses` 正常。
- 真实 signals.json：8 信号 → 6 假设（2 条同 signal_uid 去重），全 derived、持仓时长/失败条件 6/6 有值。
- ingest 无回归（schema 0.3.2，hypotheses 表 ingest 不生成=0，paper_positions=22）。

> 真实派生的 failure_conditions 多为样板 strategy_risk（语义薄）——这正是 3c-2 扩 prompt 的价值所在；原生优先逻辑已就绪。

### 主机验证步骤（已跑，2026-06-03）

```bash
cd /Users/libo/.hermes/polymarket_arbitrage
venv/bin/python3 -m pytest tests/test_smoke.py -q     # 期望仍 71（agent_b 未改，仅加法派生）
rm -f data/runtime.db data/runtime.db-wal data/runtime.db-shm
PA_BASE_DIR="$PWD" venv/bin/python3 -m runtime.ingest # schema → 0.3.2

EXECUTOR_DRY_RUN=1 PA_SHADOW_DB=1 PM_TRADER_PATH=/tmp/mock_pm_trader.sh \
  venv/bin/python3 -c "from orchestrator import Orchestrator; Orchestrator().run_once()"
# 预期：日志「🔬 派生 N 条研究假设」；data/hypotheses.jsonl 生成

PA_SHADOW_DB=1 PA_BASE_DIR="$PWD" venv/bin/python3 -m uvicorn runtime.api:app --port 8848 &
curl -s 'localhost:8848/hypotheses?limit=3' | python3 -m json.tool | head -40
```

主机结果：
- smoke **71 passed**（2 个既有 deprecated wrapper warning）。
- 删库重建 ingest 正常；schema `0.3.2-phase3c`；`hypotheses=0`（ingest 不生成）；`paper_positions=22`；`markets=107`。
- 受控单周期完成；日志出现 `🔬 派生 1 条研究假设 (hypotheses)`、`✅ 扫描周期完成`、`🗃️ 影子库已刷新 (runtime.db)`；`data/hypotheses.jsonl` 生成。
- `hypotheses` 表：1 行，`source=derived`；样例市场 `Will the Carolina Hurricanes win the 2026 NHL Stanley Cup?`，direction=NO，confidence=85，expected_edge=19.5，holding_horizon_days=27。
- 假设↔复盘 join：0（本轮信号暂无对应 postmortem，正常）。
- execution 护栏：`success=0/dry_run=1/failed=0`；无 traceback/sqlite/no such column/OperationalError/Exception；无残留项目进程。

---

## 3c-2 扩 Agent B prompt（主机验证通过）

### 做什么

在 agent_b 的 LLM prompt 输出 JSON 里新增两个字段（任务要求 + 输出示例都加了）：
- `holding_horizon_days`：B 判断的预期持仓天数。
- `failure_conditions`：B 逐市场推理的失败条件（具体到该市场，不泛泛而谈）。

### 关键发现并修复（否则 3c-2 静默失效）

`orchestrator._consolidate_signals_for_review` 用**固定字段白名单**把 Agent B 输出归一进 signals.json，原白名单不含新字段 → 新字段会在汇总时被丢掉、到不了 signals.json、提取器永远看不到。已把 `holding_horizon_days` / `failure_conditions` **加入白名单**透传。`enrich_signals` 本身 `dict(signal)` 全量保留，无需改。

### Agent M 容忍性（核心风险，已确认）

读 agent_m：M 全程 `signal.get(key, default)` 防御式取值 + 在 prompt 里 `json.dumps(signal)` **整体 dump**，**无严格 schema 校验、无 required-keys 拒绝、无会 KeyError 的访问**。新字段只会：(1) 进 M 的 prompt 上下文（有益，M 能看到失败条件）；(2) 永不被以会炸的方式访问。→ M 对新字段安全。

### 新增/改动

| 文件 | 改动 |
|---|---|
| `agents/agent_b.py` | prompt 要求 #8 + 输出 JSON 示例加 holding_horizon_days / failure_conditions |
| `orchestrator.py` | consolidation 白名单加这两个字段（透传到 signals.json） |

### 验证（沙箱，全过）

- **透传链路**：模拟 B 原生输出(holding_horizon_days=27 + 逐市场 failure_conditions) → `_consolidate_signals_for_review` → signals.json **保留**两字段 → 提取器 `source=agent_b`、采用真值(27 天 + 真失败条件)。
- **M 容忍**：带新字段的 signal 经 M 访问模式（`.get` + `json.dumps`）不报错；缺键返回默认；新字段在 dump 中可见。
- py_compile 通过。

> agent_b/agent_m 含 LLM 依赖、沙箱不可导入运行；prompt 改动本身（LLM 是否真吐字段）只能主机带真实 LLM 验证。透传与提取链路已用 Orchestrator（不依赖 openai）实跑验证。

### 主机验证步骤（已跑，2026-06-03）

```bash
cd /Users/libo/.hermes/polymarket_arbitrage
venv/bin/python3 -m pytest tests/test_smoke.py -q     # 期望仍 71（prompt + 白名单均加法）
rm -f data/runtime.db data/runtime.db-wal data/runtime.db-shm
PA_BASE_DIR="$PWD" venv/bin/python3 -m runtime.ingest

# 真实周期：agent_b 真实 LLM 应吐出新字段
EXECUTOR_DRY_RUN=1 PA_SHADOW_DB=1 PM_TRADER_PATH=/tmp/mock_pm_trader.sh \
  venv/bin/python3 -c "from orchestrator import Orchestrator; Orchestrator().run_once()"

# 看 hypotheses 是否出现 source=agent_b + 逐市场失败条件
venv/bin/python3 - <<'PY'
import sqlite3; c=sqlite3.connect("data/runtime.db")
print("source 分布:", dict(c.execute("SELECT source,COUNT(*) FROM hypotheses GROUP BY source").fetchall()))
for r in c.execute("SELECT market_name,source,holding_horizon_days,failure_conditions FROM hypotheses WHERE source='agent_b' LIMIT 3"):
    print(" ", r);
c.close()
PY
```

主机结果：
- smoke **71 passed**（2 个既有 deprecated wrapper warning）。
- 删库重建正常：schema `0.3.2-phase3c`；`hypotheses=0`（ingest 不生成）；`paper_positions=22`；`markets=107`。
- 受控单周期完成：Agent B 汇总 8 个新信号；日志出现 `🔬 派生 8 条研究假设 (hypotheses)`。
- **Agent M 审查成功**：`✅ agent_m 执行成功`，无解析报错/traceback。
- `signals.json`：8/8 信号带 `holding_horizon_days` 或 `failure_conditions`，证明 B 真吐字段且 consolidation 白名单已透传。
- `hypotheses` 表：8 行，source 分布 `{'agent_b': 8}`，说明提取器采用 B 原生字段。
- 样例：`New Rihanna Album before GTA VI?`，hold=180，failure_conditions 为逐市场失败条件；`Will Jesus Christ return before GTA VI?`，hold=365。
- 假设↔复盘闭环 join=2。
- execution 护栏：`success=0/failed=0`（本轮 total=0/dry_run=0，无待执行买入）；最终状态 `completed`。
- 无 traceback/sqlite/no such column/OperationalError/Exception；无残留项目进程。

---

## 局限 / 后续

- 3c-1 的 failure_conditions/holding_horizon 是派生，语义偏弱；3c-2 提供真推理。
- 全重构 B 为纯研究（不产信号、交易决策下放）属 PRD 最激进版，会打断 B→M→执行流水线，**不在 3c 范围**，建议与 Phase 3d(Agent M) 一起评估。
- Phase 3 剩余：Agent M（risk grading 三级，动审批/交易，风险最高）。
