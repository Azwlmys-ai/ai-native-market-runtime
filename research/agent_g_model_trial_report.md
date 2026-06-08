# Agent G 模型试用报告（P0-A）

**项目：** Polymarket_arbitrage  
**路径：** `/Users/libo/.hermes/polymarket_arbitrage`  
**最新更新：** 2026-06-06  
**当前生效配置：** ✅ **`grok-4-1-fast-reasoning` @ `https://api.pawmaas.com/v1`**

---

## 执行摘要

| 轮次 | 候选模型 | API | 结果 |
|------|---------|-----|------|
| Run 1 | `qwen3.7-plus` @ pawmaas.**cn** | 失败，已回滚 | ❌ 未通过 |
| **Run 2（当前）** | **`grok-4-1-fast-reasoning`** @ pawmaas.**com** | **通过** | ✅ **推荐进入 P0-B** |

**Run 2 核心指标：**

- LLM 成功率：**10/10（100%）**，0 超时
- 整轮均值墙钟：**19.95s**（中位 20.2s），远低于 orchestrator 120s 上限
- 同 prompt 延迟：grok **7.7s** vs deepseek **44.6s**（**降低 83%**）
- 输出质量：**无明显退化**，JSON 结构完整、洞察可执行

---

## 1. 当前配置（Run 2，已生效）

```json
// config/llm_config.json
"agent_models": { "agent_g": "grok-4-1-fast-reasoning" },
"agent_providers": {
  "agent_g": {
    "model": "grok-4-1-fast-reasoning",
    "api_base": "https://api.pawmaas.com/v1",
    "api_key": "sk-fZVvLbPH44ll7NDI6YCjHXNo9ND4EzVw8ES96s764Sj0IiRR",
    "proxy": "http://127.0.0.1:17891"
  }
}
```

> **注意：** OpenAI SDK 要求 `api_base` 带 `/v1` 后缀；用户提供的 `https://api.pawmaas.com` 需写为 `https://api.pawmaas.com/v1`。经本地代理 `127.0.0.1:17891` 可达。

### 代码（仅 `agent_g`）

- `_get_llm_provider()` / `_invoke_llm()` — 读取 `agent_providers.agent_g`，仅替换 model / api / proxy 传输层
- prompt、workflow、timeout（20s）、retry、business logic — **未改**

---

## 2. 指标对比

### 2.1 Timeout Rate

| 维度 | Before (`deepseek-v4-pro`) | Run 1 (`qwen3.7-plus`) | **Run 2 (`grok-4-1-fast-reasoning`)** |
|------|---------------------------|------------------------|--------------------------------------|
| Orchestrator 子进程超时（5日） | **28.2%** | — | 受控试验 **0%**（墙钟 <120s） |
| 受控 5 轮 LLM 调用超时 | 20s 上限下实测需 37~41s，易失败 | **100%** | **0%** ✅ |
| 受控 5 轮整轮超时（≥120s） | — | **100%** | **0%** ✅ |

**Timeout 降幅（vs deepseek 同 prompt）：** 44.6s → 7.7s = **-83%** ≥ 50% ✅

### 2.2 平均运行时长

| 任务 | deepseek-v4-pro | qwen3.7-plus | **grok-4-1-fast-reasoning** |
|------|-----------------|--------------|------------------------------|
| 拒绝分析（单任务） | 36.7~44.6s | 40.8s（90s 客户端） | **7.1~11.9s**（生产 20s 内） |
| 交易分析（单任务） | — | 超时 | **8.7~11.5s** |
| **整轮（双任务）** | >74s（估） | 123.4s（全失败） | **18.3~22.1s** |

受控 5 轮均值：**19.95s**（中位 20.2s）

### 2.3 成功完成任务数量

| 维度 | Before | Run 1 | **Run 2** |
|------|--------|-------|-----------|
| 受控 5 轮 LLM 成功 | 0 | 0/10 | **10/10** ✅ |
| 受控 5 轮流程成功 | — | 0/5 | **5/5** ✅ |
| 拒绝分析成功 | — | 0/5 | **5/5** |
| 交易分析成功 | — | 0/5 | **5/5** |

### 2.4 输出质量抽样

#### 头对头（同 prompt，`quality_pair.json`）

| 字段 | deepseek-v4-pro（44.6s） | grok-4-1-fast-reasoning（7.7s） | 退化？ |
|------|--------------------------|--------------------------------|--------|
| **Observation** | 信号-审查解耦、外部 API 脆弱、娱乐市场噪声 | API 故障占 60%、暴露规则未上游阻断 | 否 |
| **Hypothesis** | 4 条（含 GTA_VI 误分类、probe 泛滥） | 2 条（API 误杀、主题超限重复信号） | 略简，**核心一致** |
| **Attribution** | risk_review_api、agent_b rules、cointegration | 审查 API、主题暴露跟踪 | 否 |
| **Report Summary** | 5 条架构建议 | 3 条可执行建议（重试、预检、probe 阈值） | 否 |

**质量结论：** grok 输出更简洁，但覆盖了相同系统性问题（API 脆弱性、主题暴露未前置、probe 负载）。**未见明显退化。**

#### Run 2 抽样（`grok/run_1.json` 摘录）

- **拒绝分析 key_insights：** 「技术故障为主（API error 占多数），非风险逻辑缺陷；优先修复系统稳定性可显著降低拒绝率」
- **交易分析 key_insights：** 「大单 FOK 滑点损失主导失败；政治低价市场胜率高；优化订单大小是核心改进点」

---

## 3. 成功标准判定（Run 2）

| 标准 | 要求 | 实测 | 结果 |
|------|------|------|------|
| Timeout 降低 | ≥ 50% | 同 prompt **-83%**；生产 20s 内 **0 超时** | ✅ |
| 输出质量 | 无明显下降 | JSON 完整，洞察可执行，与 deepseek 同向 | ✅ |

**综合：Run 2 通过 P0-A → 推荐进入 P0-B。**

---

## 4. Run 1 回滚记录（qwen3.7-plus，仅供参考）

- API：`https://api.pawmaas.cn/v1` + 另一组 key
- 结果：20s 生产 timeout 下 **10/10 LLM 失败**；同 prompt 比 deepseek **更慢**（40.8s vs 36.7s）
- 已回滚；被 Run 2 替代

---

## 5. P0-B 推广建议

| Agent | 推荐？ | 说明 |
|-------|--------|------|
| `agent_learning` | ✅ **是** | 离线研究层，可复用同一 pawmaas provider 模式 |
| `historical_arbitrage_miner` | ✅ **是** | 研究挖掘；需独立 `agent_models` 键，勿复用 `agent_d` |
| `backtest_analyzer` | ✅ **是** | 回测/reporting，非交易路径 |

**P0-B 前置 checklist：**

1. 为各 agent 增加独立 `agent_providers.{agent_id}`（或共享 `research_provider` 块）
2. 保持 trading/risk/execution agent 仍为 `deepseek-v4-pro`
3. 在主机 orchestrator 跑满 1~2 日观察 `agent_g` 子进程超时率是否从 ~28% 降至 <10%

---

## 6. 附件

| 路径 | 说明 |
|------|------|
| `research/agent_g_trial_outputs/grok/summary.json` | Run 2 五轮汇总 |
| `research/agent_g_trial_outputs/grok/run_*.json` | 逐轮明细（含完整输出） |
| `research/agent_g_trial_outputs/grok/quality_pair.json` | grok vs deepseek 头对头 |
| `research/agent_g_trial_outputs/after_summary.json` | Run 1（qwen）失败记录 |

---

*Run 2 配置已生效；仅修改 `agent_g` + `config/llm_config.json` 中 agent_g 相关项。*
