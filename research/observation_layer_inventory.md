# Observation Layer Inventory

**Phase:** 2 (Observation Layer)  
**Date:** 2026-06-07  
**Principle:** Share Observation, not Experience  
**Project:** `/Users/libo/.hermes/polymarket_arbitrage`

---

## 1. Executive Summary

| Layer | Location | Scale | Agent 消费 | 利用率 |
|-------|----------|-------|-----------|--------|
| Shared Intelligence Hub | `/Users/libo/shared_intelligence` | 84 files / ~1.9 MB | ❌ 无 runtime | ~0% (offline analytics only) |
| Runtime DB | `data/runtime.db` | 21.6 MB | ingest / shadow | ~35% |
| Latest snapshot | `data/latest_data.json` | 45 KB | A/B/E/F/P | ~60% |
| Historical archive | `data/historical/` | 37 files / ~12.6 MB | RiskEngine (3 files) | ~4% |
| Market Intelligence | `data/market_intelligence.json` | 86 KB | ❌ shadow only | **0%** |
| Risk snapshot | `data/risk_snapshot.json` | 6 KB | Agent M, live_probe | ~70% |
| Commodity/Forex sidecar | `data/commodity_forex_data.json` | 211 B (empty) | ❌ | **0%** |
| OKX trade memory (external) | catalog `okx.trade_memory.export` | 92,575 rows / 92 MB | ❌ → **Phase 2 wired** | 0%→research |
| US ETF SQLite (external) | `us-lev-etf-cta/.../etf_trader.db` | 3,366 candles | ❌ → **Phase 2 wired** | ~5%→research |

---

## 2. Shared Intelligence Hub

**Root:** `/Users/libo/shared_intelligence`  
**Updated:** 2026-06-06/07  
**Catalog:** `research/cross_project_data_catalog.json`

| Subdir | Files | Purpose | Consumed by |
|--------|-------|---------|-------------|
| `trades/` | 4 jsonl | Weekly closed-trade exports (OKX/ETF/PM) | `analytics/event_joiner`, `weekly_kpi` |
| `history/markets/` | BTC,ETH,QQQ,TQQQ,SOXL,SOXS | Daily bars 2022–2026 | replay pipeline, **Phase 2 cross-market** |
| `history/replay_dataset.jsonl` | 346 events | Cross-market replay | theme learning (offline) |
| `events/` | CPI/NFP/FOMC/earnings | Event calendars | event_joiner |
| `observations/` | 19 OBS markdown | Unverified notes | observation_promoter |
| `learning/` | patterns/hypotheses | **Experience-adjacent** | denylist for cross-import |
| `schemas/` | trade_record, event | Contract validation | catalog loader |

**Utilization:** Runtime agents **do not read** shared hub. Offline `analytics/` only.

---

## 3. Runtime DB (`data/runtime.db`)

**Size:** 21.6 MB | **Updated:** 2026-06-07 12:58

| Table | Rows | Observation type | Agent / module consumer |
|-------|------|------------------|-------------------------|
| `market_prices` | 5,300 | PM price series | cointegration, price_history |
| `runtime_events` | 11,176 | Event trace | replay scripts |
| `signals` | 615 | Signal persistence | datastore |
| `reviews` | 374 | M decisions | model_effectiveness |
| `paper_trades` | 3,867 | Paper ledger | Agent G, paper PnL |
| `regime_states` | 23 | HMM regime | regime_hmm (offline refresh) |
| `volatility_states` | 23 | GARCH vol | garch module |
| `correlation_signals` | 4 | Cointegration | cointegration bridge |
| `hypotheses` | 616 | Research hypotheses | Agent G (learning) |

**Utilization:** ~35% — quant tables populated but not all fed to agents.

---

## 4. `latest_data.json`

**Updated:** 2026-06-07 12:47 | **Size:** 45 KB

| Key | Content | Consumers | Utilization |
|-----|---------|-----------|-------------|
| `polymarket_markets` | 100 markets, prices, liquidity | A, B, D, E, F, H, J, K | ✅ High |
| `okx` | BTC spot/swap/funding | E, F, orchestrator | ⚠️ ~30% |
| `us_stocks` | US equity snapshot | collectors, RiskEngine | ⚠️ ~5% |
| `btc_funding_rate` | Scalar funding | E, F | ⚠️ ~30% |
| `polymarket_status` | stale/degraded flag | B (skip LLM) | ✅ |
| `commodity_forex` | — | ❌ not merged | **0%** |

Sidecar `commodity_forex_data.json` exists but **empty** (211 B).

---

## 5. `data/historical/`

**Files:** 37 | **Size:** ~12.6 MB | **Updated:** mostly 2026-05-06/07

| Category | Examples | Rows/bars | Consumer |
|----------|----------|-----------|----------|
| OKX klines | `okx_BTC_USDT_klines_*.json` | 1h bars | backtest (ad hoc) |
| OKX funding | `okx_BTC_USDT_SWAP_funding_rate_*.json` | 180 obs | **Phase 2 OKX summary** |
| Commodities | `commodities_march_april_2026.json` | gold 962 bars | RiskEngine, **cross-market** |
| Forex | `forex_may_2026.json` | 6 days | ❌ unused |
| US stocks | `us_stocks_march_april_2026.json` | daily | RiskEngine only |

**Utilization:** ~4% — RiskEngine reads 3 aggregated files only.

---

## 6. `market_intelligence.json`

**Updated:** 2026-06-07 12:47 | **Size:** 86 KB | **Phase:** shadow

- 100 market profiles with tier (S/A/B/C/D), tradability_score, liquidity/spread scores
- **Consumers:** None (orchestrator step 2.5 writes only)
- **Utilization:** **0%**

---

## 7. `risk_snapshot.json`

**Updated:** 2026-06-07 12:53 | **Size:** 6 KB

- Volatility per asset, correlations, VaR, theme exposure violations
- **Consumers:** Agent M (review prompt), live_probe (optional)
- **Utilization:** ~70%

---

## 8. Cross-Project Catalog (Phase 2)

**Loader:** `runtime/observation_catalog.py`  
**Policy:** read_only, allowlist required, schema validation, no write-back

| catalog_id | Status | Phase 2 action |
|------------|--------|----------------|
| `okx.trades.weekly` | active | ✅ `okx_observation_summary.json` |
| `okx.trade_memory.export` | approved_not_wired → **wired** | ✅ 92,575 rows summarized |
| `etf.trades.weekly` | active | referenced in ETF summary |
| US ETF SQLite | not in catalog (read-only sqlite) | ✅ `us_etf_observation_summary.json` |

**Denylist enforced:** experience_review, lessons, knowledge, learned_rules, rule_weights, etc.

---

## 9. Utilization Gap → Phase 2 Coverage

| Gap (pre-Phase 2) | Phase 2 mitigation |
|-------------------|-------------------|
| Commodity ~0% | Gold bars in cross-market report; catalog loader |
| Forex ~0% | Documented DXY gap; forex sidecar empty |
| US ETF ~5% | Full SQLite read (candles/signals/trades) |
| Funding ~30% | 180 historical funding obs + OKX summary stats |
| Market Intelligence 0% | Inventory + future Agent G observation feed |
| Shared Observation 0% | Catalog loader + OKX/ETF summaries |

---

## 10. Files Produced (Phase 2)

| Output | Path |
|--------|------|
| Inventory | `research/observation_layer_inventory.md` (this file) |
| OKX summary | `research/okx_observation_summary.json` |
| ETF summary | `research/us_etf_observation_summary.json` |
| Cross-market | `research/cross_market_discovery_report.md` |
| Builder | `research/build_observation_phase2.py` |
| Loader | `runtime/observation_catalog.py` |
