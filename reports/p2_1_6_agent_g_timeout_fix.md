# P2-1.6 Agent G Timeout Fix Report

## 1. 修改文件

- `agents/agent_g.py`
- `reports/p2_1_6_agent_g_timeout_fix.md`

未修改 orchestrator、dry-run 安全逻辑、真实交易逻辑、RiskEngine、Agent M 或数据采集链路。

## 2. 超时根因

Agent G 在 dry-run 下已经生成 synthetic trade history，但 `analyze_trades()` 和 `analyze_rejections()` 仍继续进入 LLM 调用路径。

最近失败表现：

- `2026-05-15 15:28:07` Agent G 进入交易复盘。
- 已加载 10 笔 dry-run 合成交易历史。
- 随后卡在 `分析交易表现...`。
- orchestrator 于 `2026-05-15 15:30:07` 触发 `agent_g 执行超时`。

因此根因是：dry-run fallback 数据已存在，但分析阶段仍等待慢 LLM / 网络连接，导致 Agent G 被 orchestrator 的 120s timeout 杀掉。

## 3. fallback / timeout 处理方式

本轮只在 Agent G 内做最小修复：

- 新增 `LLM_TIMEOUT_SECONDS = 20`。
- 新增 `PM_HISTORY_TIMEOUT_SECONDS = 20`。
- dry-run 或 synthetic trades 场景下，`analyze_trades()` 直接使用 deterministic fallback summary。
- dry-run 场景下，`analyze_rejections()` 直接使用 deterministic fallback summary。
- 非 dry-run LLM 调用保留，但显式传入 `timeout=20`。
- 非 dry-run `pm-trader history` 调用 timeout 从 30s 收窄为 20s。

fallback summary 仍基于 dry-run mock trades / closed trades 统计生成，包括：

- closed trades 数量
- win rate
- total PnL
- best / worst markets
- rejected signal reason distribution

输出继续保留：

- `llm_available=false`
- `fallback_used=true`
- `dry_run=true`
- `synthetic=true`

## 4. 验证命令

```bash
PYTHONPYCACHEPREFIX=/private/tmp/pycache-agent-g venv/bin/python3 -m py_compile agents/agent_g.py
EXECUTOR_DRY_RUN=1 PM_TRADER_PATH=/tmp/mock_pm_trader.sh venv/bin/python3 main.py --mode once
```

## 5. 测试结果

`main.py --mode once` 结果：

- exit code: `0`
- Agent G: `2026-05-15 15:34:49` 开始，`2026-05-15 15:34:50` 成功完成
- 整体扫描周期完成：`2026-05-15 15:35:04`
- 最新扫描段落未出现 `ModuleNotFoundError`
- `execution_results.json` 保持 `success=0`

最新 Agent G 日志确认：

```text
[2026-05-15 15:34:50] [Agent G] 🔧 [DRY-RUN] 跳过 LLM 交易分析，使用 deterministic fallback
[2026-05-15 15:34:50] [Agent G] 🔧 [DRY-RUN] 跳过 LLM 拒绝分析，使用 deterministic fallback
[2026-05-15 15:34:50] [Agent G] ✅ 已保存学习报告到 /Users/libo/.hermes/polymarket_arbitrage/data/learning_report.json
[2026-05-15 15:34:50] [Agent G] ✅ 已更新 learning_knowledge_base.json → rejection_prompt_enhancement
[2026-05-15 15:34:50] [Agent G] ✅ 复盘完成
```

## 6. learning 文件刷新验证

修复前基线：

- `data/learning_report.json`: `May 15 15:02:37 2026`
- `data/learning_knowledge_base.json`: `May 15 15:02:37 2026`

修复后：

- `data/learning_report.json`: `May 15 15:34:50 2026`
- `data/learning_knowledge_base.json`: `May 15 15:34:50 2026`

JSON 标记：

```text
learning_report flags: {'llm_available': False, 'fallback_used': True, 'dry_run': True, 'synthetic': True}
kb flags: {'llm_available': False, 'fallback_used': True, 'dry_run': True, 'synthetic': True}
trade fallback: dry_run_deterministic_fallback
rejection fallback: dry_run_deterministic_fallback
```

## 7. dry-run 安全确认

- 命令使用 `EXECUTOR_DRY_RUN=1`。
- 命令使用 `PM_TRADER_PATH=/tmp/mock_pm_trader.sh`。
- Agent G 使用 synthetic trade history。
- 本轮未修改买入、卖出、真实交易执行逻辑。
- `execution_results.json` 中 `success=0`。

## 8. 结论

P2-1.6 验收通过。Agent G 在 dry-run 下不再等待慢 LLM，已稳定在 30 秒内完成，并且仍刷新 `learning_report.json` 与 `learning_knowledge_base.json`。
