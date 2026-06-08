# P0-C Historical Miner Decoupling 报告

**项目：** Polymarket_arbitrage  
**路径：** `/Users/libo/.hermes/polymarket_arbitrage`  
**日期：** 2026-06-06  
**阶段：** P0-C — Identity Decoupling（非 Model Migration）  
**结论：** ✅ **成功标准已满足，建议进入 P0-D**

---

## 1. 目标与结果

| 目标 | 结果 |
|------|------|
| 独立 `agent_id` | ✅ `agent_historical_miner` |
| 独立配置 | ✅ `agent_models` + `agent_config` |
| 不再引用 `agent_d` | ✅ 源码零引用 |
| 不改模型 / timeout / prompt / workflow | ✅ 遵守 |
| Learning ↔ Trading LLM 分离 | ✅ |

---

## 2. 新增文件列表

| 文件 | 说明 |
|------|------|
| `research/agent_registry.json` | Research layer agent 注册表；canonical id `agent_historical_miner` |
| `research/historical_miner_decoupling_audit.md` | Learning↔Trading 依赖审计 |
| `research/p0c_historical_miner_decoupling_report.md` | 本报告 |
| `research/p0c_validation/summary.json` | 验证运行摘要 |

---

## 3. 修改文件列表

| 文件 | 变更 |
|------|------|
| `config/llm_config.json` | 新增 `agent_models.agent_historical_miner`、`agent_config.agent_historical_miner` |
| `agents/historical_arbitrage_miner.py` | `agent_id`：`agent_d` → `agent_historical_miner`（仅 1 处） |

**未修改：** `executors/`、`risk/`、`strategy/`、所有 trading agent 源码、`llm_helper.py`（本阶段）、prompt、timeout（180s）、retry。

---

## 4. 旧依赖关系

```
historical_arbitrage_miner.py
    mine_arbitrage_opportunities()
        call_llm_sync(agent_id="agent_d", timeout=180, ...)
            llm_config.agent_models["agent_d"] → deepseek-v4-pro
            llm_helper.get_client() → DeepSeek proxy API
```

**问题：** Research 脚本借用 Trading 信号 agent 的 LLM identity，无法独立换模/监控/审计。

---

## 5. 新依赖关系

```
historical_arbitrage_miner.py
    mine_arbitrage_opportunities()
        call_llm_sync(agent_id="agent_historical_miner", timeout=180, ...)
            llm_config.agent_models["agent_historical_miner"] → deepseek-v4-pro
            llm_config.agent_config["agent_historical_miner"]:
                provider: deepseek
                timeout: 60
                max_retries: 3
            llm_helper.get_client() → DeepSeek proxy API（与 agent_d 同 provider 档，不同 id）
```

**注册表：**

```
research/agent_registry.json
    agents.agent_historical_miner.layer = "research"
    agents.agent_historical_miner.trading_agent_dependencies = []
```

---

## 6. `agent_d` 是否仍被 historical miner 引用？

| 检查项 | 结果 |
|--------|------|
| `historical_arbitrage_miner.py` 含 `agent_id='agent_d'` | ❌ **否** |
| `historical_arbitrage_miner.py` 含 `agent_id='agent_historical_miner'` | ✅ **是** |
| `config/llm_config.json` 中 `agent_d` 配置 | ✅ 未改动（仍为 `deepseek-v4-pro`） |
| `agents/agent_d.py` LLM 调用 | ✅ 仍为 `call_llm_sync("agent_d", ...)` |

**`agent_d` 仅作为独立 Trading Agent 存在，不再被 Learning miner 借用。**

---

## 7. 配置快照（无密钥）

```json
{
  "agent_models": {
    "agent_d": "deepseek-v4-pro",
    "agent_historical_miner": "deepseek-v4-pro"
  },
  "agent_config": {
    "agent_historical_miner": {
      "model": "deepseek-v4-pro",
      "provider": "deepseek",
      "timeout": 60,
      "max_retries": 3
    }
  }
}
```

- **未** 加入 `agent_providers`（无 grok / pawmaas）  
- 与 `agent_d` 同模型、同 provider 档；**仅 identity 独立**

---

## 8. 验证结果

### 8.1 `historical_arbitrage_miner` 运行

| 阶段 | 结果 |
|------|------|
| 加载历史数据 | ✅ 19 市场 |
| 价格波动分析 | ✅ 1 个潜在机会 |
| 统计汇总 | ✅ 完成 |
| LLM 分析 | ⚠️ 沙箱内 `Connection error`（`llm_helper` 默认客户端未走代理）；**路由正确** |

**补充验证（代理直连，同生产网络路径）：**

| `agent_id` | 解析模型 | 延迟 | JSON 结构 |
|------------|---------|------|-----------|
| `agent_d` | deepseek-v4-pro | 2.9s | ✅ |
| `agent_historical_miner` | deepseek-v4-pro | 3.2s | ✅ |

两者响应均为 `{"arbitrage_patterns":[],"top_opportunities":[]}` — **输出格式一致，无明显退化**。

### 8.2 `agent_d` 行为无变化

- `agents/agent_d.py` 未修改  
- `agent_models.agent_d` 仍为 `deepseek-v4-pro`  
- `AgentD` 类可正常加载  

### 8.3 源码审计

```json
{
  "uses_agent_historical_miner": true,
  "references_agent_d_id": false,
  "historical_miner_has_grok_provider": false,
  "agent_d_unchanged": true
}
```

---

## 9. 成功标准判定

| 标准 | 状态 |
|------|------|
| 独立 `agent_id` | ✅ |
| 独立 provider 配置（deepseek 档） | ✅ |
| 独立 `agent_config` | ✅ |
| 不依赖任何 Trading Agent identity | ✅ |
| Learning / Trading LLM 分离 | ✅ |

**P0-C 通过。**

---

## 10. 是否建议进入 P0-D？

**建议：✅ 进入 P0-D — Historical Miner Model Migration**

| P0-D 候选动作 | 说明 |
|---------------|------|
| 将 `agent_historical_miner` 迁至 `grok-4-1-fast-reasoning` | 与 `agent_g` / `agent_learning` 对齐，需新增 `agent_providers.agent_historical_miner` |
| 保持 `agent_d` 不变 | Trading 链路继续 deepseek |
| 可选：文件名对齐 | `historical_arbitrage_miner.py` → 保留别名（registry 已记录） |

**P0-D 前置已满足：** 独立 identity 已完成，换模不再影响 `agent_d`。

---

## 11. 相关文档

- 依赖审计：`research/historical_miner_decoupling_audit.md`
- Agent 注册：`research/agent_registry.json`
- 验证产物：`research/p0c_validation/summary.json`

---

*本阶段仅完成 Identity Decoupling；未切换 grok、未优化 timeout/retry、未改 prompt/workflow。*
