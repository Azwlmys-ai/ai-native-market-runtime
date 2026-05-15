# P2-1 Cross-Asset Runtime Data Pipeline Fix

Date: 2026-05-15

Scope: runtime data refresh fix only. No new Agent, no new model, no trade logic change, no dry-run logic change, no risk-engine change, no learning-logic change, no README/GitHub/look UI change.

## 1. Modified Files

- `orchestrator.py`
- `agents/agent_a.py`
- `collectors/us_stocks_updater.py`
- `collectors/commodity_forex_collector.py`
- `collectors/alpha_vantage_collector.py`
- `collectors/collect_cn_stocks_no_proxy.py`
- `collectors/collect_cn_stocks_sina.py`
- `collectors/enhanced_historical_collector.py`
- `collectors/historical_data_collector.py`
- `collectors/tencent_stocks_collector.py`
- `reports/p2_1_cross_asset_runtime_fix.md`

## 2. Subprocess Runtime Fix

Problem:

- `orchestrator.py` launched child processes with bare `python3`.
- Running `venv/bin/python3 main.py --mode once` did not guarantee Agent/collector subprocesses inherited the same Python runtime.
- This caused earlier failures:
  - `ModuleNotFoundError: No module named 'aiohttp'`
  - `ModuleNotFoundError: No module named 'openai'`

Fix:

- Added `PYTHON_BIN = sys.executable` in `orchestrator.py`.
- Replaced orchestrator subprocess calls from `["python3", ...]` to `[PYTHON_BIN, ...]`.
- Updated `agents/agent_a.py` OKX collector subprocess to use `sys.executable`.

Validation:

```bash
venv/bin/python3 main.py --mode once
```

Result:

- Exit code: `0`
- Latest run no longer shows `ModuleNotFoundError: aiohttp`.
- Latest run no longer shows `ModuleNotFoundError: openai`.
- Agent A, us stocks updater, and LLM-dependent agents entered runtime execution successfully.

## 3. Collector Path Fixes

Removed old `/opt/data/polymarket_arbitrage` defaults from collectors in scope.

Collectors now use project-local path resolution through `_paths.get_base_dir()`:

- `collectors/commodity_forex_collector.py`
- `collectors/alpha_vantage_collector.py`
- `collectors/tencent_stocks_collector.py`
- `collectors/historical_data_collector.py`
- `collectors/enhanced_historical_collector.py`
- `collectors/collect_cn_stocks_no_proxy.py`
- `collectors/collect_cn_stocks_sina.py`

Validation:

```bash
rg -n "/opt/data/polymarket_arbitrage|\\[\\\"python3\\\"" orchestrator.py main.py agents/agent_a.py collectors -S
```

Result: no matches.

## 4. Cross-Asset Data Refresh Results

Final full validation command:

```bash
venv/bin/python3 main.py --mode once
```

Run completed at `2026-05-15 15:18:22`.

### Output mtimes

```text
May 15 15:14:48 2026 data/latest_data.json
May 15 15:14:02 2026 data/us_stocks_cache.json
May 15 15:14:33 2026 data/commodity_forex_data.json
May 15 15:14:48 2026 data/okx_data.json
May 15 15:15:53 2026 data/risk_snapshot.json
May 15 15:16:03 2026 data/execution_results.json
May 15 15:15:53 2026 data/signals.json
May 15 15:16:01 2026 data/review_results.json
```

### Data source status

| Source | Status | File | Result |
|---|---|---|---|
| US stocks | ✅ refreshed and non-empty | `data/latest_data.json`, `data/us_stocks_cache.json` | `source=finnhub`, `total_symbols=10`, `stocks_len=10` |
| Polymarket | ✅ refreshed | `data/latest_data.json` | `polymarket_status=ok`, `polymarket_markets=100` |
| News | ✅ refreshed | `data/latest_data.json` | `google_news_len=131969` |
| Bonds / rates | ✅ refreshed | `data/latest_data.json` | `fed_rate=['2026-05-13', '3.63']` |
| OKX crypto | ✅ refreshed and non-empty | `data/okx_data.json`, `data/latest_data.json` | BTC/ETH/BNB/SOL spot/perp/funding present |
| Commodity | ✅ refreshed and non-empty | `data/commodity_forex_data.json` | 5 assets: gold, silver, oil_wti, natural_gas, copper |
| Forex | ✅ refreshed and non-empty | `data/commodity_forex_data.json` | 14 FX pairs |
| Signals | ✅ refreshed | `data/signals.json` | 3 new signals from `agent_b` |

## 5. `latest_data.json` Update

`latest_data.json` was updated in the final run:

```text
timestamp: 2026-05-15T15:14:48.417137
polymarket_status: ok
polymarket_markets: 100
google_news_len: 131969
fed_rate: ['2026-05-13', '3.63']
btc_funding_rate: 4.871630818e-06
okx_symbols: BTC, ETH, BNB, SOL
us_stocks.total_symbols: 10
```

## 6. Remaining Failures

The cross-asset data refresh objective is satisfied, but these non-P2-1 issues remain:

1. `Agent P` still fails:

```text
AttributeError: 'list' object has no attribute 'get'
```

Observed at `agents/agent_p.py`, caused by strategy config shape mismatch around `take_profit_range`. This was not modified because P2-1 forbids unrelated runtime/trading logic changes.

2. `Agent G` timed out in the external full run:

```text
agent_g 执行超时
```

This appears related to real LLM call latency in the non-sandbox run. Learning logic was not modified in this task.

3. Yahoo Finance commodity endpoint returned HTTP 403.

Mitigation added:

- Commodity collector now falls back to Stooq for real commodity quotes.
- Current output is non-empty with 5 commodity assets.

4. Brent oil was not available from the tested Stooq symbols.

Current commodity file still includes non-empty commodity coverage via gold, silver, WTI oil, natural gas, and copper.

## 7. Risk Snapshot

`risk_snapshot.json` was refreshed in the final run:

```text
timestamp: 2026-05-15T15:15:53.132601
data_available: True
asset_count: 13
```

Assets included:

```text
okx:BTC-USDT
okx:ETH-USDT
okx:SOL-USDT
okx:BNB-USDT
us:ARKK
us:CRSP
us:TSLA
commodities:gold
commodities:silver
commodities:oil_wti
commodities:oil_brent
commodities:natural_gas
commodities:copper
```

Note: RiskEngine was not modified. It uses the existing historical series loader and now runs after fresh cross-asset collectors complete.

## 8. look Next Read Targets

look was not modified in P2-1.

Next, look should stop relying on mock/static BTC/ETH/SOL data and read these real runtime files:

- `data/latest_data.json`
  - `polymarket_markets`
  - `google_news`
  - `fed_rate`
  - `btc_funding_rate`
  - `okx`
  - `us_stocks`
- `data/okx_data.json`
- `data/commodity_forex_data.json`
- `data/risk_snapshot.json`
- optional status context:
  - `data/signals.json`
  - `data/review_results.json`
  - `data/execution_results.json`

Recommended P2-2 scope: add a read-only look API/data adapter for these files before changing UI layout.

## 9. Dry-Run Safety

Dry-run logic was not modified.

Final full run had:

```text
execution_results.success = 0
execution_results.total = 2
result statuses = ['failed', 'failed']
```

No successful real execution was recorded. The final command was not run with `EXECUTOR_DRY_RUN=1`; however, P2-1 did not change the dry-run controls or execution logic.

## 10. P2-2 Recommendation

Yes, enter P2-2 after reviewing this local validation.

Recommended P2-2 name:

```text
look real data integration
```

Boundary:

- read real cross-asset runtime files
- avoid dashboard redesign
- do not change trading/runtime behavior
- first implement a read-only API adapter, then map existing UI panels to real data
