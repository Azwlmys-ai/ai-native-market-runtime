# LLM Agent 模型审计报告

**审计日期：** 2026-06-06  
**项目路径：** `/Users/libo/.hermes/polymarket_arbitrage`  
**配置来源：** `config/llm_config.json`、`llm_helper.py`、`orchestrator.py`  
**日志样本：** `logs/orchestrator_20260605.log`、`logs/orchestrator_20260606.log`（约 2 日主循环）

> 本报告仅做只读审计与建议，**不修改任何代码或配置**。

---

## 1. 执行摘要

| 指标 | 结论 |
|------|------|
| 全局模型 | 所有已配置 `agent_models` 均为 **`deepseek-v4-pro`**（DeepSeek 直连，无异构 fallback） |
| 全局 LLM 超时 | `timeout=60s`，`max_retries=3` |
| Orchestrator 子进程超时 | 默认 **120s**；`agent_m` **240s**；`regime_detector` / `capital_adapter` **150s** |
| 近期高频 timeout | **`agent_e`（72%）> `agent_f`（68%）> `agent_g`（65%）> `agent_b`（51%）> `agent_m`（44%）** |
| 根因模式 | 多为主循环 **子进程墙钟超时**，而非单次 LLM 调用失败；`agent_e/f` 按市场逐条 LLM 循环是主要放大器 |

**核心建议：**

1. **禁止改模型**的 trading/risk/execution 链路 agent（`agent_m`、`agent_b`、信号生成器、资金/策略/状态层）应优先通过 **批量化、限流、提高 orchestrator 超时** 解决 timeout，而非降模型能力。
2. **允许改模型**的 research/reporting agent（`agent_g`、`agent_i`、离线学习类）可换 **`deepseek-chat`**（或同 provider 更快档）以降低延迟与成本。
3. `agent_a`、`agent_k_v2`、`agent_p` **不使用 LLM**，`llm_config.json` 中 `agent_a` / `agent_p` 条目为历史残留，可忽略。

---

## 2. Timeout 审计（2026-06-05 ~ 2026-06-06）

### 2.1 Orchestrator 主循环：超时频次排名

统计口径：日志中 `⏱️  {agent} 执行超时` 条数（子进程被 orchestrator `communicate(timeout=...)` 杀死）。

| 排名 | Agent | 超时次数 | 成功次数 | 合计 | 超时率 | Orchestrator 超时 |
|------|-------|---------|---------|------|--------|-------------------|
| 1 | `agent_e` | 34 | 13 | 47 | **72%** | 120s |
| 2 | `agent_f` | 32 | 15 | 47 | **68%** | 120s |
| 3 | `agent_g` | 31 | 16 | 47 | **65%** | 120s |
| 4 | `agent_b` | 25 | 24 | 49 | **51%** | 120s |
| 5 | `agent_m` | 20 | 25 | 45 | **44%** | 240s |
| — | 其余主循环 agent | 0 | 35~36/日 | — | **0%** | 120~150s |

其余 **0 timeout** 的 orchestrator agent：`agent_a`、`agent_d`、`agent_h`、`agent_j`、`agent_okx_funding`、`agent_i`、`agent_k_v2`、`agent_p`、`regime_detector`、`strategy_manager`、`capital_adapter`。

### 2.2 超时机制分析

| Agent | 内部 LLM 行为 | 典型超时原因 |
|-------|--------------|-------------|
| `agent_e` | 每个 BTC 市场 **单独** `call_llm_sync(..., timeout=30)` 循环 | N 个市场 × 30s+ 重试 → 易超 120s 子进程上限 |
| `agent_f` | 同 `agent_e`，按 ETH 市场逐条 LLM | 同上 |
| `agent_g` | 每笔成交复盘 `call_llm(..., timeout=20)` + `pm-trader` 历史拉取（20s） | 持仓/成交条目多 → 墙钟累加；复盘属学习链路但仍在主循环末尾 |
| `agent_b` | 单次大 prompt，`call_llm_sync(..., timeout=120)` | LLM 120s 与 orchestrator 120s **贴边**，无缓冲 |
| `agent_m` | 每条待审信号 `call_llm_sync("agent_m_primary", timeout=60)` | 信号批量大时接近 240s 上限；全量 REJECT 时仍消耗 LLM |

> **注意：** `config/llm_config.json` 全局 `timeout=60` 与 agent 内硬编码 `timeout=30/120` 并存；orchestrator 日志中的「执行超时」是 **Python 子进程总时长**，不完全等同于单次 LLM API timeout。

---

## 3. Agent 分类（Research vs Trading）

### 3.1 分类标准

| 类别 | 定义 | 模型变更策略 |
|------|------|-------------|
| **Research / Analytics / Reporting** | 产出报告、复盘、监控、离线学习；不直接下单或审批信号 | ✅ **允许**换更快/更便宜模型 |
| **Trading / Risk / Execution** | 生成交易信号、风险审批、资金/策略/市场状态决策、或驱动执行 | ❌ **禁止**修改模型（保持 `deepseek-v4-pro` 或更强） |
| **Non-LLM** | 规则引擎、HTTP 采集、子进程执行 | — 不适用 |

### 3.2 全量 LLM Agent 清单

#### A. Orchestrator 主循环（生产路径）

| Agent | 使用 LLM | 职能 | 分类 |
|-------|---------|------|------|
| `agent_a` | ❌ | Polymarket 数据采集 | Non-LLM |
| `regime_detector` | ✅ | 市场状态（牛/熊/震荡）→ `strategy_config` | **Trading** |
| `strategy_manager` | ✅ | 策略参数调整 | **Trading** |
| `capital_adapter` | ✅ | 动态资金分配 | **Trading** |
| `agent_b` | ✅ | 核心市场情报 → 交易信号 | **Trading** |
| `agent_k_v2` | ❌ | 规则引擎价值信号 | Non-LLM |
| `agent_d` | ✅ | 宏观套利信号 | **Trading** |
| `agent_e` | ✅ | BTC 滞后套利信号（逐市场 LLM） | **Trading** |
| `agent_f` | ✅ | ETH 滞后套利信号（逐市场 LLM） | **Trading** |
| `agent_h` | ✅ | 事件驱动信号 | **Trading** |
| `agent_okx_funding` | ✅ | 资金费率信号 | **Trading** |
| `agent_j` | ✅ | 跨市场信号 | **Trading** |
| `agent_m` | ✅ | **风险审批门控**（APPROVE/REJECT） | **Trading / Risk** |
| `agent_p` | ❌ | `pm-trader` 执行子进程 | **Execution**（Non-LLM） |
| `agent_g` | ✅ | 交易复盘、经验学习、反馈规则 | **Research** |
| `agent_i` | ✅ | 系统健康 LLM 报告 | **Research / Reporting** |

#### B. 存在但未纳入默认主循环

| Agent | 使用 LLM | 职能 | 分类 |
|-------|---------|------|------|
| `agent_learning` | ✅ | 离线训练集模式提取 | **Research** |
| `agent_codex` | ✅ | 部署前代码审查门控 | **Research / Governance** |
| `historical_arbitrage_miner` | ✅（复用 `agent_d` model id） | 历史套利模式挖掘 | **Research** |
| `agent_b_enhanced` / `v2` / `optimized` | ✅ | `agent_b` 实验变体 | **Trading**（未上线，仍禁止） |
| `backtest_analyzer` | ✅（config 有项） | 回测分析 | **Research** |

---

## 4. 建议表（核心交付物）

| Agent | 当前模型 | 建议模型 | 是否允许改 | 原因 |
|-------|---------|---------|-----------|------|
| **agent_e** | deepseek-v4-pro | **保持** deepseek-v4-pro | ❌ 禁止 | BTC 信号生成器，在交易主路径；timeout 72% 源于逐市场 LLM 循环，应批量化/限 TOP-N 市场而非降模型 |
| **agent_f** | deepseek-v4-pro | **保持** deepseek-v4-pro | ❌ 禁止 | 同 agent_e（ETH）；68% timeout，根因相同 |
| **agent_g** | deepseek-v4-pro | **deepseek-chat** | ✅ 允许 | 复盘/学习/reporting；65% timeout，换更快档可降墙钟；输出不直接触发下单 |
| **agent_b** | deepseek-v4-pro | **保持** deepseek-v4-pro | ❌ 禁止 | 核心情报与信号源；51% timeout 因 LLM 120s 与 orchestrator 120s 贴边，应加子进程缓冲或优化 prompt |
| **agent_m** | deepseek-v4-pro（`agent_m_primary`） | **保持** deepseek-v4-pro | ❌ 禁止 | 唯一风险审批门控；44% timeout 因信号批量审查，禁止为提速换弱模型 |
| **agent_m_secondary** | deepseek-v4-pro | **保持** deepseek-v4-pro | ❌ 禁止 | 风险验证备用位（config 保留） |
| **agent_m_trainer** | deepseek-v4-pro | **保持** deepseek-v4-pro | ❌ 禁止 | 风险模型训练/校准 |
| **agent_m_test** | deepseek-v4-pro | **保持** deepseek-v4-pro | ❌ 禁止 | 风险回归测试 |
| **agent_d** | deepseek-v4-pro | **保持** deepseek-v4-pro | ❌ 禁止 | 宏观套利信号；主循环 0 timeout，稳定性尚可 |
| **agent_h** | deepseek-v4-pro | **保持** deepseek-v4-pro | ❌ 禁止 | 事件驱动信号生成 |
| **agent_j** | deepseek-v4-pro | **保持** deepseek-v4-pro | ❌ 禁止 | 跨市场信号生成 |
| **agent_okx_funding** | deepseek-v4-pro | **保持** deepseek-v4-pro | ❌ 禁止 | 资金费率交易信号 |
| **regime_detector** | deepseek-v4-pro | **保持** deepseek-v4-pro | ❌ 禁止 | 市场状态直接影响策略开关与仓位风格 |
| **strategy_manager** | deepseek-v4-pro | **保持** deepseek-v4-pro | ❌ 禁止 | 策略参数写入生产配置 |
| **capital_adapter** | deepseek-v4-pro | **保持** deepseek-v4-pro | ❌ 禁止 | 资金分配直接影响敞口 |
| **agent_i** | deepseek-v4-pro | **deepseek-chat** | ✅ 允许 | 运维健康报告；单次 LLM、0% timeout，可安全降本提速 |
| **agent_learning** | deepseek-v4-pro（代码默认，config 无独立项） | **deepseek-chat** | ✅ 允许 | 离线学习；不阻塞主循环交易 |
| **agent_codex** | deepseek-v4-pro | **deepseek-chat** | ✅ 允许 | 部署审查；非实时交易路径 |
| **historical_arbitrage_miner** | deepseek-v4-pro（经 `agent_d` id） | **deepseek-chat** | ✅ 允许 | 研究挖掘；建议独立 `agent_models` 键而非复用 `agent_d` |
| **backtest_analyzer** | deepseek-v4-pro | **deepseek-chat** | ✅ 允许 | 回测分析/reporting |
| **agent_a** | deepseek-v4-pro（config 有，**未调用**） | — | — | Non-LLM 采集 agent；config 条目可视为冗余 |
| **agent_k** / **agent_k_v2** | deepseek-v4-pro（config 有 k） | — | — | Non-LLM 规则引擎 |
| **agent_p** | deepseek-v4-pro（config 有，**未调用**） | — | — | Execution 子进程，无 LLM |
| **agent_b_enhanced**\* | deepseek-v4-pro | **保持** deepseek-v4-pro | ❌ 禁止 | 交易信号实验变体，未上线亦应按生产标准 |

\* 含 `agent_b_enhanced`、`agent_b_enhanced_v2`、`agent_b_optimized`。

### 4.1 建议模型说明

| 建议模型 | 适用场景 | 备注 |
|---------|---------|------|
| **deepseek-v4-pro**（保持） | 所有 trading/risk/execution 链路 | 当前全栈统一；`fallback_map` 为 `__SINGLE_PROVIDER_NO_FALLBACK__`，单点风险 |
| **deepseek-chat** | research/reporting/offline | 同 provider、更低延迟/成本；需在改配置前做 A/B 质量对比（复盘 JSON 结构、学习规则可用性） |
| **不建议** | 交易链路换 `deepseek-chat` 或更小模型 | 会削弱信号质量与风险一致性，且无法从日志区分「慢」与「错」 |

---

## 5. 优先行动项（仅建议，不实施）

按 **timeout 严重度 × 是否允许改模型** 排序：

| 优先级 | Agent | 建议动作 | 改模型？ |
|--------|-------|---------|---------|
| P0 | `agent_e`, `agent_f` | 市场预筛选 + 单轮批量 JSON（替代 per-market LLM）；或提高 orchestrator 超时到 180s | ❌ |
| P0 | `agent_b` | orchestrator 超时调至 **150s**（LLM 120s + 缓冲） | ❌ |
| P1 | `agent_g` | 换 **deepseek-chat**；限制每轮复盘条数；pm-trader 历史与 LLM 并行度优化 | ✅ |
| P1 | `agent_m` | 信号去重后再送审；超时保持 240s；监控 REJECT 风暴 | ❌ |
| P2 | `agent_i`, `agent_learning`, `agent_codex` | 换 **deepseek-chat** 降本 | ✅ |
| P3 | config 卫生 | 为 `agent_learning` / `historical_arbitrage_miner` 增加独立 `agent_models` 键；移除或标注 `agent_a`/`agent_p` 无用项 | — |

---

## 6. 配置与代码交叉引用

```
config/llm_config.json
├── api_base: https://api.deepseek.com
├── agent_models: 全部 → deepseek-v4-pro
├── timeout: 60, max_retries: 3
└── fallback_map: 单 provider，无 fallback

orchestrator.py::_run_agent
├── agent_m → 240s
├── regime_detector, capital_adapter → 150s
└── default → 120s

llm_helper.py::call_llm_sync(agent_id)
└── 按 agent_models[agent_id] 解析模型；agent_m 使用 agent_m_primary
```

**代码注释与配置不一致：**

- `agent_m.py` 注释写「gpt-5.4」，实际 `agent_id="agent_m_primary"` → config 映射 **deepseek-v4-pro**。
- `historical_arbitrage_miner.py` 使用 `agent_id='agent_d'`，与研究/交易模型未隔离。

---

## 7. 审计方法

1. 扫描 `agents/*.py` 中 `call_llm_sync` / `call_llm` / `llm_helper` 引用。
2. 读取 `config/llm_config.json`、`orchestrator.py` 超时策略。
3. 统计 `logs/orchestrator_20260605.log` 与 `logs/orchestrator_20260606.log` 中 per-agent 成功/超时条数。
4. 按职能划入 research/reporting 或 trading/risk/execution，生成建议表。

---

*生成方式：只读审计，未修改仓库内任何 agent、config 或 orchestrator 代码。*
