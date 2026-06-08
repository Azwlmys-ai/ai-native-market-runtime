# Funding Continuity (Phase 3e)

**Generated:** 2026-06-07T16:03:58.904471+00:00

## Audit

- Live collector: `orchestrator._record_market_prices → BTC_FUNDING in asset_price_history.json`
- Live symbols: `['BTC_FUNDING']`
- Live counts: `{'BTC_FUNDING': 60}`
- SOL status: **missing**
- Dedicated agent (not wired): `agents/agent_okx_funding.py exists but not wired to orchestrator main path`

## Export

- Output: `/Users/libo/.hermes/polymarket_arbitrage/data/historical/funding_rates.jsonl`
- Dedup key: `symbol+timestamp`
- Appended: **1**
- Total rows: **980**
- Per symbol: `{'BTC': 524, 'ETH': 456}`
- Missing (not fabricated): `[{'symbol': 'SOL', 'reason': 'no_local_json_or_feather', 'fabricated': False}]`

## Static sources

- data/historical/okx_*_USDT_SWAP_funding_rate_*.json
- okx_perp_trader feather *-funding_rate.feather (BTC/ETH)
