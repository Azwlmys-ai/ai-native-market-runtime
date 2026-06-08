# Observation Learning Snapshot (Phase 3)

**Generated:** 2026-06-07T05:09:13.880680+00:00  
**Principle:** Share Observation, not Experience  
**Entry:** `runtime.observation_learning.compute (parallel to model_effectiveness, not Agent G Experience)`

## Stable Correlations (observation only)

- **BTC ↔ ETH**: r=0.84108102078568, n=1617 (high)
- **QQQ ↔ BTC**: r=0.4338643010645598, n=1109 (high)
- **TQQQ ↔ BTC**: r=0.43275216025522667, n=1109 (high)
- **SOXL ↔ BTC**: r=0.36576557045501634, n=1109 (high)

## Insufficient Samples

- **BTC ↔ Funding**: n=60 — cross_market_pair_underpowered
- **BTC ↔ PM Crypto (replay proxy)**: n=0 — cross_market_pair_underpowered
- **Gold ↔ BTC**: n=50 — cross_market_pair_underpowered
- **DXY ↔ BTC**: n=0 — cross_market_pair_underpowered
- **US ETF indicators_5m**: n=0 — research_db_indicators_empty

## Continue Collecting

- [medium] **BTC ↔ Funding** → extend_observation_sampling
- [high] **BTC ↔ PM Crypto (replay proxy)** → pm_crypto_price_history + PM market match
- [medium] **Gold ↔ BTC** → extend_observation_sampling
- [high] **DXY ↔ BTC** → DXY daily series into catalog allowlist
- [high] **US ETF indicators_5m** → populate tsll_research.db indicators pipeline
- [medium] **market_intelligence profiles** → consume_shadow_profiles_in_observation_learning_only

## Model Research Candidates

### GARCH
- Priority: **high**
- Rationale: Volatility transmission + OKX hold-time dispersion + runtime vol states
- Experience forbidden: **True**

### HMM
- Priority: **high**
- Rationale: Regime shifts across BTC/ETH/ETF; existing regime_states table
- Experience forbidden: **True**

### PCA
- Priority: **medium**
- Rationale: Co-movement among QQQ/TQQQ/SOXL/ETF candle universe
- Experience forbidden: **True**

### COINTEGRATION
- Priority: **high**
- Rationale: BTC-ETH spread + ETF-BTC lead/lag; existing cointegration module
- Experience forbidden: **True**

## Runtime Observation

- market_prices rows: **5300**
- runtime_events rows: **11176**

## Prohibited

No trading signals. No writes to signals.json / review_results.json / learned_rules / rule_weights.
