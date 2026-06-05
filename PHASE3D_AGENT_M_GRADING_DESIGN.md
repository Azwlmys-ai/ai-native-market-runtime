# Phase 3d — Agent M 三级 Risk Grading（主机补充验证通过）

> 日期：2026-06-03
> Phase 3 压轴，**唯一直接改审批→交易行为**的一步。先设计 + 拍选型，再实现。

---

## 1. 现状（调研结论）

- **M 是纯二元**：`review_signal` 让 LLM 输出 `decision=APPROVE/REJECT` + `failure_probability(0-100)`；聚合时 `if decision=="APPROVE": approved else rejected`（agent_m.py:513）。
- **approved_signals.json = 全部 approved 信号**（不分 paper/real 执行）。`approved_signals_only = [r["signal"] for r in approved]`（:569）。
- **现有 `_is_paper`** 基于信号的 `paper:true` 标志或 `source` 前缀（:534），**只用于 review_results 的计数报表**，approved_paper 和 approved_real 都进同一个 approved_signals_only 一起执行 —— 与 PRD paper_probe **是两回事**，当前几乎恒为 0。
- **signal_executor** 读 approved_signals.json，按 `signal.position_size` 执行，全程 dry_run 护栏（status=dry_run，success=0）。
- **reviews 影子表**（Phase 1 建）已有 `decision` 列，**预留可存 PAPER_PROBE**。

硬规则前置：`_deterministic_rejection` 会先做纯 Python 拒绝（仓位/EV 越界等），不进 LLM。

---

## 2. PRD 目标

| 等级 | 含义 |
|---|---|
| approve | 正常 paper（正常仓位） |
| paper_probe | 小仓试错（边缘信号不再一票否决，给小额受控试错） |
| reject | 风险过高，不执行 |

核心理念：**不再一票否决**；边缘信号（当前会被 REJECT 的中等失败概率信号）改成小仓 paper 试错，失败也能沉淀进复盘学习。

---

## 3. 提议方案

### 3.1 三级判定（确定性后处理 + LLM）

保留 M 的 LLM 输出 `failure_probability` + `decision`，**新增一层确定性映射**把 (decision, failure_probability, 信号健全性) → 最终 grade：

```
若 deterministic_rejection 命中           → REJECT（硬规则，最高优先，不变）
否则 LLM APPROVE 且 failure_prob < 35%    → APPROVE
否则 信号健全(有 data_sources+logic_chain, 0<EV<100, 仓位<20%)
     且 35% <= failure_prob < PROBE_MAX   → PAPER_PROBE   ← 原本会被 REJECT 的边缘信号
否则                                       → REJECT
```

确定性层好处：可沙箱单测、逻辑显式、不依赖 LLM 是否“学会”三级。LLM prompt 也会同步加 PAPER_PROBE 说明（让 LLM 主动提议），但**最终 grade 由确定性层裁定**，更安全可控。

### 3.2 paper_probe 怎么执行

- approved_signals.json 同时包含 APPROVE + PAPER_PROBE 信号。
- PAPER_PROBE 信号：`grade="paper_probe"` + `position_size` 被 M **压到小仓**（probe 上限，如 2-3%）。
- signal_executor 照常执行（已按 position_size），**仍是 dry_run** → success 恒 0 护栏不破，paper_probe 是“小额 paper”，绝不实盘。
- grade 随信号流入 paper_pnl/paper_trades + reviews 表 → 复盘/归因能区分 probe vs 正常。

### 3.3 学习隔离（防污染）

- probe 的执行 status 仍是 `dry_run`（现有学习只学 success/failed，天然不学 dry_run/simulated）→ 不污染。
- grade 字段额外标记，未来 paper 闭环成熟后可单独学“probe 命中率”。

---

## 4. 风险与验证策略

| 风险 | 应对 |
|---|---|
| 改审批→更多信号被 paper 执行 | 全程 dry_run，success=0 护栏不变；probe 仓位封顶很小 |
| 学习样本污染 | probe status=dry_run，现有过滤天然隔离；额外 grade 标记 |
| M LLM 不配合三级 | 最终 grade 由**确定性层**裁定，不靠 LLM |
| 下游执行器/paper_pnl 不认 grade | grade 是附加字段，执行器只读 position_size（向后兼容，参考 3c-2 M 容忍性已证） |

沙箱可验：确定性 grade 映射函数（纯函数，喂各种 failure_prob/健全性组合）、probe 仓位封顶、reviews 表记录三级。
主机验证：真实周期看 review_results 出现 paper_probe、execution 仍 success=0、学习样本不被污染。

---

## 5. 拍板决策（已定）

1. **判定机制**：两者结合（LLM 提议 PAPER_PROBE + 确定性 `_grade()` 裁定）。
2. **probe band**：激进 `failure_probability ∈ [35%, 60%)`。
3. **probe 仓位封顶**：正常仓 × 0.25。
4. **本轮范围**：probe 直接执行小额 paper（reject→probe 立即生效，全程 dry-run）。

---

## 6. 实现（已完成，沙箱验证通过）

### 改动

| 文件 | 改动 |
|---|---|
| `agents/agent_m.py` | prompt 加 PAPER_PROBE 三级说明；新增确定性 `_grade()`（band 35-60% + 健全性守护）+ `_signal_sound()`；聚合三级分流；probe 压仓 ×0.25 + `grade` 标记；`approved_signals_only = approve + probe`；output 加 paper_probe/probe_signals；新增 `risk.paper_probe` 事件 |
| `runtime/_shadow.py` | `upsert_reviews` 读 `probe_signals` 记 `PAPER_PROBE` |

### `_grade()` 裁定逻辑（确定性，硬规则拒绝已前置）

```
失败概率 >= 60%                              → REJECT
35% <= 失败概率 < 60% 且信号健全              → PAPER_PROBE（不再一票否决；不健全→REJECT）
失败概率 < 35% 且 LLM=APPROVE 且信号健全       → APPROVE（否则 REJECT：LLM 有数据/逻辑顾虑）
```
健全 = 有 data_sources + logic_chain（probe 也要求健全，不试错垃圾信号）。

### 验证（沙箱，全过）

- **`_grade()` 真值表 9 用例全对**：含关键“不再一票否决”(fp=40 LLM=REJECT→PAPER_PROBE)、上限封顶(fp=40 LLM=APPROVE 也→PROBE)、健全性守护(无 data_sources→REJECT)、边界(60→REJECT)。
- **probe 压仓**：0.12 × 0.25 = 0.03。
- **reviews 三级落库**：decision 分布 {APPROVE:1, PAPER_PROBE:1, REJECT:1}。
- agent_m 可导入（沙箱装 openai 仅为导入单测 `_grade`，不调 LLM）；py_compile 通过。

> 全链路（M 真实 LLM 审查 + 执行器执行 probe + 护栏）需主机验证。

### 主机验证步骤（待跑）

```bash
cd /Users/libo/.hermes/polymarket_arbitrage
venv/bin/python3 -m pytest tests/test_smoke.py -q     # 期望仍 71（三级是 _grade 后处理 + output 加字段）
rm -f data/runtime.db data/runtime.db-wal data/runtime.db-shm
PA_BASE_DIR="$PWD" venv/bin/python3 -m runtime.ingest

EXECUTOR_DRY_RUN=1 PA_SHADOW_DB=1 PM_TRADER_PATH=/tmp/mock_pm_trader.sh \
  venv/bin/python3 -c "from orchestrator import Orchestrator; Orchestrator().run_once()" 2>&1 | tail -30

# 看三级分流 + 护栏 + 学习隔离
venv/bin/python3 - <<'PY'
import json,sqlite3
rr=json.load(open("data/review_results.json"))
print("review 三级:", "approved=",rr.get("approved")," paper_probe=",rr.get("paper_probe")," rejected=",rr.get("rejected"))
ap=json.load(open("data/approved_signals.json"))
probes=[s for s in ap if s.get("grade")=="paper_probe"]
print("approved_signals:",len(ap)," 其中 paper_probe:",len(probes), "| probe 仓位样例:", [s.get("position_size") for s in probes[:3]])
er=json.load(open("data/execution_results.json"))
print("execution 护栏:", "success=",er.get("success")," dry_run=",er.get("dry_run")," failed=",er.get("failed"))
c=sqlite3.connect("data/runtime.db")
print("reviews decision 分布:", dict(c.execute("SELECT decision,COUNT(*) FROM reviews GROUP BY decision").fetchall())); c.close()
PY
```

**判断标准**：smoke 71；M 审查无报错；**execution success=0 护栏不破**（probe 仍 dry_run）；review_results 出现 paper_probe 计数；approved_signals 里 probe 信号 `grade=paper_probe` 且仓位被压小；reviews 表出现 PAPER_PROBE 行。
**现实预期**：是否出现 paper_probe 取决于本轮信号的真实 failure_probability 是否落在 [35,60)；若全部 <35 或 >=60，paper_probe 可能为 0，不算失败（band 未命中）。

### 主机验证结果（2026-06-03）

结果分两段：

1. **自然 orchestrator 周期**
   - smoke **71 passed**（2 个既有 deprecated wrapper warning）。
   - 删库重建正常：schema `0.3.2-phase3c`；`reviews=8`；`signals=8`；`paper_positions=22`；`markets=107`。
   - 受控周期完成，最终 `✅ 扫描周期完成` + `🗃️ 影子库已刷新`。
   - 但本轮 Agent M 被 stale guard 跳过：`signals stale: age=16937s exceeds max_age=7200s`，买入执行也被跳过。故该自然周期**没有验证到 M 三级分流**。
   - 护栏仍安全：skip output `success=0/dry_run=0/failed=0`。

2. **补充最小验证（Agent M + dry-run executor）**
   - 直接运行 Agent M 审查当前 8 个 signals：缓存命中 8/8，无 LLM 额外等待；日志 `[grade] approve 0, paper_probe 5, reject 3`。
   - `review_results.json`：`approved=0 / paper_probe=5 / rejected=3 / total=8`。
   - `approved_signals.json`：5 条，全部 `grade=paper_probe`；probe 仓位全部压到 `0.025`。
   - `runtime.reviews`：出现 `PAPER_PROBE`（当前分布 `PAPER_PROBE=5, REJECT=11`；含重建前/回填 reviews）。
   - 单独运行 signal_executor（`EXECUTOR_DRY_RUN=1` + mock pm-trader）：5 条 probe 全部 `status=dry_run`，`success=0 / dry_run=5 / failed=0`，execution grade 分布 `paper_probe=5`。
   - 无 traceback/sqlite/no such column/OperationalError/Exception；无残留项目进程。

判读：3d 的核心高风险项（三级分流、probe 压仓、执行护栏、学习隔离）主机补充验证通过；自然 orchestrator 周期的 M 步骤因 stale guard 未实际执行，若要求“严格全周期 M 审查通过”，需等/生成 fresh signals 后再跑一轮。
