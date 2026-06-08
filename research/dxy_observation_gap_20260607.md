# DXY Observation Gap (Phase 3c)

**Audited:** 2026-06-07T05:21:19.516882+00:00

## Current State

- DXY.json in shared_intelligence/history/markets: **False**
- commodity_forex_collector DXY: **False**
- collectors/commodity_forex_collector.py fetches gold/oil/forex pairs; no DX-Y / UUP / trade-weighted USD index series collected today.
- forex_may_2026.json days: **6**

## USD Proxy Options

- USD/EUR inverse from forex_may_2026.json: n=6
- UUP ETF daily (not collected): n=0
- FRED DTWEXBGS / DXY Yahoo ^DXY: n=0

## Minimal Input Schema (if no DXY yet)

- Format: `jsonl_or_csv`
- Required: `date, close`
- Target: `/Users/libo/.hermes/polymarket_arbitrage/data/historical/dxy_daily.jsonl`
- Catalog ID: `macro.dxy.daily`
- Example: `{"date": "2026-01-02", "close": 103.45, "symbol": "DXY", "source": "yahoo^DXY"}`

## Extension Plan

- Add optional DXY/UUP daily collector → data/historical/dxy_daily.jsonl
- Register macro.dxy.daily in cross_project_data_catalog.json (read-only)
- Until then, use USD/EUR from forex as weak proxy with low confidence flag
