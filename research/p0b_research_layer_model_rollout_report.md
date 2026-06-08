# P0-B Research Layer Model Rollout 报告

**项目：** Polymarket_arbitrage  
**路径：** `/Users/libo/.hermes/polymarket_arbitrage`  
**日期：** 2026-06-06  
**阶段：** P0-B — 将 `grok-4-1-fast-reasoning` 推广至 Research / Learning Layer  
**结论：** ✅ **通过成功标准，建议进入 P0-C**

---

## 1. 执行摘要

| Agent | 模型（After） | LLM 成功 | Timeout | 延迟 vs deepseek | JSON 完整 | 质量 |
|-------|-------------|---------|---------|------------------|-----------|------|
| `agent_learning` | grok-4-1-fast-reasoning | ✅ | 0 | **34.0s → 11.3s（-67%）** | ✅ | 无明显退化 |
| `backtest_analyzer` | grok-4-1-fast-reasoning | ✅ | 0 | **6.6s → 5.3s（-20%）** | ✅ | 无明显退化 |

推广配置复用 P0-A 已验证的 `agent_g` provider（model / api_base / proxy；api_key 同配置块引用，**不在此报告展示**）。

---

## 2. 修改范围

### 2.1 已修改

| 文件 | 变更 |
|------|------|
| `config/llm_config.json` | `agent_models.agent_learning`、`agent_models.backtest_analyzer` → `grok-4-1-fast-reasoning`；新增 `agent_providers.agent_learning`、`agent_providers.backtest_analyzer`（结构与 `agent_g` 相同） |
| `llm_helper.py` | 增加 `agent_providers` 路由（`_get_agent_provider` / `_client_from_provider`）；`call_llm_sync` / `call_llm` 在存在 provider 时走 pawmaas 客户端。**仅传输层，不改 prompt/workflow/timeout/retry** |

### 2.2 未修改（按要求）

| 类别 | 清单 |
|------|------|
| **暂缓** | `historical_arbitrage_miner`（见 §4） |
| **禁止** | `agent_b`、`agent_d`、`agent_e`、`agent_f`、`agent_h`、`agent_j`、`agent_m`、`agent_okx_funding`、`regime_detector`、`strategy_manager`、`capital_adapter` |
| **目录** | `executors/`、`risk/`、`strategy/` |
| **逻辑** | 交易 / 风控 / 执行逻辑；各 agent 的 prompt、workflow、timeout、retry |

### 2.3 保持 grok 的 Research Agent（P0-A + P0-B）

- `agent_g`（P0-A 已上线）
- `agent_learning`（P0-B）
- `backtest_analyzer`（P0-B）

其余 agent 仍为 **`deepseek-v4-pro`** @ DeepSeek。

---

## 3. 验证方法

### 3.1 agent_learning

- **路径：** `call_llm(model=agent_models["agent_learning"], timeout=120)`（与 `agents/agent_learning.py` 生产调用一致）
- **Prompt：** 代表性学习 prompt（含 market_rules / price_rules / risk_thresholds / position_sizing 要求）
- **对比：** 同 prompt 直连 `deepseek-v4-pro`（Before）vs pawmaas grok（After）

### 3.2 backtest_analyzer

- **路径：** `call_llm_sync("backtest_analyzer", prompt, timeout=120)`（与 `backtest_system.py` 生产调用一致）
- **Prompt：** 回测信号验证 JSON（`action` / `reason`）
- **补充 smoke：** `timeout=30` 短 prompt，**8.4s 成功**，无超时

### 3.3 产物

- `research/p0b_trial_outputs/validation_summary.json`

---

## 4. 为什么 `historical_arbitrage_miner` 暂缓

1. **模型 ID 耦合：** `historical_arbitrage_miner.py` 当前 `call_llm_sync(agent_id='agent_d', ...)`，与交易信号 agent **`agent_d` 共用 model 槽位**，推广 grok 会模糊 research / trading 边界。  
2. **任务范围：** P0-B 明确「暂不修改」该 agent，先验证独立 research 入口（`agent_learning`、`backtest_analyzer`）。  
3. **P0-C 前置：** 需在 P0-C 为其分配独立 `agent_models.historical_arbitrage_miner` + `agent_providers` 键，并解除对 `agent_d` 的复用。

---

## 5. agent_learning 验证结果

| 指标 | Before (deepseek-v4-pro) | After (grok-4-1-fast-reasoning) |
|------|------------------------|--------------------------------|
| LLM 成功率 | 1/1 ✅ | 1/1 ✅ |
| Timeout | 0 | 0 |
| 延迟 | **34.0s** | **11.3s** |
| JSON 键完整 | `market_rules`、`price_rules`、`risk_thresholds`、`position_sizing` ✅ | 同上 ✅ |

**质量评估：**

- **Observation：** grok 按市场类型（NHL/Crypto/Other）给出优先级与滑点依据，与 deepseek 同向。  
- **Hypothesis / 规则：** grok 输出更表格化、量化（如 `max_slippage_bps: 500`）；deepseek 更叙述性（含凯利、回撤停损等扩展字段）。  
- **退化判断：** 必需四维结构完整，规则可执行；grok 略简但 **无明显退化**。

---

## 6. backtest_analyzer 验证结果

| 指标 | Before (deepseek-v4-pro) | After (grok-4-1-fast-reasoning) |
|------|------------------------|--------------------------------|
| LLM 成功率 | 1/1 ✅ | 1/1 ✅ |
| Timeout | 0 | 0 |
| 延迟 | **6.6s** | **5.3s** |
| JSON 键完整 | `action`、`reason` ✅ | 同上 ✅ |
| 30s smoke | — | **8.4s** ✅ |

**质量评估：**

- Before / After 均返回 `action: buy`，理由均引用置信度与风险可控性。  
- grok 理由更偏历史回测胜率引用；deepseek 更偏当下条件判断——**决策一致，无明显退化**。

---

## 7. 成功标准判定

| 标准 | 要求 | 结果 |
|------|------|------|
| 无 timeout | 两 agent 均无 timeout | ✅ |
| 延迟低于 deepseek | 明显更低 | ✅（learning -67%，backtest -20%） |
| 输出结构完整 | JSON 必需字段齐全 | ✅ |
| 质量无明显退化 | 人工对比 | ✅ |

**P0-B 通过。**

---

## 8. 是否建议进入 P0-C

**建议：✅ 进入 P0-C**

P0-C 建议任务：

1. **`historical_arbitrage_miner` 独立化**
   - 新增 `agent_models.historical_arbitrage_miner`
   - 新增 `agent_providers.historical_arbitrage_miner`（复用 research provider 模板）
   - 将代码中 `agent_id='agent_d'` 改为独立 id（需单独授权，本次未做）

2. **Orchestrator 观测（可选）**
   - 主机跑 1~2 日，确认 `agent_g` 子进程超时率维持低位（P0-A 受控试验 0%）

3. **保持隔离**
   - 所有 trading / risk / execution agent 继续使用 `deepseek-v4-pro`

---

## 9. 配置快照（无密钥）

```json
"agent_models": {
  "agent_g": "grok-4-1-fast-reasoning",
  "agent_learning": "grok-4-1-fast-reasoning",
  "backtest_analyzer": "grok-4-1-fast-reasoning"
},
"agent_providers": {
  "agent_g": { "model": "grok-4-1-fast-reasoning", "api_base": "https://api.pawmaas.com/v1", "proxy": "http://127.0.0.1:17891", "api_key": "<同 agent_g，见 llm_config.json>" },
  "agent_learning": { "...": "同 agent_g 结构" },
  "backtest_analyzer": { "...": "同 agent_g 结构" }
}
```

---

*P0-B 完成：仅 Research / Learning 低风险 agent 换模；交易链路未触碰。*
