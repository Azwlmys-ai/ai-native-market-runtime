# Event Calendar Audit

> Phase 2.1 — Hermes Quant Ecosystem  
> Generated: 2026-W23

## Scope

`/Users/libo/shared_intelligence/events/`

| File | Events | Data Quality | Action |
|------|--------|--------------|--------|
| `nfp_calendar.json` | 36 | **Rule-generated, high confidence** | Keep — first Friday 08:30 ET is deterministic |
| `fomc_calendar.json` | 24 | **Official Fed schedule** | Keep — sourced from federalreserve.gov |
| `cpi_calendar.json` | 36 | **Proxy — mid-month weekday** | **Replace** with BLS actual release dates |
| `earnings_calendar.json` | 84 | **Deprecated proxy** | **Do not use** for attribution |
| `earnings_actual_calendar.json` | 70 | **Verified dates** | **Primary** earnings source |
| `theme_mapping.json` | — | Design artifact | Active |

## Detail by Calendar

### NFP (`nfp_calendar.json`)

- **Source:** `rule:first_friday_0830_et`
- **is_actual:** `true` (schedule rule matches BLS release pattern)
- **Windows (v2):** pre=2h, post=24h
- **Replace?** No — algorithmic dates are industry-standard

### CPI (`cpi_calendar.json`)

- **Source:** `proxy:bls_mid_month`
- **is_actual:** `false`
- **Risk:** Attribution may join trades to wrong inflation window (±3–5 days)
- **Replace?** Yes — ingest BLS CPI release calendar 2024–2026

### FOMC (`fomc_calendar.json`)

- **Source:** `federalreserve.gov` published decision days
- **is_actual:** `true`
- **Windows (v2):** pre=4h, post=48h
- **Replace?** No — refresh quarterly when Fed publishes new year

### Earnings Proxy (`earnings_calendar.json`)

- **Source:** `proxy:quarterly_anchor` (Phase 2 builder)
- **is_actual:** `false`
- **Risk:** AVGO/NVDA dates can be off by 1–2 weeks → false multi-event joins
- **Replace?** **Removed from event_catalog loader** — kept on disk for audit only

### Earnings Actual (`earnings_actual_calendar.json`)

- **Source:** Per-ticker verification:

| Ticker | Primary Source |
|--------|----------------|
| AMZN, AVGO, META, TSLA | finance.yahoo.com/calendar/earnings |
| MSFT | historicalearnings.com + microsoft.com IR |
| NVDA, AAPL | investor.nvidia.com / wallstreethorizon.com |
| All | `research/earnings_actual_dates.py` (curated table) |

- **is_actual:** `true`
- **Windows:** pre=12h, post=72h
- **Replace?** Refresh after each earnings season; add reported EPS optional field later

## Loader Policy (Phase 2.1)

`analytics/event_catalog.py`:

1. Loads macro calendars (NFP, CPI, FOMC)
2. Loads **only** `earnings_actual_calendar.json` for earnings
3. **Skips** `earnings_calendar.json` proxy

## Recommended Replacements (Priority)

1. CPI → BLS official dates
2. PPI calendar (new)
3. Market series: VIX spike days, DXY, US10Y (new)
4. BTC ETF flow events (new)
5. Fed speaker calendar (new)
