# Polymarket Multi-Agent 套利系统

## 系统状态

**账户余额：** $9,722.58 / $10,000（-2.77%）
- 现金：$7,475.82
- 持仓价值：$2,246.75
- 未实现盈亏：-$277.42

**持仓概览：** 15 个市场
- GTA VI 相关：4 个（高相关性风险 ⚠️）
- NHL 夺冠：10 个
- 其他：1 个

## 已部署 Agent

### 核心架构
- ✅ **Orchestrator** - 系统调度器
- ✅ **LLM Helper** - 统一 LLM 调用接口

### 数据层
- ✅ **Agent A** - 市场数据采集器（Polymarket、OKX、Google News、FRED）

### 决策层
- ✅ **Agent K** - 跨市场套利专员（grok-4-1-fast-reasoning）

### 风险审查层
- ✅ **Agent M** - 双模型风险审查员（gpt-5.4 + deepseek-v3.2）

### 待实现 Agent
- ⏳ **Agent B** - 情报研究员
- ⏳ **Agent D** - 无风险套利审查员
- ⏳ **Agent E** - BTC 滞后套利监控
- ⏳ **Agent F** - 跨平台监控
- ⏳ **Agent G** - 报告汇总员
- ⏳ **Agent H** - 钱包跟单监控
- ⏳ **Agent I** - 监控保活
- ⏳ **Agent J** - 交叉分析员
- ⏳ **Agent OKX Funding** - OKX 资金费率套利
- ⏳ **Agent P** - 持仓管理监控
- ⏳ **Strategy Manager** - 策略管理器

## 配置文件

- `config/llm_config.json` - LLM 模型配置
- `config/system_config.json` - 系统配置（风险管理、交易成本、数据源）

## 数据流

```
Agent A（数据采集）
    ↓
latest_data.json
    ↓
Agent K（跨市场套利）→ signals.json
    ↓
Agent M（风险审查）→ review_results.json
    ↓
信号执行器（待实现）
    ↓
Agent P（持仓管理）→ sell_signals.json
```

## 快速启动

```bash
# 单次扫描
source /opt/data/home/.bashrc
cd /opt/data/polymarket_arbitrage
python3 main.py --mode once

# 测试 LLM 连接
python3 llm_helper.py

# 测试数据采集
python3 agents/agent_a.py

# 查看账户余额
/opt/data/home/.local/bin/pm-trader balance

# 查看持仓
/opt/data/home/.local/bin/pm-trader portfolio
```

## 下一步

1. **实现剩余 Agent**（Agent B、D、E、F、G、H、I、J、OKX Funding、P、Strategy Manager）
2. **实现信号执行器**（读取 review_results.json，调用 pm-trader buy）
3. **实现持仓管理**（Agent P 监控持仓，生成卖出信号）
4. **修复定时任务**（更新 cron job 路径）
5. **处理 GTA VI 相关性风险**（4 个市场过度集中）

## 风险提示

⚠️ **GTA VI 相关性风险**：当前持仓中有 4 个市场与 GTA VI 发布日期相关，存在过度集中风险。建议：
- 限制单一锚点事件的总敞口 ≤30%
- 逐步平仓部分 GTA VI 相关持仓
- Agent B 已禁用 GTA VI 策略（发布日期不确定）
