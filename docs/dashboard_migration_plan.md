# Dashboard Migration Plan

## Scope

- Source dashboard: `/Users/libo/look`
- Migrated dashboard: `dashboard/`
- Original `/Users/libo/look` remains untouched.
- Trading orchestration and strategy files are out of scope.

## Migration Steps

1. Copy `/Users/libo/look` into `dashboard/`.
2. Keep dashboard changes minimal during the first migration.
3. Replace runtime references to `/Users/libo/look` with paths relative to `POLY_ARB_ROOT` or the current project root when found.
4. Add a minimal Visualization Agent that only reads:
   - `data/signals.json`
   - `data/review_results.json`
   - `data/execution_results.json`
   - `logs/*.log`
5. The Visualization Agent only writes `data/visualization_state.json`.

## Validation

Run from `/Users/libo/.hermes/polymarket_arbitrage`:

```bash
python3 agents/agent_visualization.py
scripts/smoke_visualization.sh
cd dashboard && npm run build
```

## Boundary Notes

- No trading orders are submitted by the Visualization Agent.
- No parameters, signals, review results, execution results, orchestrator, or strategy files are modified.
- Dashboard should use `POLY_ARB_ROOT` for project-root discovery if future runtime integration needs filesystem access.
