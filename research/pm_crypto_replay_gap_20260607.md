# PM Crypto Replay Gap (Phase 3c)

**Audited:** 2026-06-07T05:21:19.509095+00:00

## Why PM Crypto replay n=0

shared.history.replay_dataset.jsonl holds earnings/macro event rows (QQQ_* returns), not PM crypto price tape; _load_pm_crypto_proxy filter (asset_class=crypto) matches 0 rows.

## Replay Dataset

- Path: `/Users/libo/shared_intelligence/history/replay_dataset.jsonl`
- Lines: 346
- Crypto proxy rows (current filter): **0**
- Sample keys: `event, event_class, date, theme, actual, expected, surprise, ticker, eps_actual, eps_expected, guidance, datetime_utc`

## Live Runtime Crypto Markets

- `540844` / `will-bitcoin-hit-1m-before-gta-vi-872-424` — 53 price points

## Live Price Tape (market_price_history.json)

- `540844` `will-bitcoin-hit-1m-before-gta-vi-872-424` — n=60, yes_range=[0.4925, 0.4925]

## Simulated Historical Crypto (anchor datasets)

- `btc_100k_april` — 1440h from `polymarket_extended_march_april_2026.json` (simulated_anchor_dataset_not_live_pm)
- `btc_50k_march` — 1440h from `polymarket_extended_march_april_2026.json` (simulated_anchor_dataset_not_live_pm)
- `eth_5k_april` — 1440h from `polymarket_extended_march_april_2026.json` (simulated_anchor_dataset_not_live_pm)
- `sol_200_april` — 1440h from `polymarket_extended_march_april_2026.json` (simulated_anchor_dataset_not_live_pm)
- `btc_100k_april` — 1440h from `polymarket_markets_march_april_2026.json` (simulated_anchor_dataset_not_live_pm)
- `eth_5k_april` — 1440h from `polymarket_markets_march_april_2026.json` (simulated_anchor_dataset_not_live_pm)
- `btc_50k_march` — 1440h from `polymarket_markets_march_april_2026.json` (simulated_anchor_dataset_not_live_pm)
- `sol_200_april` — 1440h from `polymarket_markets_march_april_2026.json` (simulated_anchor_dataset_not_live_pm)

## Extension Plan

- Build PM crypto daily returns from market_price_history.json (live) + historical sim anchors.
- Add replay row schema with asset_class=crypto OR dedicated pm_crypto_tape.jsonl.
- Match PM markets to BTC anchor for cross-market pair (not earnings replay).
