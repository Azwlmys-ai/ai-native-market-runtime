# Dry-Run Validation

This document summarizes the frozen validation state. It records observed dry-run behavior; it does not claim production readiness.

## 14h Dry-Run Result

Source: `reports/14h_dryrun_report.md`.

| Metric | Result |
|---|---|
| Runtime window | 2026-05-14 18:56 CST to 2026-05-15 around 09:00 CST |
| Duration | about 14 hours |
| Script cycle target | 56 cycles during extended run |
| Independent cycles after de-duplication | 51 |
| Per-cycle exit code | 0 |
| Real execution success | `success=0` throughout |
| Dry-run enforcement | enabled throughout |
| Monitor reset after audit | `scripts/monitor_2h.sh` restored to `TOTAL_CYCLES=8` |

The key safety result is that no real successful execution was recorded during the dry-run window.

## Current P0 + P1-0 Validation

The current single-cycle command:

```bash
EXECUTOR_DRY_RUN=1 PM_TRADER_PATH=/tmp/mock_pm_trader.sh venv/bin/python3 main.py --mode once
```

Confirmed:

- `main.py --mode once` exits with code 0.
- `data/execution_results.json` is refreshed.
- `execution_results.json` reports `success=0`.
- `results=[]` when no approved signals are present.
- `data/risk_snapshot.json` is generated.
- Agent G runs successfully under dry-run fallback conditions.
- `data/learning_report.json` is refreshed.
- `data/learning_knowledge_base.json` is refreshed.

## Retry And API Pressure

The 14h run showed API 429 rate-limit pressure late in the run, especially around Agent M. Retry behavior occurred and the pipeline continued, but the validation does not establish production-grade external API resilience.

The current freeze state accepts this as an observed limitation rather than expanding the architecture.

## Cache

Agent M cache is active. P0/P1 validation confirmed cache behavior, including hits/misses during dry-run. The cache helps reduce repeat review work, but it is not a substitute for production-grade risk controls.

## Risk Snapshot

RiskEngine is connected at orchestrator step 12.6 and writes:

```text
data/risk_snapshot.json
```

This is a lightweight runtime risk context. It is useful for review prompts and runtime visibility, but it is not an institutional quant risk system.

## Fallback Learning

Agent G now supports fallback learning when LLM calls fail. The dry-run fallback path is deterministic and based on:

- synthetic dry-run trades
- closed trade count
- win/loss count
- win rate
- total PnL
- best/worst closed-trade markets
- rejection reason distribution when available

Required flags are written:

```text
llm_available=false
fallback_used=true
dry_run=true
synthetic=true
```

## Safety Conclusion

The system is valid for frozen dry-run observation and documentation. It is not validated for real-money trading.
