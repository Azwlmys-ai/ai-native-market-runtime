# Theme Layer Design

> Phase 2.1 — Observation only. Learning ≠ Trading.

## Purpose

Upgrade cross-market learning from single events:

```
NFP / AVGO / NVDA  →  RATES / AI / SEMICONDUCTORS themes
```

Themes are **reusable** across ETF, OKX, and Polymarket adapters.

## Artifact

`/Users/libo/shared_intelligence/events/theme_mapping.json`

## Initial Themes

| Theme | Meaning |
|-------|---------|
| AI | Mega-cap tech / AI capex cycle |
| RATES | Labor + central bank policy |
| INFLATION | Price-level surprises |
| SEMICONDUCTORS | Chip & leveraged semi ETFs |
| CRYPTO | Digital asset perpetuals |
| ENERGY | EV / oil-adjacent exposure |

## Mapping Rules

### 1. Event → Theme

Macro labels map 1:1:

- `NFP` → RATES
- `FOMC` → RATES
- `CPI` → INFLATION

Earnings map by issuer:

- `NVDA_EARNINGS`, `AVGO_EARNINGS`, `META_EARNINGS`, `MSFT_EARNINGS`, `AMZN_EARNINGS`, `AAPL_EARNINGS` → AI
- `TSLA_EARNINGS` → ENERGY

### 2. Symbol → Theme (instrument exposure)

Examples:

- `SOXL`, `SOXS`, `NVDL` → SEMICONDUCTORS + AI
- `BTC`, `ETH`, `SOL` → CRYPTO
- `TSLL`, `TSLQ` → AI + ENERGY

### 3. Trade Theme Set

For each attributed trade:

```
themes = union(event_themes, symbol_themes)
```

Stored in `event_attributed_trades.jsonl` as `themes[]`.

## Attribution Flow

```
trades/*.jsonl
    + events/*.json (with pre/post windows)
    + theme_mapping.json
        ↓ event_joiner.py
event_attributed_trades.jsonl
        ↓ theme_attribution_report.py
insights/theme_attribution_report.md
```

## Future (Chapter 9)

- NLP theme tagging from news headlines
- Dynamic theme clusters (embedding-based)
- Theme × regime (HMM) interaction — still read-only

## Constraints

- No theme-based trade filters
- No theme-based risk overrides
- Themes inform **reports and memory**, not execution
