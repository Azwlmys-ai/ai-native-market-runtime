# Agent K v2 实施指南

## 概述

Agent K v2 是对原 Agent K 的重大重构，从**跨市场套利**转向**单边价值投资**。

## 核心变化

### 策略转变
- **原策略**：跨市场套利（买入多个市场的 NO，对冲风险）
- **新策略**：单边价值投资（识别被严重高估的单个市场）

### EV 提升
- **原 EV**：2-7%（套利空间限制）
- **新 EV**：20%+（极端错误定价）

### 数据支撑
- **原数据**：抽象描述（"过估"、"组最高"）
- **新数据**：具体数据（战绩、年龄、排名、ESPN 模型）

## 使用方法

### 1. 运行 Agent K v2

```bash
cd /opt/data/polymarket_arbitrage
python agents/agent_k_v2.py
```

### 2. 查看日志

```bash
tail -f logs/agent_k_v2_20260503.log
```

### 3. 查看生成的信号

```bash
cat data/signals.json | jq '.[] | select(.source == "agent_k_v2")'
```

## 信号格式

### 示例信号

```json
{
  "market": "Will the San Antonio Spurs win the 2026 NBA Finals?",
  "slug": "will-the-san-antonio-spurs-win-the-2026-nba-finals",
  "direction": "NO",
  "price": 0.7925,
  "amount": 150,
  "confidence": 88,
  "reason": "Spurs 重建期（平均年龄 24.3 岁），当前战绩 18-42（西部第 14），核心球员 Wembanyama 新秀赛季，ESPN 夺冠概率 < 1%，但市场隐含概率 20.75%，高估 20 倍",
  "data_sources": ["NBA.com Stats", "ESPN Power Rankings", "Basketball Reference"],
  "market_implied_probability": 20.75,
  "true_probability": 0.8,
  "ev_percentage": 24.9,
  "team_stats": {
    "record": "18-42",
    "rank": "Western Conference 14th",
    "average_age": 24.3,
    "key_info": "Wembanyama rookie season"
  },
  "source": "agent_k_v2",
  "timestamp": "2026-05-03T22:52:00.000000"
}
```

### 字段说明

| 字段 | 类型 | 说明 |
|------|------|------|
| `market` | string | 市场问题（完整英文） |
| `slug` | string | 市场 slug（用于 API 调用） |
| `direction` | string | 交易方向（固定为 "NO"） |
| `price` | float | NO 价格（> 0.75） |
| `amount` | int | 建议投入金额（$100-150） |
| `confidence` | int | 置信度（85-95） |
| `reason` | string | 具体数据支撑 |
| `data_sources` | array | 数据来源 |
| `market_implied_probability` | float | 市场隐含概率（%） |
| `true_probability` | float | 真实概率估计（%） |
| `ev_percentage` | float | 预期收益率（%，必须 > 20） |
| `team_stats` | object | 球队统计数据 |
| `source` | string | 信号来源（"agent_k_v2"） |
| `timestamp` | string | 生成时间 |

## 识别标准

### 必须同时满足

1. **重建期球队**或**战绩垫底**
   - 平均年龄 < 25
   - 排名后 25%

2. **严重高估**
   - 市场隐含概率 > 真实概率 * 3

3. **极端价格**
   - NO 价格 > 0.75

4. **高 EV**
   - EV > 20%

5. **流动性充足**
   - 交易量 > $100k

## 与 Agent M 的兼容性

### Agent M 审查标准

| 标准 | Agent K v2 满足情况 |
|------|-------------------|
| 数据支撑 | ✅ 具体战绩、年龄、排名 |
| 逻辑完整 | ✅ 市场隐含概率 vs 真实概率 |
| 价格优势 | ✅ EV > 20% |
| 风险控制 | ✅ 极端价格区间（NO > 0.75） |

### 预期通过率

- **原 Agent K**：0%（21/24 拒绝）
- **Agent K v2**：60%+（类似 Agent B）

## 与原 Agent K 的对比

| 维度 | 原 Agent K | Agent K v2 |
|------|-----------|-----------|
| 策略 | 跨市场套利 | 单边价值投资 |
| EV | 2-7% | 20%+ |
| 数据支撑 | 抽象描述 | 具体数据 |
| 通过率 | 0% | 60%+ |
| 信号频率 | 10-20/天 | 2-5/周 |
| 风险 | 低风险低收益 | 中风险高收益 |

## 迁移建议

### 方案 1：完全替换（推荐）

```bash
# 备份原 Agent K
mv agents/agent_k.py agents/agent_k_old.py

# 启用 Agent K v2
mv agents/agent_k_v2.py agents/agent_k.py
```

### 方案 2：并行运行

```bash
# 保留原 Agent K
# 同时运行 Agent K v2
python agents/agent_k_v2.py
```

### 方案 3：A/B 测试

```bash
# 运行 7 天，对比通过率和 EV
# 原 Agent K：每天运行
# Agent K v2：每天运行
# 7 天后选择更优方案
```

## 监控指标

### 关键指标

1. **信号生成数量**
   - 目标：2-5 个/周

2. **Agent M 通过率**
   - 目标：> 60%

3. **平均 EV**
   - 目标：> 20%

4. **实际收益**
   - 目标：扣除手续费后 > 15%

### 监控命令

```bash
# 查看信号数量
cat data/signals.json | jq '[.[] | select(.source == "agent_k_v2")] | length'

# 查看平均 EV
cat data/signals.json | jq '[.[] | select(.source == "agent_k_v2") | .ev_percentage] | add / length'

# 查看通过率
cat data/review_results.json | jq '.approved_signals | [.[] | select(.signal.source == "agent_k_v2")] | length'
```

## 常见问题

### Q1: 为什么不再做跨市场套利？

**A**: 跨市场套利的 EV 天花板只有 2-7%，无法达到 Agent M 的 20% 标准。即使是套利空间最大的 NHL（7%），EV 也只有 6.5%。

### Q2: 单边交易风险更高吗？

**A**: 是的，但通过以下方式控制风险：
- 只选择极端价格区间（NO > 0.75）
- 只选择重建期/战绩垫底球队
- 要求 EV > 20%（安全边际）
- 限制仓位（$100-150）

### Q3: 如何验证真实概率？

**A**: 
- 使用 ESPN、FiveThirtyEight 等模型
- 基于战绩、年龄、历史数据推断
- 要求市场隐含概率 > 真实概率 * 3（严重高估）

### Q4: 信号频率会降低吗？

**A**: 是的，从 10-20 个/天降低到 2-5 个/周。但信号质量大幅提升，通过率从 0% 提升到 60%+。

### Q5: 可以恢复原 Agent K 吗？

**A**: 可以，原代码已备份到 `agents/agent_k_old.py`。

## 下一步

1. **运行 Agent K v2**，生成第一批信号
2. **提交给 Agent M 审查**，验证通过率
3. **监控 7 天**，对比原 Agent K 和 Agent K v2
4. **根据数据决定**是否完全替换

## 联系

如有问题，请查看：
- 分析报告：`/opt/data/agent_k_ev_analysis.md`
- 代码：`/opt/data/polymarket_arbitrage/agents/agent_k_v2.py`
- 日志：`/opt/data/polymarket_arbitrage/logs/agent_k_v2_*.log`
