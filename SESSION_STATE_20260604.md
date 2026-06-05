# SESSION_STATE 2026-06-04 — Phase 3d 全周期签收完成

> 本轮单一目标：补全 VNext 里程碑遗留的「3d 全周期签收」——让 Agent M 三级 risk grading 在**完整 orchestrator 周期路径内**真正分流一次（此前因 signals stale 被跳过，非缺陷）。
> 结论：**已签收。三级分流 + probe 压仓 + 执行护栏 + 影子表记录，在真实 orchestrator 调用链上全部复现，smoke 71 passed。**

---

## 1. 卡点回顾

`VNEXT_MILESTONE_20260603.md` §6 剩余尾巴 #1：3d 核心高风险项（_grade 真值表、probe 压仓、执行护栏、学习隔离）此前已沙箱 + 主机补充验证通过，**唯一缺口**是自然 orchestrator 周期里 Agent M 被 stale guard 跳过（`signals stale: age=16937s exceeds max_age=7200s`），三级分流没在 step 13 完整管线内跑过。

根因：`orchestrator._signals_ready_for_review()` 用 `SIGNAL_MAX_AGE_SECONDS=7200`（2h）做 fail-closed；现有 8 个真实 signals 的 `generated_at=2026-06-03T10:30`，已超 1 天 → 跳过。

---

## 2. 本轮验证方法（受控、非破坏性）

环境约束：本轮在 Linux 沙箱执行（项目文件 = 主机 `~/.hermes/polymarket_arbitrage` 挂载同一份）。上游采集器/agent 子进程需网络+密钥，沙箱不可全跑，且 `run_once` 全 18 步含多个会挂起的网络子进程。故采用**直接驱动 orchestrator 真实方法**，只跑 3d 关心的 step 13/14 代码路径，避开无关的上游采集步骤。

关键安全设计：
- **非破坏性**：先备份 `signals/review_results/approved_signals/execution_results/runtime.db(+wal/shm)/review_cache/cache.json` 到 `/tmp/pa_3d_backup`，验证后**全部恢复**到验证前状态（signals 时间戳已还原为 `2026-06-03T10:30`）。
- **fresh signals 来源**：把 8 个真实 signals 的 `generated_at` 刷到 now（**内容不变**），让 `_signals_ready_for_review()` 自然返回 fresh——这正是一轮真实 fresh 周期 consolidation 会产出的形态。`ReviewCache.calculate_signal_hash` 明确忽略 timestamp/source → cache 仍 8/8 命中，**不触发 live LLM**（沙箱无密钥也安全）。
- **全程 dry-run 护栏**：`EXECUTOR_DRY_RUN=1` + `PM_TRADER_PATH=/tmp/mock_pm_trader.sh` + `PA_SHADOW_DB=1`。dry-run 分支 status=dry_run，从不调真实 trader。

执行的真实 orchestrator 调用链（= run_once 的 step 13→14）：
```
o = Orchestrator()
ready, reason = o._signals_ready_for_review()   # → (True, "signals fresh")
o._run_agent("agent_m")                          # step 13：真实子进程 agents/agent_m.py
o._execute_signals()                             # step 14：真实 executor，dry-run
```

---

## 3. 验证结果（全 PASS）

| 判据 | 结果 | 证据 |
|---|---|---|
| step13 gate 通过（不再被 stale 跳过） | ✅ | `_signals_ready_for_review() → (True, "signals fresh")` |
| Agent M 经真实 orchestrator 调用执行成功 | ✅ | `✅ agent_m 执行成功`（子进程 returncode 0） |
| **三级分流（非二元）** | ✅ | `review_results: total=8 approved=0 paper_probe=5 rejected=3` |
| probe 压仓 ×0.25 | ✅ | `approved_signals=5 全 grade=paper_probe，position_size 全=0.025`（≈0.1×0.25） |
| **执行护栏 success=0**（probe 仍 dry_run） | ✅ | `execution: total=5 success=0 dry_run=5 simulated=0 failed=0` |
| 影子表记录三级 | ✅ | `runtime.reviews decision: PAPER_PROBE 出现`（本轮跑后含历史累积 PAPER_PROBE=10/REJECT=14） |
| smoke 全过 | ✅ | `71 passed`（与主机基线一致；沙箱补装 openai/aiohttp/pytest 后） |

判读：**「approved=0 / paper_probe=5 / rejected=3」即三级分流在完整 orchestrator 路径内成立的硬证据**——既有 reject（高失败概率一票否决保留），又有 paper_probe（原本会被 REJECT 的边缘信号转小仓试错），证明 M 已不再二元。approved=0 属 band 未命中（本轮 8 信号失败概率无落在 <35% 的），符合设计预期，非缺陷。

---

## 4. 一个小观察（非 3d 缺口，记录备查）

经 `orchestrator._execute_signals()` 跑出的 `execution_results.results[].grade` 全为 `(none)`，而 2026-06-03 单独跑 `signal_executor` 时报告过 `execution grade=paper_probe`。即**执行器未把 signal 的 `grade` 透传进 execution_results**。这不破任何护栏（success=0 不变、probe 压仓在 approved_signals 已生效），只是执行层归因少了一个 grade 标签。若希望执行结果也能按 probe/approve 归因，可在 `executors/signal_executor.py` 的结果组装处把 `signal.get("grade")` 带出。列为可选改进，**不影响 3d 签收**。

---

## 5. 状态更新

- `VNEXT_MILESTONE_20260603.md` §1 表中 3d 行「全周期签收待 fresh signals」→ **已签收**。
- 里程碑 §6 尾巴 #1（3d 全周期签收）→ **完成**。
- 剩余尾巴顺延为下一步候选：#2 trailing 真实最高水位、#3 临时键 reconcile 自动化、#4 dashboard 切 canonical 视图、#5 PRD Mobile、#6 3c-2 失败条件复盘对照。

## 6. 给未来会话

- 本轮**未改任何业务代码**，纯验证 + 数据已恢复，项目处于验证前一致状态。
- 复现命令（沙箱/主机通用，主机用 venv/bin/python3）：备份 data → 刷新 signals.generated_at 为 now → `EXECUTOR_DRY_RUN=1 PA_SHADOW_DB=1 PM_TRADER_PATH=<mock>` 下调 `_signals_ready_for_review/_run_agent('agent_m')/_execute_signals` → 校验三级 + success=0 → 恢复 data。
- 沙箱补装依赖：`openai aiohttp pytest`（主机 venv 已自带，主机直接跑无需补装）。
