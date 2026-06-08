# Polymarket Arbitrage — 数据利用率审计

**审计日期：** 2026-06-07  
**项目：** `/Users/libo/.hermes/polymarket_arbitrage`  
**类型：** 只读审计 — 未修改代码 / Agent / orchestrator / 配置；未部署、未重启

---

## 核心问题

> **系统当前采集的数据，到底有多少真正进入了决策链路？**

### 结论（先答）

| 口径 | 利用率 | 说明 |
|------|--------|------|
| **实时采集字段（`latest_data.json`）** | **~28–30%** | 10 个顶层字段中，仅 `polymarket_markets`、`fed_rate`、`btc_funding_rate` 进入 Agent B → M 信号决策链 |
| **每周期持久化产物** | **~41%** | 约 20 个写盘文件中，8 个被 B/M/P/G 决策链读取 |
| **历史归档（`data/historical/`）** | **~4%** | 37 个文件；RiskEngine 部分读取 3 个聚合文件，其余零消费 |
| **跨项目 shared_intelligence** | **0%（实时链）** | 952 行 OKX + 38 行 ETF + 346 行 replay — 仅离线 `analytics/` 使用 |

**最大浪费机制：** `orchestrator._consolidate_signals_for_review()` 在 Agent B 有信号时 **完整替换** `signals.json`，同周期 Agent D/E/F/H/J/K 的产出 **不进入 Agent M**（代码注释与实现一致：`orchestrator.py:493–606`）。

**决策链路定义（本审计）：**

```
买入：A 采集 → B 情报 → consolidate → RiskEngine → M 审查 → Executor
卖出：P 读 pm-trader + market_price_history + strategy_config
学习反馈：G 读 pm-trader history + review_results → learning_knowledge_base → 下轮 M
```

研究层（HMM/GARCH/协整）默认 `enforced=False`，**不计入**主决策链，除非 `PA_COINT_SIGNALS` / `PA_ENFORCE_*` 显式开启。

---

## 第一部分 — 数据源盘点

### 1.1 实时采集（每周期 ~300s）

| 数据源名称 | 采集模块 | 文件路径 | 更新频率 | 记录规模 | 分类 |
|-----------|----------|----------|----------|----------|------|
| Polymarket 市场快照 | `agents/agent_a.py` | `data/latest_data.json` → `polymarket_markets` | 每周期 | 100 市场 | Polymarket |
| PM 价格滚动历史 | `orchestrator._record_market_prices` | `data/market_price_history.json` | 每周期 | 100 序列 / 5,900 点 | Polymarket |
| PM 订单簿缓存 | `market_intelligence.py` | `data/orderbook_cache.json` | TTL 120s | 可变 | Polymarket |
| PM 市场情报画像 | `market_intelligence.py` | `data/market_intelligence.json` | 每周期 shadow | ~100 profiles / 84 KB | Market Intelligence |
| Google News RSS | `agents/agent_a.py` | `latest_data.json` → `google_news` | 每周期 | 全文 RSS | Market Intelligence |
| OKX 现货/永续/费率 | `collectors/okx_collector.py` + Agent A | `data/okx_data.json`, `latest_data.okx` | 每周期 | 4 币 | Crypto |
| BTC 资金费率（标量） | `agents/agent_a.py` | `latest_data.btc_funding_rate` | 每周期 | 1 值 | Funding |
| 美股报价 | `collectors/us_stocks_updater.py` | `latest_data.us_stocks`, `us_stocks_cache.json` | 每周期 | 8 标的 | US Stocks |
| 商品 & 外汇 | `collectors/commodity_forex_collector.py` | `data/commodity_forex_data.json` | 每周期 | **0 商品 / 0 外汇**（空） | Commodity / Forex |
| FRED 联邦基金利率 | `agents/agent_a.py` | `latest_data.fed_rate` | 每周期 | 最新 1 行 | Macro |
| 跨资产价格历史 | `orchestrator._record_market_prices` | `data/asset_price_history.json` | 每周期 | 15 symbol / 724 点 | Crypto / US Stocks / Funding |
| LLM 市场状态（legacy） | `agents/regime_detector.py` | `data/market_regime.json` | 每周期 | 1 对象 | Regime |
| 策略配置 | `agents/strategy_manager.py` | `data/strategy_config.json` | 每周期 | 1 对象 | Other |
| 资金分配 | `agents/capital_adapter.py` | `data/capital_allocation.json` | 每周期 | 1 对象 | Other |
| Agent B 情报报告 | `agents/agent_b.py` | `data/intelligence_report.json` | 每周期 | ~9 KB | Market Intelligence |
| 风险快照 | `risk/risk_engine.py` | `data/risk_snapshot.json` | 每周期 | 1 对象 | Other |
| 信号批次 | `orchestrator` consolidate | `data/signals.json` | 每周期替换 | 581（shadow 累计） | Polymarket |
| 审查结果 | `agents/agent_m.py` | `data/review_results.json`, `approved_signals.json` | 每周期 | 353 reviews | Polymarket |
| 持仓 / 执行 | `runtime/datastore.py` | `positions.json`, `execution_results.json` 等 | 每周期 | 26 持仓 / 72 订单 | Polymarket |
| 纸面成交 | `runtime/datastore.py` | `data/paper_trades.jsonl` | 成交时 | 3,847 行 | Polymarket |
| 运行时事件 | `event_logger.py` | `data/events/runtime_events.jsonl` | 每周期 | 11,116 行 | Other |

### 1.2 周期末研究层（`PA_SHADOW_DB=1` 时）

| 数据源名称 | 采集模块 | 文件路径 | 记录规模 | 分类 |
|-----------|----------|----------|----------|------|
| HMM Regime | `runtime/regime_hmm.py` | `data/regime_states.json` | 23 序列 | Regime |
| GARCH 波动率 | `runtime/garch.py` | `data/volatility_states.json` | 23 序列 | Volatility |
| 协整候选 | `runtime/cointegration.py` | `data/correlation_signals.json` | 7 对 | Polymarket |
| Regime 有效性 | `runtime/regime_effectiveness.py` | `data/regime_effectiveness.json` | 1 bucket | Regime |
| 仓位建议 | `runtime/position_sizing.py` | `data/sizing_suggestions.json` | 7 条 | Other |
| 规则权重建议 | `runtime/rule_weights.py` | `data/rule_effectiveness.json` | 6 条 | Other |
| 研究假设 | `runtime/hypothesis.py` | `data/hypotheses.jsonl` | 582 行 | Market Intelligence |
| 复盘 | `runtime/postmortem.py` | `data/postmortems.jsonl` | 13 行 | Polymarket |

> 上述产物均标注 `enforced=False`（协整/仓位/权重需 env 门控才进信号链）。

### 1.3 历史归档（一次性 / 批量）

| 数据源名称 | 采集模块 | 路径模式 | 记录规模 | 分类 |
|-----------|----------|----------|----------|------|
| OKX 小时 K 线 | `collectors/historical_data_collector.py` | `data/historical/okx_*_klines_*.json` | 136–744 bars/文件 | Crypto |
| OKX 资金费率历史 | 同上 | `data/historical/okx_*_funding_rate_*.json` | 87–93/文件 | Funding |
| 美股历史 | `enhanced_historical_collector.py` | `data/historical/us_stocks_*.json` | 3–10 标的 | US Stocks |
| 商品历史 | `alpha_vantage_collector.py` | `data/historical/commodities_*.json` | ~1.2 MB | Commodity |
| 外汇历史 | collectors | `data/historical/forex_may_2026.json` | 6 对 | Forex |
| 港股 / A 股 | `tencent_stocks_collector.py` 等 | `hk_stocks_*.json`, `cn_stocks_*.json` | MB 级 | US Stocks / Other |
| PM 历史市场 | collectors | `data/historical/polymarket_markets_*.json` | 0–13 市场/文件 | Polymarket |

### 1.4 跨项目 Observation（读取，非本项目写入）

| 数据源名称 | 来源项目 | 路径 | 记录规模 | 分类 |
|-----------|----------|------|----------|------|
| OKX 周度成交 | okx_perp_trader | `shared_intelligence/trades/okx_weekly.jsonl` | 952 行 | Crypto |
| US ETF 周度成交 | us-lev-etf-cta | `shared_intelligence/trades/us_etf_weekly.jsonl` | 38 行 | ETF |
| 事件回放集 | shared hub | `shared_intelligence/history/replay_dataset.jsonl` | 346 行 | Macro / MI |
| 日频市场条 | shared hub | `shared_intelligence/history/markets/*.json` | ~1,600 日/资产 | ETF / Crypto |
| OKX explore memory | okx_perp_trader | `okx_trade_memory_sample.jsonl` | 92,575 行 | Crypto |
| PM 周度导出 | 本项目 export | `shared_intelligence/trades/polymarket_weekly.jsonl` | 48 行 | Polymarket |

### 1.5 配置但未写入的数据源

| 名称 | 配置位置 | 状态 |
|------|----------|------|
| `whale_wallets` | `config/system_config.json` | Agent H 读取 `whale_trades`，**无 collector 写入** |
| `noaa` | system_config | 未实现 |
| `onchain` | system_config | 未实现 |

---

## 第二部分 — Agent 实际使用情况

### Agent A（采集）

| 维度 | 内容 |
|------|------|
| **读取** | Polymarket Gamma API、Google RSS、FRED CSV、OKX funding API、`okx_collector` 子进程 |
| **使用字段** | markets 全字段；RSS 全文；DFF 利率；BTC funding |
| **输出** | `data/latest_data.json`（保留 `us_stocks` 等 collector 字段） |
| **决策角色** | 上游采集；**不消费**其他数据做交易判断 |

### Agent B（主信号源）

| 维度 | 内容 |
|------|------|
| **读取** | `latest_data.json`（`polymarket_markets`）、`learned_rules.json` |
| **使用字段** | `question/slug/outcomes/outcome_prices/liquidity/volume/end_date`；`fed_rate`；`btc_funding_rate` |
| **未使用** | `google_news`、`us_stocks`、`okx` 全量、`multi_exchange_*`、commodity/forex |
| **输出** | `intelligence_report.json` → consolidate → `signals.json` |
| **决策角色** | **唯一稳定进入 Agent M 的信号生产者** |

### Agent D（无风险套利）

| 维度 | 内容 |
|------|------|
| **读取** | `latest_data.polymarket_markets`（yes/no price, volume） |
| **输出** | append `signals.json` |
| **决策角色** | ⚠️ **写入但被 consolidate 覆盖**（B 有信号时） |

### Agent E（BTC 滞后）

| 维度 | 内容 |
|------|------|
| **读取** | PM BTC 市场 + `get_okx_btc_context()`（spot price） |
| **使用字段** | `question`, `yes_price`, `no_price`, `volume`, BTC spot |
| **输出** | append `signals.json` |
| **决策角色** | ⚠️ 同上，**极少到达 M** |

### Agent F（跨平台 OKX↔PM）

| 维度 | 内容 |
|------|------|
| **读取** | PM crypto 市场 + OKX BTC price + funding |
| **输出** | append `signals.json` |
| **决策角色** | ⚠️ 同上 |

### Agent H（鲸鱼跟单）

| 维度 | 内容 |
|------|------|
| **读取** | `latest_data.whale_trades[]` |
| **实际状态** | 字段 **从未被采集** → **恒空退出** |
| **决策角色** | ❌ 无效链路 |

### Agent J（交叉验证）

| 维度 | 内容 |
|------|------|
| **读取** | `latest_data.markets/news/btc_price`（**错误 key**）、`intelligence_report.opportunities`（**不存在**） |
| **实际状态** | Schema 漂移 → **恒空退出** |
| **决策角色** | ❌ 无效链路 |

### Agent K（价值 / 体育 NO）

| 维度 | 内容 |
|------|------|
| **读取** | `polymarket_markets` + 内嵌 `weak_teams` 字典 |
| **Bug** | 解析 `outcomePrices`（camelCase）但数据为 `outcome_prices` → 价格恒 0.5 |
| **输出** | append `signals.json` |
| **决策角色** | ⚠️ 大概率零信号 + consolidate 覆盖 |

### Agent M（风险审查）

| 维度 | 内容 |
|------|------|
| **读取** | `signals.json`、`risk_snapshot.json`、`learning_knowledge_base.json`、`review_cache` |
| **使用字段** | 信号全 JSON；exposure violations；VaR；correlations；`rejection_prompt_enhancement` |
| **未读取** | `latest_data`、`market_intelligence`、`regime_states`、`volatility_states`、historical |
| **输出** | `review_results.json`、`approved_signals.json` |
| **决策角色** | **买入审查闸门** |

### Agent P（持仓退出）

| 维度 | 内容 |
|------|------|
| **读取** | `pm-trader portfolio` CLI、`latest_data.polymarket_markets`、`market_price_history.json`、`strategy_config.json`、`positions_closed_registry.json` |
| **使用字段** | shares, pnl, entry/exit price；yes_price 回退；滚动波动 / trailing stop 阈值 |
| **未读取** | GARCH `volatility_states`、regime、us_stocks、OKX |
| **输出** | `sell_signals.json`、`positions.json` |
| **决策角色** | **卖出决策链** |

### Agent G（学习反馈）

| 维度 | 内容 |
|------|------|
| **读取** | `pm-trader history --limit 50`、`review_results.json` |
| **输出** | `learning_report.json`、`learning_knowledge_base.json` → **下轮 Agent M** |
| **未读取** | 市场采集数据、shared_intelligence |
| **决策角色** | **间接**影响 M（非当轮信号生成） |

### 编排层内非用户列出但影响决策的模块

| 模块 | 读取 | 进入决策？ |
|------|------|-----------|
| `RiskEngine` | `latest_data` PM 快照 + 3 个 historical 文件 + `positions.json` | ✅ → `risk_snapshot` → M |
| `regime_detector` | `latest_data`, `trade_log.json` | ❌ 仅 → `capital_allocation`（执行器不读） |
| `strategy_manager` | `learning_report`, positions | ⚠️ → `strategy_config` → **仅 P** |
| `capital_adapter` | `market_regime`, `strategy_config`, positions | ❌ 产出无人消费 |
| `market_intelligence` | PM orderbook | ❌ shadow |
| `runtime.cointegration` | `market_price_history`, `asset_price_history` | ⚠️ 仅 `PA_COINT_SIGNALS=1` |
| `runtime.enforcement` | `sizing_suggestions`, `rule_effectiveness` | ⚠️ 仅 `PA_ENFORCE_*=1` |

---

## 第三部分 — 数据利用率矩阵

完整 CSV：`research/data_utilization_matrix.csv`

图例：**✅** 使用 · **⚠️** 部分使用 / 写入但不到达决策 · **❌** 未使用 · **collect** 仅采集

| 数据源 ↓ \ Agent → | A | B | D | E | F | H | J | K | M | P | G |
|-------------------|---|---|---|---|---|---|---|---|---|---|---|
| polymarket_markets | collect | ✅ | ⚠️ | ⚠️ | ⚠️ | ❌ | ❌ | ⚠️ | ❌ | ✅ | ❌ |
| google_news | collect | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| fed_rate | collect | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| btc_funding_rate | collect | ✅ | ❌ | ⚠️ | ⚠️ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| okx_bundle (4 coins) | collect | ❌ | ❌ | ⚠️ | ⚠️ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| us_stocks | preserve | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| commodity / forex | collect | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| market_price_history | — | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ | ❌ |
| asset_price_history | write | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| market_intelligence | — | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| learned_rules | — | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| signals.json | — | via_B | ⚠️ | ⚠️ | ⚠️ | ❌ | ❌ | ⚠️ | ✅ | ❌ | ❌ |
| risk_snapshot | — | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ | ❌ | ❌ |
| learning_knowledge_base | — | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ | ❌ | write |
| strategy_config | — | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ | ❌ |
| regime_states (HMM) | — | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| volatility_states (GARCH) | — | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| correlation_signals | — | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| historical archive | — | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ⚠️ | ❌ | ❌ |
| shared_intelligence.* | — | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| whale_trades | — | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |

---

## 第四部分 — 浪费数据识别

### 已采集但从未进入任何决策链路

| 优先级 | 数据 | 分类 | 规模 | 浪费原因 |
|--------|------|------|------|----------|
| P0 | `google_news` | Market Intelligence | 每周期全文 | 零 consumer |
| P0 | `us_stocks`（实时） | US Stocks | 8 标的/周期 | 仅写入 `asset_price_history`，不进 B/M/P prompt |
| P0 | `market_intelligence.json` | Market Intelligence | ~100 profiles | orchestrator 明确 shadow |
| P0 | `commodity_forex` 实时 | Commodity/Forex | 空 | collector 跑但无数据 |
| P0 | Agent D/E/F/H/J/K 信号 | Polymarket | 每周期计算 | consolidate 覆盖 |
| P1 | `asset_price_history` | Crypto/US/Funding | 724 点 | 仅协整研究，默认不进链 |
| P1 | `regime_states` / `volatility_states` | Regime/Vol | 23 序列 | enforced=False |
| P1 | `correlation_signals` | Polymarket | 7 对 | PA_COINT_SIGNALS 默认关 |
| P1 | `capital_allocation.json` | Other | 1/周期 | 无 reader |
| P1 | `shared_intelligence` 全部 | 多类 | 1,300+ 行 | 仅 analytics 离线 |
| P2 | `data/historical/*` 大部 | 多类 | 37 文件 | 除 RiskEngine 3 文件外零消费 |
| P2 | `hk_stocks` / `cn_stocks` 历史 | Other | MB 级 | 零 consumer |
| P2 | `whale_trades` | Other | 0 | 配置启用但无 writer |

### 重点类别审计

| 类别 | 采集状态 | 进入决策链？ | 浪费程度 |
|------|----------|-------------|----------|
| **Commodity** | 实时空 + 历史 ~1.2MB | ❌ | **100%** |
| **Forex** | 实时空 + 历史 May 2026 | ❌ | **100%** |
| **Funding** | BTC 标量→B；全量 OKX/历史未用 | 部分 | **~70%** |
| **US Stocks** | 8 标的实时 + 历史 OHLCV | ❌（Agent 链） | **~95%** |
| **ETF** | 跨项目 38 行 | ❌ | **100%** |
| **Volatility** | GARCH 计算但不 enforced；P 用简单 vol | 部分 | **~60%** |
| **Regime** | HMM + LLM regime 均不进 M/B | ❌ | **~90%** |

---

## 第五部分 — Top 20 最有价值未利用数据

详见 `research/unused_data_opportunities.json`（含 `easiest_integration` / `potential_value` / `sample_completeness` 排序字段）。

| Rank | 数据源 | 最易接入 | 潜在价值 | 样本完整度 | Phase |
|------|--------|----------|----------|------------|-------|
| 1 | `latest_data.us_stocks` | ★★★ | 高 | 高 | A |
| 2 | `market_intelligence.json` | ★★★ | 高 | 高 | A |
| 3 | `google_news` | ★★★ | 中 | 高 | A |
| 4 | `asset_price_history.json` | ★★★ | 高 | 中 | A |
| 5 | `correlation_signals.json` | ★★★ | 高 | 中 | A |
| 6 | `regime_states.json` | ★★★ | 中 | 高 | A |
| 7 | `volatility_states.json` | ★★★ | 中 | 高 | A |
| 8 | OKX 全量 bundle | ★★★ | 高 | 高 | A |
| 9 | `okx_weekly.jsonl` | ★★★ | 高 | 高 | A |
| 10 | `us_etf_weekly.jsonl` | ★★★ | 中 | 低 | A |
| 11 | funding 历史文件 | ★★★ | 中 | 高 | A |
| 12 | us_stocks 历史 | ★★★ | 中 | 高 | A |
| 13 | `market_regime.json` | ★★★ | 低 | 高 | A |
| 14 | `capital_allocation.json` | ★★★ | 低 | 高 | A |
| 15 | sizing + rule_effectiveness | ★★★ | 中 | 中 | A |
| 16 | `replay_dataset.jsonl` | ★★ | 高 | 高 | B |
| 17 | `okx_trade_memory` 92k | ★★ | 高 | 高 | B |
| 18 | commodities 历史 | ★★ | 中 | 高 | B |
| 19 | forex 历史 | ★★ | 低 | 中 | B |
| 20 | whale/onchain/noaa | ★ | 中 | 无 | C |

---

## 第六部分 — 路线图（仅建议，不实施）

### Phase A — 低风险高收益（读已有数据，不改模型）

1. **Agent B prompt 扩展：** 注入 `us_stocks` 涨跌幅、`market_intelligence` 流动性/价差摘要、`google_news` 标题列表（截断）。
2. **修复无效 Agent：** `Agent J` schema 对齐（`polymarket_markets` / `signals`）；`Agent K` `outcome_prices` 键名；`Agent H` 补 whale collector 或下线。
3. **Consolidate 策略：** B 信号为主但 **merge** D/E/F 而非 replace；或按 `source` 分桶送 M。
4. **Agent M 上下文：** 只读附加 `regime_states.current_regime` + `volatility_states.risk_state` 进 prompt（不自动改判）。
5. **shared_intelligence 只读 Observation：** `okx_weekly` / `us_etf_weekly` 最近 N 笔摘要进 B（遵守不共享 Experience）。
6. **启用已有门控（观察模式）：** `PA_COINT_SIGNALS=1` + `EXECUTOR_DRY_RUN=1` 验证协整桥到达率。

### Phase B — 需要新增 Learning 层（仍非策略代码）

1. **事件窗特征：** `replay_dataset.jsonl` → 周期性 macro/earnings flag 写入 `latest_data` 衍生字段。
2. **OKX memory 聚合：** 92k explore 行 → 按 symbol/session 聚合为 Observation 摘要（非 experience atoms）。
3. **商品/外汇修复采集：** 修复 `commodity_forex_collector` 空数据；与宏观 replay 对齐。
4. **跨项目 ETF 观察：** US ETF 38 笔 → 主题风险共变提示（观察层）。

### Phase C — 需要新增模型

1. **Whale / onchain 管线：** 新 collector + 结构化 `whale_trades` + Agent H 重接。
2. **Funding 领先模型：** 历史 funding + PM crypto 市场滞后特征（研究模型，非直接交易规则）。
3. **多资产 Regime 融合：** 合并 LLM `market_regime` + HMM `regime_states` → 统一 Observation 标签供 M/P。

---

## 附录 — 利用率计算明细

### A. `latest_data.json` 字段利用率

| 字段 | 采集 | 进入 B prompt | 进入 M/P 链 |
|------|------|---------------|-------------|
| polymarket_markets | ✅ | ✅ | ✅（P 退出定价） |
| fed_rate | ✅ | ✅ | ❌ |
| btc_funding_rate | ✅ | ✅ | ❌ |
| okx (4 coins) | ✅ | ❌（仅标量 funding） | ❌ |
| us_stocks | ✅ | ❌ | ❌ |
| google_news | ✅ | ❌ | ❌ |
| multi_exchange_* | ✅ | ❌ | ❌ |
| commodity/forex | ✅（空） | ❌ | ❌ |
| polymarket_status | ✅ | ✅（降级逻辑） | ❌ |

**有效字段：3/10 ≈ 30%**

### B. 信号 Agent 到达 Agent M 有效率

| Agent | 本周期运行 | 到达 M（实测架构） |
|-------|-----------|-------------------|
| B | ✅ | **~100%**（consolidate 唯一源） |
| D/E/F/K | ✅ | **~0%**（B 有信号时） |
| H/J | ✅ | **0%**（数据/schema 断裂） |

### C. 研究层 vs 决策层

| 产物 | 每周期计算 | 默认进决策 |
|------|-----------|-----------|
| regime_hmm | ✅ | ❌ |
| garch | ✅ | ❌ |
| cointegration | ✅ | ❌（env 关） |
| position_sizing | ✅ | ❌（env 关） |
| hypothesis | ✅ | ❌（观察） |

---

## 审计方法

- 代码路径：`orchestrator.py`、`agents/agent_*.py`、`risk/risk_engine.py`、`runtime/*.py`
- 文件统计：`data/` 目录枚举、sqlite `runtime.db` 表计数、jsonl 行数
- 交叉验证：subagent 探索 + 本地 `sqlite3` / `python3` 计数
- **未修改**任何代码、配置、Agent、服务

---

*End of audit.*
