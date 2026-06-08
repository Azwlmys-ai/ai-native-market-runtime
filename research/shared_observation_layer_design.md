# Shared Observation Layer 设计

**版本：** v0.1（Phase 1 设计稿）  
**日期：** 2026-06-07  
**状态：** 设计 only — 无代码、无服务、无部署  
**原则：** 共享 Observation，不共享 Experience

---

## 1. 设计目标

构建跨项目、可扩展的 **只读观测数据层**，使：

- **Polymarket_arbitrage** 可读取 OKX / ETF 的原始市场与探索观测
- **OKX Perp Trader** 可读取 PM / ETF 的标准化成交与事件日历
- **US ETF Quant**（未来）以相同契约接入

同时 **硬性隔离** 各项目的 Experience（规则、权重、审批、结论）。

---

## 2. 概念模型

```
┌─────────────────────────────────────────────────────────────────┐
│                    SHARED OBSERVATION LAYER                      │
│                  /Users/libo/shared_intelligence                 │
├─────────────────────────────────────────────────────────────────┤
│  observations/   ← 原子观测（未验证）                              │
│  history/        ← 时序/market replay 数据集                       │
│  trades/         ← 标准化成交导出（周度）                           │
│  events/         ← 宏观/财报/主题事件                               │
│  schemas/        ← 跨项目 JSON Schema                              │
│  manifests/      ← 溯源、checksum、safety_flags（新增）            │
├─────────────────────────────────────────────────────────────────┤
│  ❌ 禁止目录：                                                     │
│  experience/  rules/  weights/  decisions/  strategy_params/     │
└─────────────────────────────────────────────────────────────────┘
         ▲                    ▲                    ▲
         │ export (write)     │ export             │ export
         │                    │                    │
   ┌─────┴─────┐        ┌─────┴─────┐        ┌─────┴─────┐
   │  OKX Perp │        │ Polymarket│        │  US ETF   │
   │  Trader   │        │ Arbitrage │        │  Quant    │
   └───────────┘        └───────────┘        └───────────┘
         │                    │                    │
   Experience 留在        Experience 留在        Experience 留在
   各项目 private/        各项目 data/           各项目 private/
```

### 2.1 Observation vs Experience 判定规则

| 若数据回答… | 分类 | 示例 |
|------------|------|------|
| 「发生了什么？」 | **Observation** | 价格、成交、指标、funding、事件、探索样本 |
| 「我们应该怎么做？」 | **Experience** | boost rule、learned_rules、approved/rejected |
| 「模型/规则权重是多少？」 | **Experience** | rule_weights, model_effectiveness |
| 「统计上 N 笔交易的均值？」 | **Observation**（若不含行动建议） | theme_patterns, attribution counts |
| 「因此应该 ban 某 cell」 | **Experience** | experience_learning_candidates |

---

## 3. 目录结构（目标态）

在现有 `shared_intelligence/` 基础上 **增量扩展**，不破坏 Phase 1–3 已有路径：

```
shared_intelligence/
├── schemas/                          # 已有 + 扩展
│   ├── trade_record.schema.json      # 已有：周度成交
│   ├── event.schema.json             # 已有：事件日历
│   ├── observation_row.schema.json   # 新增：通用观测行
│   ├── okx_trade_memory.schema.json  # 镜像 OKX export schema
│   └── market_bar.schema.json        # 新增：OHLCV/funding bar
│
├── manifests/                        # 新增：溯源层
│   ├── okx_trade_memory_2026-06-07.json
│   ├── okx_weekly_2026-W23.json
│   └── pm_weekly_2026-W23.json
│
├── trades/                           # 已有
│   ├── okx_weekly.jsonl
│   ├── polymarket_weekly.jsonl
│   ├── us_etf_weekly.jsonl
│   └── event_attributed_trades.jsonl
│
├── events/                           # 已有
│   ├── nfp_calendar.json
│   ├── cpi_calendar.json
│   ├── fomc_calendar.json
│   ├── earnings_actual_calendar.json
│   └── theme_mapping.json
│
├── observations/                     # 已有（Markdown）+ 扩展 JSONL
│   ├── OBS_*.md                      # 已有：Polymarket 生成
│   ├── crypto/                       # 新增：按资产类分区
│   │   └── okx_explore_observations.jsonl
│   ├── equities/                     # 新增
│   │   └── etf_explore_observations.jsonl
│   └── prediction_markets/           # 新增
│       └── pm_probability_snapshots.jsonl
│
├── history/                          # 已有（Phase 3）
│   ├── macro/
│   ├── earnings/
│   ├── markets/
│   ├── themes/
│   ├── replay_dataset.jsonl
│   └── cross_market/                 # 新增
│       ├── okx_pm_aligned.jsonl      # lag/lead 对齐观测
│       └── funding_vol_panel.jsonl
│
├── kpi/                              # 已有
├── insights/                         # 已有（报告类 Observation 输出）
├── hypotheses/                       # 已有（候选，非 Experience）
│
└── learning/                         # ⚠️ 保留但重新定义边界
    ├── theme_patterns.json           # ✅ 统计观测
    ├── hypotheses.json               # ✅ 候选假设（未晋升）
    ├── insights.json                 # ⚠️ 晋升后仍非 rule weights
    └── learning_dashboard_summary.md # ✅ 报告
```

**明确禁止在 shared 层新增：**

- `shared_intelligence/experience/`
- `shared_intelligence/rules/`
- `shared_intelligence/weights/`
- `shared_intelligence/decisions/`

---

## 4. 资产类支持（crypto / stocks / prediction_markets）

### 4.1 统一观测行（`observation_row.schema.json` 设计要点）

```json
{
  "observation_id": "OBS_OKX_20260607_000001",
  "source_project": "okx_perp_trader",
  "asset_class": "crypto",
  "instrument": "BTC-USDT-SWAP",
  "observation_type": "explore_trade | bar | funding | probability | event_reaction",
  "ts_start": "2026-06-01T01:29:12.631Z",
  "ts_end": "2026-06-01T02:15:00.000Z",
  "payload": { },
  "metadata": {
    "safety_flag": "external_observation_only",
    "schema_version": "1.0",
    "manifest_ref": "manifests/okx_trade_memory_2026-06-07.json"
  }
}
```

### 4.2 按资产类映射

| asset_class | 源项目 | 观测类型 | 目标路径 |
|-------------|--------|----------|----------|
| **crypto** | OKX | explore_trade, funding, volatility, OHLCV | `observations/crypto/`, `history/cross_market/` |
| **stocks** | US ETF | closed trades, bar returns, event reactions | `observations/equities/`, `trades/us_etf_weekly.jsonl` |
| **prediction_markets** | Polymarket | probability snapshots, paper trades, market prices | `observations/prediction_markets/`, `trades/polymarket_weekly.jsonl` |

### 4.3 跨市场对齐（lag/lead 研究专用）

```
OKX observation (ts_open, ts_close, net_pnl_bps, metadata.regime)
        │
        │  time-align (±Δt window)
        ▼
PM probability snapshot (market_slug, yes_price, ts)
        │
        ▼
history/cross_market/okx_pm_aligned.jsonl   ← 仅 Observation，不含交易建议
```

---

## 5. 项目边界与读写矩阵

| 项目 | 可写入 shared | 可读取 shared | 禁止写入 shared |
|------|--------------|--------------|----------------|
| **OKX** | `trades/okx_weekly.jsonl`, `observations/crypto/*`, manifests | `events/`, `trades/pm_*`, `trades/etf_*` | knowledge/, experience_* |
| **Polymarket** | `trades/pm_*`, `events/`, `observations/`, `history/`, `learning/`（统计） | `trades/okx_*`, `trades/etf_*`, `observations/crypto/*` | `learning_knowledge_base`, `learned_rules` |
| **US ETF** | `trades/us_etf_weekly.jsonl`, `observations/equities/*` | `events/`, `trades/okx_*`, `trades/pm_*` | strategy params, risk rules |

**全局禁止（所有项目）：**

- 写入他方 Experience 文件
- 读取他方 `experience_learning_candidates`, `knowledge/`, `learned_rules`, `rule_effectiveness`
- 自动将 shared 观测注入 trading agent / executor / risk runtime

---

## 6. cross_project_data_catalog 集成

`cross_project_data_catalog` 是 Shared Observation Layer 的 **访问控制面**：

```
research/cross_project_data_catalog.json   (Phase 2 落盘)
        │
        ├── allowlist[]   → catalog_id → path → schema → asset_class
        ├── denylist[]    → path_pattern → reason
        └── adapters[]    → {catalog_id, reader, validator, target_path}
```

**读取流程（设计）：**

```
1. consumer 请求 catalog_id (e.g. "okx.trade_memory.export")
2. catalog_loader 解析绝对路径
3. experience_guard 匹配 denylist → 拒绝则 abort
4. observation_validator 校验 schema + safety_flag
5. 只读加载 → 写入本地 staging 或 shared history/
6. 禁止 touch data/learned_rules.json 等 Experience 路径
```

---

## 7. OKX → Polymarket 首批接入设计

### 7.1 已验证可共享包

| 字段 | 值 |
|------|-----|
| 源路径 | `okx_perp_trader/research/external_exports/okx_trade_memory_2026-06-07/` |
| 行数 | 92,575 |
| safety | `external_observation_only` |
| 用途 | OKX 价格行为 vs PM 概率定价的 lag/lead 研究 |

### 7.2 建议落点（Phase 2）

| 步骤 | 动作 | 输出 |
|------|------|------|
| 1 | 复制/链接 export → shared | `observations/crypto/okx_explore_observations.jsonl` |
| 2 | 复制 manifest | `manifests/okx_trade_memory_2026-06-07.json` |
| 3 | analytics 只读 joiner | `history/cross_market/okx_pm_aligned.jsonl` |
| 4 | 生成 OBS markdown | `observations/OBS_OKX_PM_LAG_*.md` |

### 7.3 明确不做

- ❌ 合并进 `data/paper_trades.jsonl`
- ❌ 更新 `rule_effectiveness.json`
- ❌ 注入 `agent_b` / `agent_m` prompt
- ❌ 修改 orchestrator / runtime

---

## 8. 未来扩展：US ETF Quant Project

| 接入项 | 路径 | asset_class |
|--------|------|-------------|
| 周度成交导出 | `trades/us_etf_weekly.jsonl`（已有） | equities |
| 探索观测（未来） | `observations/equities/etf_explore_observations.jsonl` | equities |
| 事件反应 | `history/equities/event_reactions.jsonl` | equities |

ETF 项目须遵守同一 schema 与 denylist；其 `strategy/` / `risk/` 下 Experience **不得**进入 shared。

---

## 9. 安全与合规

| 机制 | 说明 |
|------|------|
| `safety_flag` | 每份 manifest 必须含 `external_observation_only` |
| `additionalProperties: false` | Schema 限制敏感字段渗入 |
| 脱敏字段 | 禁止：API key, order_id, wallet, account_id, live position |
| checksum | manifest 含 sha256；消费者校验 |
| 只读挂载 | Phase 2+ 建议 read-only bind mount 或 symlink |
| 审计日志 | 每次 cross-project read 记录 catalog_id + row_count |

---

## 10. 与现有组件关系

| 现有组件 | 关系 |
|----------|------|
| `shared_intelligence/PRD_v1.1.md` | 本设计为其 Phase 2+ 扩展 |
| `research/history_paths.py` | 扩展 `OBSERVATIONS_CRYPTO` 等常量 |
| `analytics/event_joiner.py` | 继续消费 `trades/*_weekly.jsonl` |
| `research/export_shared_trades.py` | 继续写入 `trades/polymarket_weekly.jsonl` |
| OKX `external_exports/` | 首批 crypto observation 源 |

---

## 11. 实施路线图

| Phase | 内容 | 本次 |
|-------|------|------|
| **Phase 1** | 审计 + 分类 + 设计 | ✅ 本次完成 |
| **Phase 2** | catalog JSON + validator + 只读 adapter | 未开始 |
| **Phase 3** | OKX trade memory → shared observations/crypto | 未开始 |
| **Phase 4** | OKX↔PM lag/lead joiner（analytics only） | 未开始 |
| **Phase 5** | ETF observation 扩展 + 三市场 dashboard | 未开始 |

---

## 12. 成功标准（设计层）

- [x] 四分法清单覆盖 OKX 主路径
- [x] Polymarket allowlist/denylist _catalog 设计完成
- [x] `shared_observation_layer` 目录规范支持 crypto/stocks/prediction_markets
- [x] Experience 隔离规则可执行、可审计
- [x] 零代码、零部署、零 agent 修改

---

*配套文档：`research/data_sharing_audit_20260607.md`*
