# Architecture

**Project:** AI Native Multi-Agent Market Runtime  
**Phase:** STABLE OBSERVATION PHASE  
**Last updated:** 2026-06-10

See also: [SYSTEM_ARCHITECTURE.md](./SYSTEM_ARCHITECTURE.md) for the 18-step orchestrator pipeline.

---

## Layer Overview

```text
┌─────────────────────────────────────────────────────────────────┐
│                    TRADING LAYER (dry-run)                       │
│  orchestrator.py → agents → risk → execution → postmortems       │
└────────────────────────────┬────────────────────────────────────┘
                             │ file-based artifacts only
┌────────────────────────────┴────────────────────────────────────┐
│                    RESEARCH LAYER (isolated)                     │
│  Cross Market V0  │  Crypto Beta V0  │  Crypto Ecosystem audit   │
└─────────────────────────────────────────────────────────────────┘
```

Research layers **never write** trading guard paths (`signals.json`, `execution_results.json`, `paper_portfolio.json`, `approved_signals.json`).

---

## Agent B Hedged Race V1

### Problem

Grok (`grok-4-1-fast-reasoning`) requests occasionally hang beyond serial timeout. Increasing orchestrator timeout alone did not fix root cause.

### Solution

Hedged Race in `llm_helper.call_llm_hedged_race()`:

```text
T=0     Start Grok only (zero extra API cost on fast path)
T=45s   If Grok pending → start DeepSeek Flash (hedge)
T≤90s   FIRST_COMPLETED wins; loser runs on daemon thread
```

### Call path

```text
agents/agent_b.py
    └── llm_helper.call_llm_hedged_race(agent_id='agent_b', ...)
            ├── Phase 1: grok_future.result(timeout=45s)
            └── Phase 2: hedge + wait(FIRST_COMPLETED, deadline=90s)
```

### Telemetry

Each Agent B run appends to `data/agent_b_race_stats.json`:

- `grok_started`, `deepseek_started`, `winner`, `elapsed_sec`
- `hedge_triggered`, `timeout`, `signals_generated`

### Orchestrator boundary

- Orchestrator subprocess timeout: **180s** (buffer above 90s race deadline)
- Agent M/E/F route through `routing_agent_id()` → same model chain as Agent B (unchanged)

### Validation result (24 cycle)

| Metric | Value |
|--------|-------|
| timeout | 0/24 |
| winner | grok: 24 |
| hedge_triggered | 2 |
| p50 / p90 | 38.1s / 44.7s |

---

## Cross Market Layer

### Scope

Independent research cron — **not wired to trading scheduler**.

| Component | Path |
|-----------|------|
| Brief generator | `research/cross_market/brief_cron.py` |
| Shell wrapper | `scripts/cross_market_brief_cron.sh` |
| Reports | `shared_intelligence/research/cross_market_v0/reports/` |
| Status | `shared_intelligence/research/cross_market_v0/brief_cron_status.json` |

### Brief types

| Type | Description |
|------|-------------|
| `us-cn` | US close → CN open context |
| `cn-us` | CN close → US open context |

### Isolation guard

`TRADING_GUARD_PATHS` in `research/cross_market/paths.py` — brief cron verifies no mtime changes on trading files. When `CROSS_MARKET_PARALLEL_PAPER=1`, `orchestrator_status.json` changes are filtered (paper loop side effect, not brief write).

### Parallel validation mode

```text
final_validation_run_24.sh
    ├── orchestrator.py          (paper loop, background)
    ├── cross_market_brief_cron  (research, background)
    └── run_beta_audit.py        (research, background)
```

Final Validation: **24/24** us-cn + cn-us brief pairs generated.

---

## Crypto Beta Layer

### Scope

Read-only beta attribution — no trading dependencies.

| Component | Path |
|-----------|------|
| Attribution engine | `research/crypto_ecosystem/beta_attribution.py` |
| Runner | `research/crypto_ecosystem/run_beta_audit.py` |
| Results JSON | `shared_intelligence/research/crypto_ecosystem_v0/beta_attribution_results.json` |
| Reports | `shared_intelligence/research/crypto_ecosystem_v0/beta_attribution/` |

### Universe

| Role | Tickers |
|------|---------|
| Driver | BTC |
| Response layer | MSTR, COIN, WGMI, BLOK, IBIT, FBTC |

### Key metrics per asset

- OLS Beta, Up/Down Beta, Beta asymmetry
- Rolling β30 / β60 / β120
- Extreme-move implied returns

### Validation result (24 cycle)

**24/24** full report sets generated (beta_attribution_report.md + MSTR/COIN specials).

---

## Research / Trading Isolation

| Check | Result (Final Validation) |
|-------|---------------------------|
| Cross Market writes trading paths | **No** |
| Crypto Beta writes trading paths | **No** |
| Real pollution detected | **None** |
| Observed parallel artifact | `orchestrator_status.json` mtime (paper loop) |

---

## Data Flow (Observation Phase)

```text
Manual trigger or patrol script
        │
        ├─► orchestrator.py (dry-run paper cycle)
        │       └─► agent_b → hedged race → intelligence_report.json
        │
        ├─► cross_market_brief_cron.sh
        │       └─► shared_intelligence/.../reports/
        │
        └─► run_beta_audit.py
                └─► shared_intelligence/.../beta_attribution/
```

No continuous scheduler in observation phase.
