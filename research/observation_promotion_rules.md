# Observation Promotion Rules

> Phase 2.1 — Governance for Learning Layer  
> **Observation ≠ Knowledge ≠ Production**

## Directory Layout

```
shared_intelligence/
├── observations/     OBS_YYYY_MM_DD_NNN.md   (raw, Unverified)
├── hypotheses/       HYP_YYYYMMDD_*.md       (candidate patterns)
└── insights/         INS_*.json + *.md       (validated, still non-trading)
```

## Pipeline

```
Observation  →  Hypothesis  →  Insight  →  (future) Production
     ↑              ↑              ↑
  auto-gen      sample≥10      sample≥30 + review
```

**Forbidden shortcut:** Observation → Production

## Stage Definitions

### Observation (`observations/`)

- **Trigger:** `observation_generator.py` — notable event-attributed trades
- **Status:** `Unverified`
- **Sample:** often 1
- **Use:** human-readable incident log (e.g. NFP window + MSTZ loss)

### Hypothesis (`hypotheses/`)

- **Trigger:** `observation_promoter.py`
- **Gate:** ≥ **10** trades sharing same `(themes, events, symbol)` key
- **Status:** `Candidate`
- **Use:** pattern worth tracking; still no strategy changes

### Insight (`insights/INS_*.json`)

- **Gate:**
  - ≥ **30** samples
  - Win rate differs from baseline by ≥ **5pp** (descriptive gate, not formal test)
  - Human statistical review required
- **Status:** `insight_candidate`
- **Use:** cross-market lesson documentation

### Production (out of scope)

- Requires explicit human approval + validation backtest
- Must never be auto-wired from Observation

## Automated Tooling

```bash
PYTHONPATH=. python3 analytics/observation_generator.py
PYTHONPATH=. python3 analytics/observation_promoter.py
```

## Review Checklist (Human)

Before promoting Insight → any trading discussion:

1. Sample size ≥ 30?
2. CPI/FOMC dates verified (not proxy)?
3. Earnings from `earnings_actual_calendar.json`?
4. Confounding themes separated (AI vs RATES)?
5. Out-of-sample window exists?

## Current Status (2026-W23)

- Observations: generated from weekly trade window
- Hypotheses: require expanded historical export (not just current ISO week)
- Insights: **none promoted** — insufficient sample depth
