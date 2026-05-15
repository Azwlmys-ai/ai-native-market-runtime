# Polymarket Arbitrage 项目 — Agent & Model 全面盘点

**审计日期**：2026-05-15  
**审计范围**：仅 `/Users/libo/.hermes/polymarket_arbitrage`  
**审计方式**：纯静态代码分析，不运行、不修改、不下单  
**参考入口**：`main.py` → `orchestrator.py` → `run_once()` (18 步流水线)

---

## 一、Orchestrator 当前运行流水线

`orchestrator.py` `run_once()` 定义了 18 步执行流程：

| 步骤 | 调用模块 | 类型 | 说明 |
|------|----------|------|------|
| 0 | `us_stocks_updater` | Collector | 美股数据采集 |
| 1 | `agent_a` | Agent | Polymarket 数据采集 |
| 2 | `regime_detector` | Agent | 市场状态识别 |
| 3 | `strategy_manager` | Agent | 策略管理 |
| 4 | `capital_adapter` | Agent | 资金分配 |
| 5 | `agent_b` | Agent | 情报研究 |
| 6 | `agent_k_v2` | Agent | 价值投资 |
| 7 | `agent_d` | Agent | 无风险套利 |
| 8 | `agent_e` | Agent | BTC 套利 |
| 9 | `agent_f` | Agent | 跨平台套利 |
| 10 | `agent_h` | Agent | 钱包跟单 |
| 11 | `agent_okx_funding` | Agent | OKX 资金费率套利 |
| 12 | `agent_j` | Agent | 交叉验证 |
| 12.5 | `_consolidate_signals_for_review()` | Orchestrator 内部 | 汇总信号到 signals.json |
| 13 | `agent_m` | Agent | 风险审查（双模型验证） |
| 14 | `signal_executor.py` | Executor | 买入执行 |
| 15 | `agent_p` | Agent | 持仓管理 |
| 16 | `sell_executor.py` | Executor | 卖出执行 |
| 17 | `agent_g` | Agent | 交易复盘（学习） |
| 18 | `agent_i` | Agent | 系统监控 |

---

## 二、所有 Agent 完整盘点

### ✅ 已接入运行流水的 Agent（18 个）

| Agent | 文件路径 | 层级 | 功能说明 | 状态 |
|-------|----------|------|----------|------|
| Agent A | `agents/agent_a.py` | 数据层 | Polymarket 市场数据采集 | ✅ 运行中 |
| Regime Detector | `agents/regime_detector.py` | 分析层 | 市场状态识别（regime detection） | ✅ 运行中 |
| Strategy Manager | `agents/strategy_manager.py` | 决策层 | 策略参数管理与选择 | ✅ 运行中 |
| Capital Adapter | `agents/capital_adapter.py` | 风控层 | 资金动态分配 | ✅ 运行中 |
| Agent B | `agents/agent_b.py` | 决策层 | 情报研究与信号生成 | ✅ 运行中 |
| Agent K v2 | `agents/agent_k_v2.py` | 决策层 | 价值投资（基本面分析） | ✅ 运行中 |
| Agent D | `agents/agent_d.py` | 决策层 | 无风险套利（arbitrage） | ✅ 运行中 |
| Agent E | `agents/agent_e.py` | 决策层 | BTC 专项套利 | ✅ 运行中 |
| Agent F | `agents/agent_f.py` | 决策层 | 跨平台套利（多 DEX/CEX） | ✅ 运行中 |
| Agent H | `agents/agent_h.py` | 决策层 | 钱包地址跟单 | ✅ 运行中 |
| Agent OKX Funding | `agents/agent_okx_funding.py` | 决策层 | OKX 永续合约资金费率套利 | ✅ 运行中 |
| Agent J | `agents/agent_j.py` | 验证层 | 多 Agent 信号交叉验证 | ✅ 运行中 |
| Agent M | `agents/agent_m.py` | 风控层 | 风险审查（双模型 LLM 验证） | ✅ 运行中 |
| Agent P | `agents/agent_p.py` | 执行层 | 持仓管理与止盈止损 | ✅ 运行中 |
| Agent G | `agents/agent_g.py` | 学习层 | 交易复盘、胜败分析、经验积累 | ✅ 运行中 |
| Agent I | `agents/agent_i.py` | 监控层 | 系统健康监控与告警 | ✅ 运行中 |
| US Stocks Updater | `collectors/us_stocks_updater.py` | 数据层 | 美股行情更新 | ✅ 运行中 |
| Signal Executor | `signal_executor.py` | 执行层 | 买入信号执行 | ✅ 运行中 |
| Sell Executor | `sell_executor.py` | 执行层 | 卖出信号执行 | ✅ 运行中 |

### ⚠️ 存在但未接入的 Agent（14 个）

| Agent | 文件路径 | 功能说明 | 状态 | 原因 |
|-------|----------|----------|------|------|
| Agent B Enhanced | `agents/agent_b_enhanced.py` | Agent B 增强版 | ⚠️ 未接入 | orchestrator 调用 agent_b.py，未调用 enhanced 版本 |
| Agent B Enhanced v2 | `agents/agent_b_enhanced_v2.py` | Agent B 增强 v2 | ⚠️ 未接入 | 同上 |
| Agent B Optimized | `agents/agent_b_optimized.py` | Agent B 优化版 | ⚠️ 未接入 | 同上 |
| Agent CN Stocks | `agents/agent_cn_stocks.py` | A股/港股分析 | ⚠️ 未接入 | orchestrator 无此步骤 |
| Agent Codex | `agents/agent_codex.py` | Codex 代码审查 | ⚠️ 未接入 | orchestrator 无此步骤 |
| Agent Learning | `agents/agent_learning.py` | 历史交易学习（LLM 特征提取） | ⚠️ 未接入 | 不在 orchestrator，独立脚本 |
| Agent N | `agents/agent_n.py` | 反对层负载均衡器 | ⚠️ 未接入 | orchestrator 直接调 agent_m，未用负载均衡 |
| Agent OKX Trader | `agents/agent_okx_trader.py` | OKX 现货/合约交易 | ⚠️ 未接入 | orchestrator 无此步骤 |
| Agent P Stop-Loss | `agents/agent_p_stop_loss.py` | Agent P 的止损增强版 | ⚠️ 未接入 | orchestrator 调 agent_p.py |
| Agent Stock Trader | `agents/agent_stock_trader.py` | 美股/港股对冲交易 | ⚠️ 未接入 | orchestrator 无此步骤 |
| Agent Validator | `agents/agent_validator.py` | 在测试集上验证学习策略 | ⚠️ 未接入 | 离线验证脚本 |
| Agent Vibe | `agents/agent_vibe.py` | 集成 Vibe-Trading 本地 API | ⚠️ 未接入 | orchestrator 无此步骤 |
| Historical Arbitrage Miner | `agents/historical_arbitrage_miner.py` | 历史套利机会挖掘 | ⚠️ 未接入 | 独立分析工具 |
| Multi-Platform Collector | `agents/multi_platform_collector.py` | 多平台数据采集 | ⚠️ 未接入 | orchestrator 用 collector 目录下的 |
| Arbitrage Simulator | `agents/arbitrage_simulator.py` | 套利场景模拟 | ⚠️ 未接入 | 仿真工具 |

---

## 三、学习 / 训练 / 自适应能力盘点

### 是否真实存在学习能力？ ✅ 存在，但有限

| 模块 | 文件路径 | 能力描述 | 是否接入 | 说明 |
|------|----------|----------|----------|------|
| **Agent G（已接入）** | `agents/agent_g.py` | 复盘分析：从交易历史和拒绝信号中提取成功/失败模式，调用 LLM 分析，输出 learning_report.json + learning_history.json | ✅ 已接入（步骤 17） | 真正的在线学习模块，每次扫描周期后运行 |
| **LearningKnowledgeBase** | `learning_knowledge_base.py` | 静态知识库：市场白名单、定价规则、执行规则、拒绝标准、因果验证规则 | ⚠️ 未接入 orchestrator | 未被任何 agent 直接 import，独立脚本 |
| **Agent Learning** | `agents/agent_learning.py` | 离线批量学习：加载 train_trades.json，分析市场类型/价格区间/滑点，调用 LLM 生成 learned_rules.json | ⚠️ 未接入 | 需手动运行，依赖 data/train_trades.json |
| **Agent Validator** | `agents/agent_validator.py` | 离线验证：加载 test_trades.json + learned_rules.json，验证策略在测试集表现 | ⚠️ 未接入 | 离线验证脚本 |
| **prepare_training_data.py** | `scripts/prepare_training_data.py` | 训练数据准备 | ⚠️ 未接入 | 工具脚本 |
| **train_agent_m_with_history.py** | 根目录 | 用历史数据训练 Agent M | ⚠️ 未接入 | 独立训练脚本 |
| **train_and_test_with_api_data.py** | 根目录 | 用 API 真实数据训练 | ⚠️ 未接入 | 独立训练脚本 |
| **trigger_learning_from_failure.py** | 根目录 | 从失败中触发学习 | ⚠️ 未接入 | 独立触发脚本 |
| **trigger_learning_historical_trades.py** | 根目录 | 从历史交易触发学习 | ⚠️ 未接入 | 独立触发脚本 |
| **trigger_learning_okx_arbitrage.py** | 根目录 | 从 OKX 套利失败触发学习 | ⚠️ 未接入 | 独立触发脚本 |
| **trigger_learning_round2.py** | 根目录 | 第二轮学习触发 | ⚠️ 未接入 | 独立触发脚本 |
| **agent_g_distillation.py** | 根目录 | Agent G 蒸馏训练 | ⚠️ 未接入 | 独立训练脚本 |
| **Memory/Feedback/Self-Improve 机制** | — | ❌ 不存在 | — | 无持久化 memory vector、无 RL-based self-improve、无在线 feedback loop |

### 学习能力结论

- ✅ **Agent G** 提供了基础的复盘学习能力（已接入运行流水，步骤 17）
- ✅ `learning_knowledge_base.py` 提供了结构化的知识蒸馏框架
- ⚠️ 但 knowledge base **未被任何 agent import**，是死角
- ⚠️ 多个 trigger_learning_*.py / train_*.py 独立存在，都不在运行流水中
- ❌ 没有真正的 **持续自适应学习**（无 feedback → retrain → deploy 闭环）
- ❌ 没有 RL / 在线梯度更新 / 参数自动调优

---

## 四、金融 / 数学模型盘点

| 模型类型 | 是否存在 | 文件位置 | 接入状态 | 说明 |
|----------|----------|----------|----------|------|
| **Markov Chain** | ❌ 不存在 | — | — | 全仓搜索无结果 |
| **Hidden Markov Model (HMM)** | ❌ 不存在 | — | — | 全仓搜索无结果 |
| **Monte Carlo** | ❌ 不存在 | — | — | 全仓搜索无结果 |
| **Bayesian** | ❌ 不存在 | — | — | 全仓搜索无结果 |
| **Regression** | ❌ 不存在 | — | — | 无线性/逻辑/多项式回归模块 |
| **VaR (Value at Risk)** | ❌ 不存在 | — | — | 全仓搜索无结果 |
| **Factor Model** | ❌ 不存在 | — | — | 全仓搜索无结果 |
| **Sentiment Model** | ❌ 不存在 | — | — | 全仓搜索无结果 |
| **Correlation Analysis** | ✅ 存在 | `analyze_market_correlation.py` | ❌ 未接入 | 相关性矩阵计算（np.corrcoef），独立脚本 |
| **Cross-Market Correlation** | ✅ 存在 | `cross_market_analyzer.py` | ❌ 未接入 | 跨市场定性关联分析，独立脚本 |
| **Z-Score Analysis** | ✅ 存在 | `analyze_zscore.py` | ❌ 未接入 | 配对价差 Z-Score 分析，独立脚本 |
| **Risk Analysis** | ✅ 存在 | `analyze_risk_and_optimize.py` | ❌ 未接入 | 简单胜负率/PnL 统计分析，独立脚本 |
| **Volatility** | ❌ 不存在 | — | — | 无 GARCH/EWMA/realized volatility 模块 |
| **Regime Detection** | ⚠️ 概念存在 | `agents/regime_detector.py` | ✅ 已接入（步骤 2） | 但 regime_detector 用 LLM 判断状态，非定量模型（HMM/GARCH） |

### 数学模型结论

- ❌ **关键数学/金融模型全部缺失**：无 Markov、HMM、Monte Carlo、VaR、Bayesian
- ⚠️ 仅有的**统计工具**（相关性、Z-Score、风险分析）都是**独立脚本**，未接入运行流水
- ⚠️ `regime_detector.py` 使用 LLM 做市场状态识别，而非定量模型（HMM/GARCH）
- ❌ 无任何概率模型（Bayesian inference）、无风险量化（VaR/CVaR）、无因子定价模型

---

## 五、综合汇总表

| 模块名 | 类型 | 文件路径 | 状态 | 功能说明 | 修复建议 |
|--------|------|----------|------|----------|----------|
| Agent A | Agent | `agents/agent_a.py` | ✅ | 数据采集 | — |
| Agent B | Agent | `agents/agent_b.py` | ✅ | 情报研究 | — |
| Agent B Enhanced | Agent | `agents/agent_b_enhanced.py` | ⚠️ 未接入 | B 增强版 | 合并进 agent_b 或删除 |
| Agent B Enhanced v2 | Agent | `agents/agent_b_enhanced_v2.py` | ⚠️ 未接入 | B 增强 v2 | 合并进 agent_b 或删除 |
| Agent B Optimized | Agent | `agents/agent_b_optimized.py` | ⚠️ 未接入 | B 优化版 | 合并进 agent_b 或删除 |
| Agent CN Stocks | Agent | `agents/agent_cn_stocks.py` | ⚠️ 未接入 | A股分析 | 确认需求后接入或删除 |
| Agent Codex | Agent | `agents/agent_codex.py` | ⚠️ 未接入 | 代码审查 | 离线工具，保留 |
| Agent D | Agent | `agents/agent_d.py` | ✅ | 套利 | — |
| Agent E | Agent | `agents/agent_e.py` | ✅ | BTC 套利 | — |
| Agent F | Agent | `agents/agent_f.py` | ✅ | 跨平台 | — |
| Agent G | Agent | `agents/agent_g.py` | ✅ | 复盘学习 | 把 knowledge_base 集成进去 |
| Agent H | Agent | `agents/agent_h.py` | ✅ | 钱包跟单 | — |
| Agent I | Agent | `agents/agent_i.py` | ✅ | 监控 | — |
| Agent J | Agent | `agents/agent_j.py` | ✅ | 交叉验证 | — |
| Agent K v2 | Agent | `agents/agent_k_v2.py` | ✅ | 价值投资 | — |
| Agent Learning | Agent | `agents/agent_learning.py` | ⚠️ 未接入 | 批量学习 | 集成到 Agent G |
| Agent M | Agent | `agents/agent_m.py` | ✅ | 风险审查 | — |
| Agent N | Agent | `agents/agent_n.py` | ⚠️ 未接入 | 负载均衡 | 如果信号量少不需要，可删 |
| Agent OKX Funding | Agent | `agents/agent_okx_funding.py` | ✅ | 资金费率 | — |
| Agent OKX Trader | Agent | `agents/agent_okx_trader.py` | ⚠️ 未接入 | OKX 交易 | 确认需求后接入或删除 |
| Agent P | Agent | `agents/agent_p.py` | ✅ | 持仓管理 | — |
| Agent P Stop-Loss | Agent | `agents/agent_p_stop_loss.py` | ⚠️ 未接入 | 止损增强 | 合并进 agent_p 或删除 |
| Agent Stock Trader | Agent | `agents/agent_stock_trader.py` | ⚠️ 未接入 | 股票对冲 | 确认需求后接入或删除 |
| Agent Validator | Agent | `agents/agent_validator.py` | ⚠️ 未接入 | 策略验证 | 离线保留 |
| Agent Vibe | Agent | `agents/agent_vibe.py` | ⚠️ 未接入 | Vibe-Trading | 确认 API 可用后接入或删除 |
| Regime Detector | Agent | `agents/regime_detector.py` | ✅ | 市场状态 | — |
| Strategy Manager | Agent | `agents/strategy_manager.py` | ✅ | 策略管理 | — |
| Capital Adapter | Agent | `agents/capital_adapter.py` | ✅ | 资金分配 | — |
| Arbitrage Simulator | Agent | `agents/arbitrage_simulator.py` | ⚠️ 未接入 | 仿真 | 离线保留 |
| Historical Arbitrage Miner | Agent | `agents/historical_arbitrage_miner.py` | ⚠️ 未接入 | 历史挖掘 | 离线保留 |
| Multi-Platform Collector | Agent | `agents/multi_platform_collector.py` | ⚠️ 未接入 | 多平台采集 | 确认需求后接入或删除 |
| Learning Knowledge Base | Tool | `learning_knowledge_base.py` | ⚠️ 未接入 | 知识库 | 被 Agent G/B/M 引用 |
| market_correlation analyzer | Tool | `analyze_market_correlation.py` | ⚠️ 未接入 | 相关性分析 | 离线保留或集成到 decision agent |
| cross_market_analyzer | Tool | `cross_market_analyzer.py` | ⚠️ 未接入 | 跨市场分析 | 离线保留 |
| zscore analyzer | Tool | `analyze_zscore.py` | ⚠️ 未接入 | Z-Score | 离线保留 |
| risk optimizer | Tool | `analyze_risk_and_optimize.py` | ⚠️ 未接入 | 风险优化 | 离线保留 |
| Signal Executor | Executor | `signal_executor.py` | ✅ | 买入执行 | — |
| Sell Executor | Executor | `sell_executor.py` | ✅ | 卖出执行 | — |

---

## 六、最终结论

### 1. 当前实际运行中的 Agent 列表（18 个）
`agent_a`, `regime_detector`, `strategy_manager`, `capital_adapter`, `agent_b`, `agent_k_v2`, `agent_d`, `agent_e`, `agent_f`, `agent_h`, `agent_okx_funding`, `agent_j`, `agent_m`, `agent_p`, `agent_g`, `agent_i`, `us_stocks_updater`, `signal_executor`, `sell_executor`

### 2. 已存在但未接入的 Agent / 模型（14 个 Agent + 5 个工具脚本）
Agent: `agent_b_enhanced`, `agent_b_enhanced_v2`, `agent_b_optimized`, `agent_cn_stocks`, `agent_codex`, `agent_learning`, `agent_n`, `agent_okx_trader`, `agent_p_stop_loss`, `agent_stock_trader`, `agent_validator`, `agent_vibe`, `historical_arbitrage_miner`, `multi_platform_collector`, `arbitrage_simulator`

工具: `learning_knowledge_base.py`, `analyze_market_correlation.py`, `cross_market_analyzer.py`, `analyze_zscore.py`, `analyze_risk_and_optimize.py`

### 3. 已废弃或疑似失效的模块
- `agent_b_enhanced.py` / `agent_b_enhanced_v2.py` / `agent_b_optimized.py` — 三重版本堆砌
- `agent_p_stop_loss.py` — agent_p 的旧版/分支版
- `agent_n.py` — 负载均衡器在当前信号量下无必要
- 根目录大量 `train_*.py` / `trigger_learning_*.py` — 一次性的独立脚本，杂乱

### 4. 学习能力是否真实存在
**部分存在**。Agent G 提供了复盘学习（✅ 已接入），但 knowledge_base 未集成，无持续自适应闭环。

### 5. 马尔可夫链等数学模型是否真实存在并接入
**全部不存在**。Markov Chain / HMM / Monte Carlo / Bayesian / VaR / Factor Model / Sentiment Model / Volatility Model — 均未找到任何实现代码。现有的相关性/Z-Score/风险分析只是独立脚本，未接入流水。

### 6. 下一阶段建议

**保留并继续维护**：
- 所有 18 个已接入 Agent（流水线完整）

**接入**：
- `learning_knowledge_base.py` → 集成到 Agent G（复盘后自动更新知识库）、Agent B（注入市场白名单）、Agent M（注入拒绝标准）
- `agent_stock_trader.py` → 如果股票对冲策略有效，接入 orchestrator
- `agent_vibe.py` → 如果本地 Vibe-Trading API 可用，接入作为补充信号源

**删除或归档**：
- `agent_b_enhanced.py` / `agent_b_enhanced_v2.py` / `agent_b_optimized.py` — 合并最优特性到 agent_b 后删除
- `agent_p_stop_loss.py` — 合并到 agent_p 后删除
- `agent_n.py` — 当前信号量无需负载均衡，删除
- 根目录 `trigger_learning_*.py` / `train_*.py` — 移到 `scripts/` 归档
- 根目录 `collect_*.py` / `generate_*.py` — 移到 `scripts/` 归档

**如果今后要增强量化能力，考虑引入**：
- Markov/HMM → 用于 Regime Detection 替代纯 LLM 判断
- Monte Carlo → 用于 VaR 和风险评估
- Bayesian → 用于信号置信度估计
- 相关性模型 → 接入作为跨市场套利的定量触发条件