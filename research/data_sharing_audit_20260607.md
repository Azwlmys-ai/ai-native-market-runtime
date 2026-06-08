# 跨项目数据共享审计报告

**审计日期：** 2026-06-07  
**阶段：** Data Sharing Layer — Phase 1（只读审计）  
**项目范围：**

| # | 项目 | 根目录 |
|---|------|--------|
| 1 | OKX Perp Trader | `/Users/libo/okx_perp_trader` |
| 2 | Polymarket Arbitrage | `/Users/libo/.hermes/polymarket_arbitrage` |
| 3 | US ETF Quant（未来） | `/Users/libo/us-lev-etf-cta`（已部分接入） |

**核心原则：** 共享 **Observation**，不共享 **Experience**。

> 本次仅审计、分类、设计。**未修改** Agent、orchestrator、runtime、策略、风控、配置、数据库；未部署、未重启、未写代码。

---

## 1. 分类标准

| 类别 | 定义 | 跨项目策略 |
|------|------|-----------|
| **A. Observation Data** | 原始市场/价格/指标/事件/成交/持仓/探索样本/研究结果（事实记录） | ✅ **允许只读共享** |
| **B. Experience Data** | 学习规则、权重、审批结论、归因结论、知识原子、boost/penalize/ban | ❌ **禁止共享** |
| **C. Runtime Data** | 运行日志、checkpoint、manifest、orchestrator 状态 | ❌ **禁止共享**（项目私有） |
| **D. Configuration** | Schema、manifest、策略参数、LLM 路由、API 密钥 | ⚠️ **仅共享 Schema/Manifest**；密钥与策略参数禁止 |

---

## 2. OKX Perp Trader 数据清单

### 2.1 A — Observation Data（可共享）

#### 2.1.1 已标准化跨项目导出包（最高优先级）

| 路径 | 大小 | 记录数 | 更新时间 | 数据类型 |
|------|------|--------|----------|----------|
| `/Users/libo/okx_perp_trader/research/external_exports/okx_trade_memory_2026-06-07/okx_trade_memory_sample.jsonl` | **96.2 MB** | **92,575** | 2026-06-07 09:49 | 标准化探索成交观测（paper observation rows） |
| 同目录 `okx_trade_memory_schema.json` | 2 KB | — | 2026-06-07 | 行级 JSON Schema |
| 同目录 `okx_trade_memory_manifest.json` | 3.6 KB | — | 2026-06-07 | 溯源、checksum、`external_observation_only` 安全标记 |
| 同目录 `README.md` | 2 KB | — | 2026-06-07 | 使用边界说明 |

**行字段（观测）：** `source_project`, `symbol`, `ts_open`, `ts_close`, `direction`, `signal_type`, `exit_reason`, `hold_sec`, `gross/net_pnl_bps`, `fees_bps`, `session`, `metadata`（regime, cell_key, MFE/MAE, spread, follow-through 等）

**时间范围：** 2026-06-01 ~ 2026-06-07 · **标的：** BTC, ETH, SOL

#### 2.1.2 探索成交记忆（原始 JSONL，含内嵌指标快照）

| 路径模式 | 规模（估） | 记录数（估） | 更新时间 | 数据类型 |
|----------|-----------|-------------|----------|----------|
| `research/explore_runs/*/explore_trade_memory.jsonl` | 1–27 MB/运行 | 12–9,490/运行 | 2026-06-01~02 | 探索层成交 + **内嵌 indicators** |
| `research/experience_snapshot/explore_runs/*/explore_trade_memory.jsonl` | 同上（副本） | 同上 | 2026-06-01~07 | 快照副本 |
| `research/vps_daily/*/explore_runs/*/explore_trade_memory.jsonl` | ~430 MB 合计 | 多运行累加 | 2026-06-02~04 | VPS 拉取副本 |
| `research/trade_memory.jsonl` | 2.3 MB | 952 | 2026-06-01 | 早期 trade memory |
| `research/okx_public_trade_memory.jsonl` | 181 KB | 79 | 2026-06-01 | OKX public paper 成交 |

**内嵌指标（非独立文件）：** `ema20/50`, `atr14`, `rsi14`, `adx14`, `volatility_bps`, **`funding_rate`**, `spread_bps`, `regime`, `volume_ratio`

> 注意：原始 JSONL 比 external export **字段更全**，但需额外脱敏与去重；**优先使用已 scrub 的 export 包**。

#### 2.1.3 市场快照 / 指标快照

| 路径 | 大小 | 记录数 | 更新时间 | 数据类型 |
|------|------|--------|----------|----------|
| `research/okx_capture/capture.json` | 18 KB | 3 instruments | 2026-06-01 | 时点 OKX public WS 捕获 |
| *嵌入于 trade memory `indicators` 字段* | — | per-trade | — | 指标快照（无独立 snapshot 文件） |

#### 2.1.4 Funding / Volatility / OHLCV

| 路径 | 大小 | 更新时间 | 数据类型 |
|------|------|----------|----------|
| `env_rule/user_data/data/okx/futures/BTC_USDT_USDT-1h-funding_rate.feather` | 7 KB | 2026-05-29 | BTC 资金费率序列 |
| `env_rule/user_data/data/okx/futures/ETH_USDT_USDT-1h-funding_rate.feather` | 7 KB | 2026-05-29 | ETH 资金费率 |
| `env_rule/user_data/data/okx/futures/*-5m/15m/1h-futures.feather` | 66 KB–655 KB | 2026-05-29 | OHLCV K 线 |
| `env_rule/user_data/data/okx/futures/*-1h-mark.feather` | 51–52 KB | 2026-05-29 | Mark price |

#### 2.1.5 执行历史 / 信号观测样本

| 路径 | 大小 | 记录数 | 更新时间 | 数据类型 |
|------|------|--------|----------|----------|
| `execution_mvp/samples/okx_public_paper_30m.jsonl` | 615 KB | 2,321 | 2026-05-30 | Public paper 事件流 |
| `execution_mvp/samples/okx_signal_audit_30m.jsonl` | 607 KB | 1,438 | 2026-05-30 | 信号审计 tick |
| `execution_mvp/samples/signal_candidates_30m.jsonl` | 435 KB | 542 | 2026-05-30 | 信号候选观测 |
| `execution_mvp/samples/reversal_observation_*.jsonl` | 99–232 KB | 425–1,003 | 2026-05-30 | 反转模型观测 |

#### 2.1.6 持仓 / 执行（Freqtrade dry-run，弱观测）

| 路径 | 大小 | 记录数 | 更新时间 | 数据类型 |
|------|------|--------|----------|----------|
| `env_rule/user_data/tradesv3.sqlite` | 极小 | trades: 2 | 2026-05-30 | Freqtrade 长方向 dry-run |
| `env_rule/user_data/tradesv3_short.sqlite` | 极小 | trades: 12 | 2026-06-03 | Freqtrade 短方向 dry-run |

> 优先级低：与 explore 层 schema 不一致，样本极少。

#### 2.1.7 已接入 shared_intelligence 的 OKX 周度导出

| 路径 | 大小 | 记录数（行） | 更新时间 | 数据类型 |
|------|------|-------------|----------|----------|
| `/Users/libo/shared_intelligence/trades/okx_weekly.jsonl` | **210 KB** | ~数百 | 2026-06-06 | 标准化 closed-trade 导出（`trade_record.schema.json`） |

---

### 2.2 B — Experience Data（禁止共享）

| 路径 | 大小 | 记录/结构 | 更新时间 | 禁止原因 |
|------|------|----------|----------|----------|
| `research/experience_learning_candidates.json` | 4.3 KB | boost:2, penalize:5, ban:5 | 2026-06-07 | **学习候选规则** |
| `research/vps_learning_feedback_2026-06-07.json` | 5.0 KB | 同上 + safety_notes | 2026-06-07 | **经验反馈包装** |
| `research/experience_review_2026-06-07.md` | 13 KB | 91,443 笔归因结论 | 2026-06-07 | **经验审查结论** |
| `research/knowledge/knowledge_summary.json` | 424 B | 565 atoms 索引 | 2026-06-04 | 知识库索引 |
| `research/knowledge/**/*.json` | **2.2 MB** | **565** atoms | 2026-06-02~04 | **EDGE/RISK/REGIME 结论** |
| `research/cell_attribution.json` | 6 KB | by_cell 归因 | 2026-06-01 | 单元归因经验 |
| `research/explore_cell_attribution*.json` | 14–27 KB | 多运行归因 | 2026-06-01 | 探索归因经验 |
| `research/reports/daily_attribution_2026-06-0*.json` | 258–302 KB | risk_warnings | 2026-06-04 | 日度归因 + 风险警告 |
| `research/lessons/weekly_lessons_2026-W23.json` | 269 KB | prefer/avoid/rules | 2026-06-04 | **周度蒸馏经验** |
| `research/oos_candidates.json` | 1.1 KB | OOS cell 候选 | 2026-06-02 | 样本外验证候选 |
| `reports_rule/v5_*_summary.json` | 0.5–2.3 MB | 回测结论 | 2026-05-31 | 策略研究结论 |
| `research/trade_case_studies/*.md` | 902 文件 | 叙事复盘 | 2026-06-01 | 衍生经验叙述（可选只读，默认禁止） |

---

### 2.3 C — Runtime Data（禁止共享）

| 路径模式 | 说明 |
|----------|------|
| `research/explore_runs/*/explore_run.json` | 运行配置快照 |
| `research/vps_daily/*/pull_manifest.json` | VPS 同步清单 |
| `research/vps_daily/*/logs/*.log` | 探索运行日志 |
| `research/okx_public_runs/*/okx_public_run.json` | Public run checkpoint |
| `execution_mvp/reports/*_audit*.json` | MVP 审计 checkpoint |
| `logs/docker_freqtrade_*.log` | Freqtrade 容器日志 |

---

### 2.4 D — Configuration（仅 Schema/Manifest 可共享）

| 路径 | 可共享？ | 说明 |
|------|---------|------|
| `external_exports/.../okx_trade_memory_schema.json` | ✅ | 跨项目契约 |
| `external_exports/.../okx_trade_memory_manifest.json` | ✅ | 溯源与安全标记 |
| `execution_mvp/configs/paper_*.json` | ❌ | 策略/纸面参数 |
| `execution_mvp/configs/reversal_btc.json` | ❌ | 策略参数 |
| `env_rule/user_data/data/okx/leverage_tiers_USDT.json` | ⚠️ | 交易所元数据，可观测但非必需 |

---

## 3. Polymarket Arbitrage 本地数据分类（摘要）

### 3.1 可向外共享（Observation）

| 路径 | 类型 |
|------|------|
| `shared_intelligence/trades/polymarket_weekly.jsonl`（经 export 脚本） | 标准化成交观测 |
| `shared_intelligence/events/*` | 事件日历 |
| `shared_intelligence/observations/OBS_*.md` | 未验证观测 |
| `shared_intelligence/history/*` | 历史回放数据集 |
| `shared_intelligence/learning/theme_patterns.json` | 主题统计（学习层输出，非规则） |
| `data/arbitrage_opportunities.json` | 历史挖掘模式（研究结果） |

### 3.2 禁止向外共享（Experience / Runtime）

| 路径 | 类别 | 禁止原因 |
|------|------|----------|
| `data/learning_knowledge_base.json` | Experience | rejection prompt 增强 |
| `data/learned_rules.json` | Experience | Agent B 学习规则 |
| `data/model_effectiveness.json` | Experience | 模型权重建议 |
| `data/rule_effectiveness.json` | Experience | rule weights |
| `data/postmortems.jsonl` | Experience | Agent G 复盘 |
| `data/signals.json`, `approved_signals.json` | Runtime | 交易信号 |
| `data/positions.json`, `execution_results.json` | Runtime | 执行状态 |
| `config/llm_config.json` | Configuration | 含 API 密钥 |

---

## 4. cross_project_data_catalog（Polymarket 视角）

> 机器可读路径注册表建议落盘：`research/cross_project_data_catalog.json`（Phase 2 实现）。以下为 Phase 1 设计目录。

### 4.1 允许读取（Read Allowlist）

| catalog_id | 源项目 | 路径 | 数据类型 | Polymarket 用途 |
|------------|--------|------|----------|----------------|
| `okx.trade_memory.export` | OKX | `okx_perp_trader/research/external_exports/okx_trade_memory_*/okx_trade_memory_sample.jsonl` | A | OKX↔PM 滞后/领先研究 |
| `okx.trade_memory.schema` | OKX | 同目录 `okx_trade_memory_schema.json` | D | 契约校验 |
| `okx.trade_memory.manifest` | OKX | 同目录 `okx_trade_memory_manifest.json` | D | 溯源 / checksum |
| `okx.trades.weekly` | OKX | `shared_intelligence/trades/okx_weekly.jsonl` | A | 事件归因（**已接入**） |
| `okx.market.ohlcv` | OKX | `env_rule/user_data/data/okx/futures/*.feather` | A | 宏观/波动背景 |
| `okx.market.funding` | OKX | `*-funding_rate.feather` | A | 资金费率观测 |
| `okx.execution.samples` | OKX | `execution_mvp/samples/okx_public_paper_30m.jsonl` 等 | A | 微观结构参考 |
| `etf.trades.weekly` | ETF | `shared_intelligence/trades/us_etf_weekly.jsonl` | A | 跨市场归因（**已接入**） |
| `pm.trades.weekly` | PM | `shared_intelligence/trades/polymarket_weekly.jsonl` | A | 自有导出 |
| `shared.events` | Hub | `shared_intelligence/events/*.json` | A | 事件窗口 |
| `shared.attributed_trades` | Hub | `shared_intelligence/trades/event_attributed_trades.jsonl` | A | 归因后观测 |
| `shared.schemas` | Hub | `shared_intelligence/schemas/*.json` | D | 契约 |

### 4.2 禁止读取（Read Denylist）

| catalog_id | 源项目 | 路径模式 | 类别 | 风险 |
|------------|--------|----------|------|------|
| `okx.experience.candidates` | OKX | `research/experience_learning_candidates.json` | B | boost/penalize/ban 规则泄漏 |
| `okx.experience.feedback` | OKX | `research/vps_learning_feedback_*.json` | B | 学习反馈 |
| `okx.experience.review` | OKX | `research/experience_review_*.md` | B | 经验结论 |
| `okx.knowledge.atoms` | OKX | `research/knowledge/**/*.json` | B | 565 知识原子 |
| `okx.attribution.cells` | OKX | `research/*cell_attribution*.json` | B | 单元 edge 结论 |
| `okx.lessons.weekly` | OKX | `research/lessons/weekly_lessons_*.json` | B | 蒸馏经验 |
| `okx.oos.candidates` | OKX | `research/oos_candidates.json` | B | OOS 验证候选 |
| `pm.experience.rules` | PM | `data/learned_rules.json` | B | 策略规则 |
| `pm.experience.kb` | PM | `data/learning_knowledge_base.json` | B | 风控 prompt 增强 |
| `pm.experience.weights` | PM | `data/rule_effectiveness.json` | B | rule weights |
| `pm.runtime.signals` | PM | `data/signals.json` 等 | C | 运行时状态 |
| `*.config.secrets` | ALL | `**/llm_config.json`, API keys | D | 密钥泄漏 |

### 4.3 访问模式（Phase 1 设计，未实现）

```
polymarket_arbitrage/research/
    └── read_only adapters (Phase 2+)
            ├── catalog_loader.py      # 读取 allowlist
            ├── observation_validator.py  # schema + safety flag 校验
            └── experience_guard.py    # 拒绝 denylist 路径
```

**硬规则：**

1. 只读 `open()` / 只读 mmap；禁止 write/append  
2. 必须通过 `catalog_id` 解析路径，禁止硬编码 OKX 经验文件路径  
3. 导入数据写入 `shared_intelligence/observations/` 或 `history/`，**不得**写入 `data/learned_rules.json` 等 Experience 文件  

---

## 5. 风险分析

| 风险 ID | 描述 | 等级 | 缓解 |
|---------|------|------|------|
| R1 | **Experience 误导入**：将 `experience_learning_candidates.json` 当作观测读入 PM | 🔴 高 | catalog denylist + `experience_guard` |
| R2 | **规则交叉污染**：OKX boost/penalize 影响 PM `agent_b` / `agent_m` | 🔴 高 | 禁止写入任何 `learned_rules` / `learning_knowledge_base` |
| R3 | **隐式策略泄漏**：原始 `explore_trade_memory.jsonl` 含 `cell_key`/`setup_type` 被当作 PM 信号 | 🟡 中 | 优先用 scrubbed export；标注 `external_observation_only` |
| R4 | **副本膨胀**：同一 run 存于 explore_runs / experience_snapshot / vps_daily 三处 | 🟡 中 | manifest 去重；catalog 指向 canonical export |
| R5 | **归因缺口**：`okx_weekly.jsonl` 与事件窗口 0 重叠（gap analysis） | 🟡 中 | 扩展 export 时间戳精度；非共享层问题 |
| R6 | **密钥泄漏**：`llm_config.json` 误入共享目录 | 🔴 高 | D 类禁止；schema-only 共享 |
| R7 | **未来 ETF 扩展**：第三项目接入时 Experience 混放 | 🟡 中 | 统一 `shared_observation_layer` 目录规范 |

---

## 6. 当前接入状态

| 数据通道 | 状态 | 消费者 |
|----------|------|--------|
| `okx_weekly.jsonl` → shared_intelligence | ✅ 已接入 | `event_joiner`, `weekly_kpi`, 归因报告 |
| `okx_trade_memory` export | ⏸️ **未接入** | 无 polymarket 代码引用；README 已声明用途 |
| `explore_trade_memory` 原始 JSONL | ⏸️ 未接入 | — |
| OKX funding/volatility feather | ⏸️ 未接入 | PM 用本地 `data/historical/okx_*_klines*.json` 回退 |

---

## 7. 后续建议（Phase 2+，本次不实施）

| 优先级 | 动作 |
|--------|------|
| P0 | 落盘 `research/cross_project_data_catalog.json`（allowlist/denylist） |
| P1 | 实现 `observation_validator`：校验 `external_observation_only` + schema |
| P1 | 研究适配器：只读加载 `okx_trade_memory_sample.jsonl` → `shared_intelligence/history/okx_observations.jsonl` |
| P2 | OKX↔PM lag/lead joiner（analytics 层，非 agent） |
| P2 | ETF 项目对齐同一 catalog 与 schema |
| P3 | 定期 manifest 刷新与 checksum 审计 |

---

## 8. 审计方法

1. 遍历 `/Users/libo/okx_perp_trader/research/`, `execution_mvp/`, `env_rule/user_data/data/`  
2. 比对 `/Users/libo/shared_intelligence/` 现有布局与 PRD v1.1  
3. Grep polymarket 跨项目路径引用（22 文件）  
4. 按 Observation / Experience / Runtime / Configuration 四分法归类  
5. 对照用户禁止清单（learning rules, weights, decisions, strategy params 等）

---

*Phase 1 完成：仅研究报告，零代码变更、零部署。*
