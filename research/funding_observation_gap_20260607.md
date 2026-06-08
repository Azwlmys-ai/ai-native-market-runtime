# Funding Observation Gap (Phase 3c)

**Audited:** 2026-06-07T05:21:19.469172+00:00

## Why n≈60

March+April 2026 only (~180 raw 8h settlements → ~60 unique calendar days after daily mean); ETH local JSON exists but Phase2/model_sandbox loaders historically scanned BTC glob only; SOL has no local JSON; OKX feather longer history approved_not_wired in catalog.

## Current Sources

### BTC
- Files: 2
- Raw rows: 180
- Daily points: 60
- Date range: 2026-03-01 → 2026-04-29

### ETH
- Files: 2
- Raw rows: 180
- Daily points: 60
- Date range: 2026-03-01 → 2026-04-29

### SOL
- Files: 0
- Raw rows: 0
- Daily points: 0

## OKX Feather (catalog approved_not_wired)

- `/Users/libo/okx_perp_trader/env_rule/user_data/data/okx/futures/BTC_USDT_USDT-1h-funding_rate.feather` (7346 bytes)
- `/Users/libo/okx_perp_trader/env_rule/user_data/data/okx/futures/ETH_USDT_USDT-1h-funding_rate.feather` (7322 bytes)

## Live Rolling
- BTC_FUNDING in asset_price_history: 38 points

## Extension Plan

- Wire okx_{BTC,ETH,SOL}_USDT_SWAP_funding_rate_*.json in all loaders (not BTC-only glob).
- Read okx.market.funding feather via catalog (optional pyarrow) for multi-month backfill.
- Extend collector date range beyond 2026-03/04; add SOL swap funding collection.
- Aggregate 8h → daily for cross-market lag (document settlement cadence).

## Catalog

- `pm.local.funding.historical`
- `okx.market.funding (existing, wire loaders)`
