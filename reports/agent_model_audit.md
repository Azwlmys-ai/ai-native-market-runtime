# Polymarket Multi-Agent 套利系统 — Agent 与模型模块全量审计

审计日期：2026-05-15  
范围：仅 `/Users/libo/.hermes/polymarket_arbitrage`  
方法：纯静态代码分析，未运行交易，未修改代码

---

## 一、启动入口与调用链路

```
main.py
  └─ Orchestrator.run_once()

0.  us_stocks_updater（数据采集器）
1.  agent_a          — 市场数据采集
2.  regime_detector  — 市场状态识别
3.  strategy_manager — 策略管理
4.  capital_adapter  — 资金分配
5.  agent_b          — 情报研究
6.  agent_k_v2       — 价值投资（规则引擎版）
7.  agent_d          — 无风险套利
8.  agent_e          — BTC 短期套利
9.  agent_f          — OKX 跨平台套利
10. agent_h          — 钱包跟单
11. agent_okx_funding— OKX 资金费率套利
12. agent_j          — 交叉验证
12.5 _consolidate_signals_for_review — 信号归一化合并
13. agent_m          — 风险审查
14. signal_executor  — 买入执行
15. agent_p          — 持仓管理
16. sell_executor    — 卖出执行
17. agent_g          — 交易复盘与经验学习
18. agent_i          — 系统监控保活
```

主入口仅引用 `orchestrator.py`。存在 `orchestrator_advanced.py` 和 `orchestrator_realtime.py` 两个备选版，但 `main.py` 只 import `orchestrator.Orchestrator`。

---

## 二、全量 Agent 审计表

| 模块名 | 类型 | 文件路径 | 当前状态 | 功能说明 | 修复建议 |
|--------|------|----------|----------|----------|----------|
| agent_a | Agent | agents/agent_a.py | ✅ 已接入 | 多源市场数据采集（PM/OKX/新闻/天气） | 运行正常 |
| agent_b | Agent | agents/agent_b.py | ✅ 已接入 | 情报研究，生成交易信号 | 实际文件名为 agent_b.py，但 `orchestrator.py` 调用 `agent_b`，文件存在且可运行 |
| agent_k_v2 | Agent | agents/agent_k_v2.py | ✅ 已接入 | 价值投资专员（规则引擎版），基于硬编码弱队数据库生成极端价格 NO 信号 | 运行正常（规则引擎，无 LLM 依赖） |
| agent_d | Agent | agents/agent_d.py | ✅ 已接入 | 无风险套利审查（YES+NO<$1.00） | 需要 LLM 调用 |
| agent_e | Agent | agents/agent_e.py | ✅ 已接入 | BTC 短期套利监控（PM vs OKX 实时价格） | 需要 LLM + OKX API |
| agent_f | Agent | agents/agent_f.py | ✅ 已接入 | OKX 跨平台套利监控 | 需要 LLM + OKX API |
| agent_h | Agent | agents/agent_h.py | ✅ 已接入 | 钱包跟单监控 | 需要 LLM |
| agent_okx_funding | Agent | agents/agent_okx_funding.py | ✅ 已接入 | OKX 资金费率套利 | 需要 LLM |
| agent_j | Agent | agents/agent_j.py | ✅ 已接入 | 交叉验证多个数据源 | 需要 LLM |
| agent_m | Agent | agents/agent_m.py | ✅ 已接入 | 风险审查员（弹性负载均衡 + 缓存） | 核心反对层 Agent，运行正常 |
| agent_p | Agent | agents/agent_p.py | ✅ 已接入 | 持仓管理监控，生成止盈止损信号 | 需要 PM trader CLI |
| agent_g | Agent | agents/agent_g.py | ✅ 已接入 | 交易复盘与经验学习 | 需要 LLM，可产出 learning_report.json |
| agent_i | Agent | agents/agent_i.py | ✅ 已接入 | 系统监控保活，自动重启崩溃 Agent | 需要 LLM |
| regime_detector | Agent | agents/regime_detector.py | ✅ 已接入 | 市场状态识别（牛/熊/震荡） | 需要 LLM |
| strategy_manager | Agent | agents/strategy_manager.py | ✅ 已接入 | 策略管理与动态调整 | 不需要 LLM |
| capital_adapter | Agent | agents/capital_adapter.py | ✅ 已接入 | 动态资金分配 | 需要 LLM |
| agent_b_enhanced | Agent | agents/agent_b_enhanced.py | ⚠️ 存在但未接入 | Agent B 增强版（集成学习到的策略规则） | 被 agent_b_enhanced_v2 取代，建议删除 |
| agent_b_enhanced_v2 | Agent | agents/agent_b_enhanced_v2.py | ⚠️ 存在但未接入 | Agent B 增强 v2（带数据支撑的情报研究） | 未被 orchestrator 引用，但 agent_b.py 的文件内容实际上也是 "Agent B Enhanced"。需确认 agent_b.py 是否实际是 v2 版本 |
| agent_b_optimized | Agent | agents/agent_b_optimized.py | ⚠️ 存在但未接入 | Agent B 优化版（降置信度阈值 80%→70%） | 实验变体，未被引用，建议删除 |
| agent_learning | Agent | agents/agent_learning.py | ⚠️ 存在但未接入 | 从历史交易中学习策略模式 | 独立脚本，手动运行，不在运行链路中 |
| agent_n | Agent | agents/agent_n.py | ⚠️ 存在但未接入 | 负载均衡器（反对层协调员），动态分配信号给多个 Agent M 实例 | Agent M 已内置弹性负载均衡（ThreadPoolExecutor），Agent N 成为冗余 |
| agent_codex | Agent | agents/agent_codex.py | ⚠️ 存在但未接入 | 部署前代码审查门禁 | 仅开发流程使用，非交易运行链路 |
| agent_cn_stocks | Agent | agents/agent_cn_stocks.py | ⚠️ 存在但未接入 | A 股套利分析（PM 中国市场 vs A 股） | 未被 orchestrator 调用 |
| agent_validator | Agent | agents/agent_validator.py | ⚠️ 存在但未接入 | 验证学习到的策略（测试集模拟） | 独立脚本，手动运行 |
| agent_vibe | Agent | agents/agent_vibe.py | ⚠️ 存在但未接入 | Vibe-Trading API 集成策略生成 | 未被 orchestrator 调用 |
| agent_stock_trader | Agent | agents/agent_stock_trader.py | ⚠️ 存在但未接入 | 美股/港股对冲交易 | 未被 orchestrator 调用 |
| agent_okx_trader | Agent | agents/agent_okx_trader.py | ⚠️ 存在但未接入 | OKX 加密货币对冲交易 | 未被 orchestrator 调用 |
| agent_p_stop_loss | Agent | agents/agent_p_stop_loss.py | ⚠️ 存在但未接入 | Agent P 止损增强版 | 变体版本，未被引用 |
| arbitrage_simulator | Agent | agents/arbitrage_simulator.py | ⚠️ 存在但未接入 | 模拟历史套利交易，验证策略收益率 | 回测工具，非运行时 |
| historical_arbitrage_miner | Agent | agents/historical_arbitrage_miner.py | ⚠️ 存在但未接入 | 从历史数据挖掘套利机会 | 回测工具，非运行时 |
| multi_platform_collector | Agent | agents/multi_platform_collector.py | ⚠️ 存在但未接入 | 多平台数据采集器 | 未被 orchestrator 调用 |
| us_stocks_updater | Collector | collectors/us_stocks_updater.py | ✅ 已接入 | 美股数据采集（Orchestrator 步骤 0） | 运行正常 |
| signal_executor | Executor | executors/signal_executor.py | ✅ 已接入 | 买入信号执行 | 通过 orchestrator subprocess 调用 |
| sell_executor | Executor | executors/sell_executor.py | ✅ 已接入 | 卖出信号执行 | 通过 orchestrator subprocess 调用 |
| cn_stocks_paper_trader | Executor | executors/cn_stocks_paper_trader.py | ⚠️ 存在但未接入 | A 股纸交易执行器 | 未被 orchestrator 调用 |
| okx_paper_trader | Executor | executors/okx_paper_trader.py | ⚠️ 存在但未接入 | OKX 纸交易执行器 | 未被 orchestrator 调用 |
| stock_paper_trader | Executor | executors/stock_paper_trader.py | ⚠️ 存在但未接入 | 美股纸交易执行器 | 未被 orchestrator 调用 |
| llm_helper | Tool | llm_helper.py | ✅ 已接入 | LLM 统一调用接口（Fallback 策略） | 被大多数 Agent 引用 |
| review_cache | Tool | review_cache.py | ✅ 已接入 | Agent M 审查缓存（MD5 哈希 + 24h TTL） | 被 Agent M 使用 |
| learning_knowledge_base | Tool | learning_knowledge_base.py | ⚠️ 存在但未接入 | 学习成果知识库类 | 硬编码路径 `/opt/data/polymarket_arbitrage`，与当前项目路径不一致。Agent M 直接读 `data/learning_knowledge_base.json` 而非使用此类 |

---

## 三、学习 / 训练 / 自适应 Agent 审计

| 模块 | 文件路径 | 是否真实接入运行链路 | 详情 |
|------|----------|---------------------|------|
| Agent G | agents/agent_g.py | ✅ 是 | Orchestrator 步骤 17，分析历史交易，产出 `learning_report.json` |
| Agent G 蒸馏版 | agent_g_distillation.py | ⚠️ 否 | 独立脚本，手动运行，不在 orchestrator 中 |
| Agent Learning | agents/agent_learning.py | ⚠️ 否 | 独立脚本，需手动运行 `python agents/agent_learning.py` |
| learning_knowledge_base.py | learning_knowledge_base.py | ⚠️ 否 | 类定义了但未被任何 Agent import（硬编码路径 `/opt/data/` 与当前项目不匹配） |
| learning_knowledge_base.json | data/learning_knowledge_base.json | ✅ 是 | 静态 JSON 文件，被 Agent M 的 `review_signal()` 读取作为 `rejection_prompt_enhancement` |
| train_agent_m_with_history.py | train_agent_m_with_history.py | ⚠️ 否 | 独立训练脚本，手动运行 |
| trigger_learning_from_failure.py | trigger_learning_from_failure.py | ⚠️ 否 | 独立触发脚本 |
| trigger_learning_historical_trades.py | trigger_learning_historical_trades.py | ⚠️ 否 | 独立触发脚本 |
| trigger_learning_okx_arbitrage.py | trigger_learning_okx_arbitrage.py | ⚠️ 否 | 独立触发脚本 |
| trigger_learning_round2.py | trigger_learning_round2.py | ⚠️ 否 | 独立触发脚本 |

**学习能力结论：**
- ⚠️ **部分存在但不完整**。Agent G 在运行链路中做复盘分析，但其产出（`learning_report.json`）是否真的被 Agent M 和 Agent B 消费是不完整的闭环：Agent M 只读了一个简单的 `learning_knowledge_base.json` 中的 `rejection_prompt_enhancement` 字段。
- **没有** memory vector store、没有 embedding-based retrieval、没有 online learning、没有 weight update。
- **没有** self-improvement 闭环（即学习→更新策略→验证→再学习）。
- 所有 `trigger_learning_*` 和 `train_agent_m_*` 脚本都是**手动触发的一次性分析工具**，不属于自动化运行链路。

---

## 四、金融 / 数学模型审计

| 模型 | 是否存在 | 文件位置 | 是否接入运行链路 | 详述 |
|------|---------|----------|-----------------|------|
| Markov Chain（马尔可夫链） | ❌ 不存在 | — | — | 全项目搜索无匹配 |
| HMM（隐马尔可夫模型） | ❌ 不存在 | — | — | 全项目搜索无匹配 |
| Monte Carlo（蒙特卡洛） | ❌ 不存在 | — | — | 全项目搜索无匹配 |
| Bayesian（贝叶斯） | ❌ 不存在 | — | — | 全项目搜索无匹配 |
| Regression（回归模型） | ❌ 不存在 | — | — | 无线性/逻辑/多项式回归模型 |
| Volatility（波动率） | ⚠️ 存在但非正式模型 | update_stock_data.py, fast_backtest.py, generate_polymarket_simulation.py | ⚠️ 仅数据生成/回测 | 使用简单 stddev 计算，非运行链路核心 |
| Correlation（相关性分析） | ⚠️ 存在但未接入 | analyze_market_correlation.py, cross_market_analyzer.py, validate_strategy_with_history.py | ⚠️ 独立脚本 | Pearson 相关系数计算，不在 orchestrator 中 |
| Factor Model（因子模型） | ❌ 不存在 | — | — | 全项目搜索无匹配 |
| Sentiment Model（情绪模型） | ❌ 不存在 | — | — | 全项目搜索无匹配（LLM 调用不构成 formal sentiment model） |
| VaR / Risk Model（风险价值） | ❌ 不存在 | — | — | 全项目搜索无匹配 |
| Z-Score | ⚠️ 存在但未接入 | validate_strategy_with_history.py, backtest_*.py | ⚠️ 仅回测 | 用于配对交易回测，不在运行链路 |

**数学/金融模型结论：**
- ❌ **所有正式数学模型均不存在或不接入运行链路**。
- 唯一相关的是简单的标准差波动率、Pearson 相关系数和 Z-Score，但这些都只在数据生成脚本和回测文件中使用，**不在 orchestrator 的实际交易流程中**。
- Agent M 的风险评估完全依赖 LLM 的文本推理，没有数值 VaR 或 risk model。

---

## 五、汇总

### 5.1 当前实际运行中的 Agent 列表（18 个步骤，16 个 Agent + 2 个 Executor + 1 个 Collector）

| # | 模块 | 类型 |
|---|------|------|
| 0 | us_stocks_updater | Collector |
| 1 | agent_a | Agent |
| 2 | regime_detector | Agent |
| 3 | strategy_manager | Agent |
| 4 | capital_adapter | Agent |
| 5 | agent_b | Agent |
| 6 | agent_k_v2 | Agent |
| 7 | agent_d | Agent |
| 8 | agent_e | Agent |
| 9 | agent_f | Agent |
| 10 | agent_h | Agent |
| 11 | agent_okx_funding | Agent |
| 12 | agent_j | Agent |
| 13 | agent_m | Agent |
| 14 | signal_executor | Executor |
| 15 | agent_p | Agent |
| 16 | sell_executor | Executor |
| 17 | agent_g | Agent |
| 18 | agent_i | Agent |

### 5.2 已存在但未接入的 Agent / 模型列表

| 模块 | 类型 | 原因 |
|------|------|------|
| agent_learning.py | Agent（学习） | 独立脚本 |
| agent_n.py | Agent（负载均衡） | Agent M 已内置，冗余 |
| agent_codex.py | Agent（代码审查） | 仅开发流程 |
| agent_cn_stocks.py | Agent（A 股套利） | 未集成 |
| agent_validator.py | Agent（策略验证） | 独立脚本 |
| agent_vibe.py | Agent（Vibe-Trading） | 未集成 |
| agent_stock_trader.py | Agent（股票交易） | 未集成 |
| agent_okx_trader.py | Agent（OKX 交易） | 未集成 |
| agent_p_stop_loss.py | Agent（止损变体） | 变体版本 |
| agent_b_enhanced.py | Agent（B 增强） | 被 v2 取代 |
| agent_b_enhanced_v2.py | Agent（B 增强 v2） | 未明确引用 |
| agent_b_optimized.py | Agent（B 优化） | 实验变体 |
| arbitrage_simulator.py | Agent（套利模拟） | 回测工具 |
| historical_arbitrage_miner.py | Agent（历史挖掘） | 回测工具 |
| multi_platform_collector.py | Agent（多平台采集） | 未集成 |
| learning_knowledge_base.py | Tool（知识库类） | 硬编码路径不匹配 |
| cn_stocks_paper_trader.py | Executor | 未集成 |
| okx_paper_trader.py | Executor | 未集成 |
| stock_paper_trader.py | Executor | 未集成 |
| 所有触发学习脚本 (x5) | Script | 手动工具 |
| train_agent_m_with_history.py | Script | 训练工具 |
| analyze_market_correlation.py | Analysis | 独立分析脚本 |
| cross_market_analyzer.py | Analysis | 独立分析脚本 |
| agent_g_distillation.py | Agent（蒸馏学习） | 独立脚本 |

### 5.3 已废弃或疑似失效的模块

| 模块 | 原因 |
|------|------|
| agent_b_enhanced.py | 被 agent_b_enhanced_v2 取代，且 orchestrator 只调用 agent_b.py |
| agent_b_optimized.py | 实验变体，无引用 |
| agent_n.py | Agent M 已内置 ThreadPoolExecutor 弹性负载均衡，Agent N 功能冗余 |
| learning_knowledge_base.py | 硬编码路径 `/opt/data/` 与当前项目路径 `/Users/libo/.hermes/polymarket_arbitrage` 不一致，且未被任何模块 import |
| orchestrator_advanced.py | main.py 不引用此文件 |
| orchestrator_realtime.py | main.py 不引用此文件 |
| agent_p_stop_loss.py | agent_p.py 的变体，未被引用 |

### 5.4 学习能力是否真实存在

**结论：⚠️ 部分存在，但不构成完整的学习闭环。**

- Agent G（步骤 17）在每次扫描周期运行，可产出 `learning_report.json`
- Agent M 在审查时读取 `data/learning_knowledge_base.json` 中的 `rejection_prompt_enhancement` 字段
- 但两者之间没有自动化连接：Agent G 产出的是 `learning_report.json`，而 Agent M 读的是 `learning_knowledge_base.json`——这两个是不同的文件
- 没有 embedding、没有 vector DB、没有 online weight update
- 所有 `trigger_learning_*` 脚本都是手动触发的一次性分析工具

### 5.5 马尔可夫链等数学模型是否真实存在并接入

**结论：❌ 所有正式数学模型均不存在。**

- Markov Chain：不存在
- HMM：不存在
- Monte Carlo：不存在
- Bayesian：不存在
- Regression：不存在
- Factor Model：不存在
- Sentiment Model：不存在
- VaR：不存在
- 仅有简单 stddev volatility、Pearson correlation、Z-score，但仅限于数据生成/回测脚本，不在运行链路

### 5.6 下一阶段建议

#### 该保留（已在运行链路中）
- agent_a, agent_b, agent_k_v2, agent_d, agent_e, agent_f, agent_h, agent_okx_funding, agent_j, agent_m, agent_p, agent_g, agent_i
- regime_detector, strategy_manager, capital_adapter
- signal_executor, sell_executor, us_stocks_updater
- llm_helper, review_cache
- _paths.py

#### 该接入（有价值但未在运行链路）
- **agent_okx_trader**：如果要做 OKX 对冲交易，应接入
- **agent_cn_stocks**：如果要做 A 股-PM 套利，应接入
- **agent_validator**：建议改造为 Agent M 的回测验证环节，而非独立脚本
- **cross_market_analyzer / analyze_market_correlation**：建议改造为运行链路中的一个步骤（Agent X），在下单前检查跨市场相关性

#### 该删除（冗余/废弃/实验残留）
- agent_b_enhanced.py — 被 v2 取代
- agent_b_optimized.py — 实验变体
- agent_n.py — 功能已被 Agent M 内置
- agent_p_stop_loss.py — 变体版本
- learning_knowledge_base.py — 硬编码路径不匹配，且未被引用
- orchestrator_advanced.py / orchestrator_realtime.py — 非主入口引用的备选版本
- agent_b_enhanced_v2.py — 如果当前 agent_b.py 内容实际上已是最新版本

#### 关于学习能力增强
- 建立 Agent G 产出 → Agent M/B 消费的闭环（统一文件名和数据格式）
- 考虑引入简单的统计模型（如 logistic regression 对信号进行评分）
- 为 Agent M 增加真正的历史胜率统计而非纯 LLM 判断

#### 关于数学模型
- 当前系统为纯 LLM 多 Agent 架构，没有数值金融模型
- 如需提升风控质量，建议在 Agent M 中增加：
  - VaR 计算（基于历史持仓 PnL）
  - 简单的相关性矩阵（限制同向敞口）
  - Kelly Criterion 仓位优化