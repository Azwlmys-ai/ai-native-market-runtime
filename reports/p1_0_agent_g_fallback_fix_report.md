# P1-0 Agent G LLM Fallback Fix Report

时间：2026-05-15 12:47 Asia/Shanghai

## 修改文件

- `agents/agent_g.py`
- `reports/p1_0_agent_g_fallback_fix_report.md`

## Agent G 原因分析

P0 dry-run 中 Agent G 已能生成合成交易历史，但交易复盘仍依赖 LLM 返回 JSON。LLM connection error、timeout、API error 或当前 venv 中 `openai` 包不可导入时，原逻辑会让 `analyze_trades()` / `analyze_rejections()` 返回 `None`，最终 `save_learning_report()` 不执行，因此不会刷新：

- `data/learning_report.json`
- `data/learning_knowledge_base.json`

本轮未修改 orchestrator 主流程、dry-run 安全逻辑、真实交易逻辑、risk engine，也未新增 Agent 或模型。

## Fallback 逻辑说明

Agent G 现在在 LLM 不可用时使用 deterministic rule-based fallback：

- `llm_helper` 导入失败时，Agent G 仍可启动，并在分析阶段进入 fallback。
- 交易 fallback 基于 dry-run mock trades / closed trades 统计生成：
  - closed trades 数量
  - winning / losing trades
  - win rate
  - total PnL
  - best / worst markets by closed PnL
- 拒绝信号 fallback 基于 rejected signals 的拒绝原因分布生成。
- 输出显式标记：
  - `llm_available=false`
  - `fallback_used=true`
  - `dry_run=true`
  - `synthetic=true`

## learning_report.json 更新验证

命令：

```bash
stat -f '%Sm %m %N' data/learning_report.json
```

结果：

```text
May 15 12:47:37 2026 1778820457 data/learning_report.json
```

字段验证：

```text
report flags {'llm_available': False, 'fallback_used': True, 'dry_run': True, 'synthetic': True}
trade flags {'llm_available': False, 'fallback_used': True, 'dry_run': True, 'synthetic': True}
```

## learning_knowledge_base.json 更新验证

命令：

```bash
stat -f '%Sm %m %N' data/learning_knowledge_base.json
```

结果：

```text
May 15 12:47:37 2026 1778820457 data/learning_knowledge_base.json
```

字段验证：

```text
kb flags {'llm_available': False, 'fallback_used': True, 'dry_run': True, 'synthetic': True}
kb summary keys ['dry_run', 'fallback_used', 'llm_available', 'rejection_key_insights', 'rejection_stats', 'synthetic', 'timestamp', 'trade_key_insights', 'trade_stats']
```

## dry-run 安全确认

验收命令：

```bash
EXECUTOR_DRY_RUN=1 PM_TRADER_PATH=/tmp/mock_pm_trader.sh venv/bin/python3 main.py --mode once
```

结果：

```text
exit code 0
execution success 0 results []
```

`data/execution_results.json` 验证：

```text
execution success 0 results []
```

`scripts/monitor_2h.sh` 验证：

```text
TOTAL_CYCLES=8
```

## 测试命令和结果

```bash
env PYTHONPYCACHEPREFIX=/private/tmp/pycache-agent-g venv/bin/python3 -m py_compile agents/agent_g.py
```

结果：exit code 0

```bash
venv/bin/python3 -m pytest tests/test_smoke.py -k agent_g -q
```

结果：

```text
1 passed, 65 deselected
```

```bash
EXECUTOR_DRY_RUN=1 PM_TRADER_PATH=/tmp/mock_pm_trader.sh venv/bin/python3 main.py --mode once
```

结果：exit code 0；Agent G 执行成功并刷新 learning 文件。
