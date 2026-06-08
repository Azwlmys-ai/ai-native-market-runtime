# Event Memory Gap Analysis

> Generated: 2026-06-06T04:02:47.061664+00:00

## 1. 当前事件库最大缺口

- **CPI 日历**仍为 `proxy:bls_mid_month` 近似日，非 BLS 官方发布日。
- **PPI / VIX / DXY / US10Y / BTC ETF Flows** 尚未入库（PRD Chapter 6 待建）。
- **Fed Speakers** 无结构化日历。
- 事件文件计数: `{'fomc_calendar.json': 24, 'cpi_calendar.json': 36, 'earnings_actual_calendar.json': 70, 'nfp_calendar.json': 36, 'earnings_calendar.json': 84}`

## 2. 哪类事件样本最少？

- 当前归因样本中最少事件类型: **NFP** (10 trades)
- 主题覆盖: `{'AI': 26, 'ENERGY': 5, 'SEMICONDUCTORS': 21, 'CRYPTO': 964, 'RATES': 10}`
- Earnings 实际日历已替换 proxy，但 OKX/BTC 与 AVGO 的直接重叠样本仍稀少。

## 3. 哪类事件最可能对 ETF 有影响？

- ETF 命中事件窗口的交易: **20**
- 预期高影响: **NFP / FOMC / CPI**（RATES/INFLATION）+ **AVGO/NVDA EARNINGS**（AI/SEMICONDUCTORS → SOXL/NVDL）
- 当前 ETF 主要命中: `{'AVGO_EARNINGS': 1, 'NFP': 1}`

## 4. 哪类事件最可能对 OKX 有影响？

- OKX 命中事件窗口的交易: **0**
- 预期高影响: **FOMC / CPI**（宏观波动）+ **NVDA EARNINGS**（BTC/ETH 联动）
- 当前 OKX 主要命中: `{}`

## 5. Observation 是否足够升级为 Hypothesis？

- Observations on disk: **19**
- Hypotheses: **0** | Insight candidates: **0**
- Multi-event trades: **4** | Event-attributed: **20**
- **结论:** 可进入 Hypothesis 候选（≥10 单事件样本）
- 升级为 **Insight** 需 ≥30 样本 + 人工统计复核（见 observation_promotion_rules.md）。

## Next Actions (non-trading)

1. 用 BLS/FRED API 替换 CPI proxy 日期
2. 入库 PPI + 市场宏观序列
3. 扩展 trade export 历史窗口（不只当前 ISO week）
4. 在 AVGO/NFP 同日窗口积累 ≥30 样本后复核 AI×RATES 交叉主题
