# P2-0 Cross-Asset Data Audit

Date: 2026-05-15

Scope: diagnosis only. No runtime, Agent, orchestrator, dry-run, risk engine, learning logic, or look UI code was changed.

## Validation Command

```bash
venv/bin/python3 main.py --mode once
```

Result:

- Exit code: `0`
- Orchestrator cycle completed.
- Data collection stages did not fully run because subprocess agents/collectors failed on missing imports.
- `risk_snapshot.json` was refreshed successfully.

Key runtime failures from `logs/orchestrator_20260515.log`:

```text
us_stocks_updater: ModuleNotFoundError: No module named 'aiohttp'
agent_a: ModuleNotFoundError: No module named 'aiohttp'
regime_detector / strategy_manager / many LLM agents: ModuleNotFoundError: No module named 'openai'
```

Important observation: although the top-level command used `venv/bin/python3`, `orchestrator.py` starts child agents and collectors with bare `python3`. In this environment, that child interpreter does not have `aiohttp` / `openai`, so several data-producing stages fail before they can refresh files.

## 1. Data Source Inventory

| Data source | Code path | Current status | Data file | Notes |
|---|---|---|---|---|
| US stocks | `collectors/us_stocks_updater.py`, `collectors/finnhub_collector.py`, `collectors/polygon_collector.py` | ❌缺依赖/失败 | `data/latest_data.json` → `us_stocks`; also `data/finnhub_data.json`, `data/polygon_data.json` | Step 0 failed on `aiohttp` import. Existing `latest_data.us_stocks` has `source=finnhub`, `total_symbols=0`. `polygon_data.json` has stale 5-stock data from May 8. |
| Crypto / OKX | `collectors/okx_collector.py`, `agents/agent_a.py` | ⚠️有文件但本轮未刷新 | `data/okx_data.json`; `data/latest_data.json` → `okx` | Existing OKX file has BTC/ETH/BNB/SOL. Agent A failed before invoking OKX collector in this run. |
| Polymarket | `agents/agent_a.py` | ⚠️有旧数据但本轮未刷新 | `data/latest_data.json` → `polymarket_markets` | `polymarket_markets` has 100 items, but `polymarket_status=stale` and file timestamp is earlier than this audit run. |
| News | `agents/agent_a.py` | ❌缺依赖/失败 | `data/latest_data.json` → `google_news` | Agent A failed on import; current `google_news` is empty. |
| Bonds / rates | `agents/agent_a.py` FRED fetch | ❌缺依赖/失败 | `data/latest_data.json` → `fed_rate` | Agent A failed on import; current `fed_rate=[]`. |
| Commodities | `collectors/commodity_forex_collector.py`; historical files consumed by RiskEngine | ⚠️有代码/旧文件，未进入 active orchestrator refresh | `data/commodity_forex_data.json`; `data/historical/commodities_*.json`; `data/risk_snapshot.json` | `commodity_forex_data.json` exists but is stale from May 6. Collector default path still points to `/opt/data/polymarket_arbitrage` and is not called by `orchestrator.py`. RiskEngine uses historical commodity files and includes commodity keys. |
| Forex | `collectors/commodity_forex_collector.py` | ⚠️有代码/旧文件，未进入 active orchestrator refresh | `data/commodity_forex_data.json` | Existing file has 14 FX pairs, stale from May 6. Not read into `latest_data.json`; not called by orchestrator. |
| Risk snapshot | `risk/risk_engine.py` | ✅已采集/计算并写入 | `data/risk_snapshot.json` | Refreshed at `2026-05-15T14:51:02`. Contains 13 assets: OKX, US historical, commodities historical. |

## 2. Current Data Files

Observed after the validation run:

| File | Status | Important keys / counts |
|---|---|---|
| `data/latest_data.json` | ⚠️stale / not refreshed in this run | `polymarket_markets=100`, `polymarket_status=stale`, `google_news=""`, `fed_rate=[]`, `okx.data=4`, `us_stocks.total_symbols=0` |
| `data/market_data.json` | ❌missing | No unified cross-asset market file exists at this path. |
| `data/okx_data.json` | ⚠️exists, stale | BTC/ETH/BNB/SOL spot/perpetual/funding present; timestamp `2026-05-15T10:21:35` |
| `data/commodity_forex_data.json` | ⚠️exists, stale | 6 commodities, 14 FX pairs; timestamp `2026-05-06T14:13:07` |
| `data/finnhub_data.json` | ⚠️exists but empty stock payload | `status=success`, `total_symbols=0`, `failed_symbols=10` |
| `data/polygon_data.json` | ⚠️exists, stale backup source | `total_symbols=5`, timestamp `2026-05-08T17:00:26` |
| `data/risk_snapshot.json` | ✅fresh | `asset_count=13`, includes `okx:*`, `us:*`, `commodities:*` keys |

## 3. Per-Source Status Detail

### Stocks

Status: ❌缺依赖/失败 for current orchestrator run.

Evidence:

- `us_stocks_updater.py` failed before running because `collectors/finnhub_collector.py` could not import `aiohttp`.
- Existing `data/latest_data.json.us_stocks` is not useful as current multi-asset display data: source is `finnhub`, `total_symbols=0`, `stocks=[]`.
- `data/polygon_data.json` has a previous 5-symbol snapshot, but it is not the current unified runtime output.

Write target:

- intended: `data/latest_data.json.us_stocks`
- auxiliary: `data/finnhub_data.json`, `data/polygon_data.json`

### Commodities

Status: ⚠️有代码但未运行 in active pipeline.

Evidence:

- `collectors/commodity_forex_collector.py` exists and can write `commodity_forex_data.json`.
- It is not called by `orchestrator.py`.
- Its default base path is `/opt/data/polymarket_arbitrage`, which does not match the current project path.
- Existing `data/commodity_forex_data.json` is stale from May 6.
- RiskEngine does include commodity assets, but from historical files, not from a fresh commodity collector run.

Write target:

- `data/commodity_forex_data.json`
- historical commodity data indirectly feeds `data/risk_snapshot.json`

### Forex

Status: ⚠️有代码但未运行 in active pipeline.

Evidence:

- FX fetch code exists in `collectors/commodity_forex_collector.py`.
- Existing FX data has 14 pairs, but is stale from May 6.
- FX data is not merged into `latest_data.json`.
- RiskEngine currently does not include FX assets in `risk_snapshot.json`.

Write target:

- `data/commodity_forex_data.json`

### Bonds / Rates

Status: ❌缺依赖/失败.

Evidence:

- FRED rate fetch exists in `agents/agent_a.py`.
- Agent A failed before running due `aiohttp` import failure.
- Current `latest_data.json.fed_rate=[]`.

Write target:

- `data/latest_data.json.fed_rate`

### News

Status: ❌缺依赖/失败.

Evidence:

- Google News RSS fetch exists in `agents/agent_a.py`.
- Agent A failed before running due `aiohttp` import failure.
- Current `latest_data.json.google_news=""`.

Write target:

- `data/latest_data.json.google_news`

### Polymarket

Status: ⚠️old data retained, current refresh failed.

Evidence:

- Agent A has Polymarket fetch code.
- Agent A failed before running.
- `latest_data.json` contains `polymarket_markets=100`, but `polymarket_status=stale`.

Write target:

- `data/latest_data.json.polymarket_markets`

### OKX Crypto

Status: ⚠️existing data, current refresh did not run.

Evidence:

- `data/okx_data.json` exists and contains BTC/ETH/BNB/SOL.
- `latest_data.json.okx.data` contains 4 items.
- Agent A failed before it could invoke `collectors/okx_collector.py` in this run.

Write target:

- `data/okx_data.json`
- `data/latest_data.json.okx`

## 4. Does look Read These Files?

Checked read-only paths:

- `/Users/libo/look/app/api/runtime`
- `/Users/libo/look/app/api/dryrun`
- `/Users/libo/look/app/api/signals`
- `/Users/libo/look/app/api/agents-runtime`
- `/Users/libo/look/app/api/runtime-logs`

| look API | Files read | Cross-asset market data coverage |
|---|---|---|
| `app/api/runtime/route.ts` | `execution_results.json`, `approved_signals.json`, `agent_m_learned_rules.json`, orchestrator logs | ❌ Does not read `latest_data.json`, `okx_data.json`, `commodity_forex_data.json`, or `risk_snapshot.json`. |
| `app/api/dryrun/route.ts` | `review_results.json`, `execution_results.json`, logs | ❌ Does not read cross-asset market data. |
| `app/api/signals/route.ts` | `signals.json`, `review_results.json`, `execution_results.json` | ❌ Reads signal queue, not market data. |
| `app/api/agents-runtime/route.ts` | logs only | ❌ No market data. |
| `app/api/runtime-logs/route.ts` | logs only | ❌ No market data. |

Additional look observation:

- `app/components/MarketDataPanel.tsx` imports `mockOKXMarkets`, `mockPolymarkets`, `mockNewsEvents`, `btcPriceHistory`, `ethPriceHistory` from `app/data/mockMarkets.ts`.
- That mock data defines BTC/ETH/SOL-centric display content.
- This explains why the current large screen can show BTC/ETH/SOL even when the real upstream cross-asset files are stale or not read.

## 5. Why look Currently Only Shows BTC/ETH/SOL

The current display is primarily a look-side issue:

1. The visible market panel uses mock data from `/Users/libo/look/app/data/mockMarkets.ts`, not live `polymarket_arbitrage/data/*.json`.
2. The checked look APIs expose runtime status, dry-run stats, signals, and logs, but not cross-asset market data.
3. No checked API route reads:
   - `data/latest_data.json`
   - `data/okx_data.json`
   - `data/commodity_forex_data.json`
   - `data/risk_snapshot.json`
4. The mock market set is crypto-heavy and explicitly contains BTC/ETH/SOL.

However, this is not only a look problem: the upstream current run also failed to refresh several cross-asset sources.

## 6. Problem Attribution

Conclusion: **both sides have issues**, but at different layers.

### polymarket_arbitrage side

Issues:

- Child processes use bare `python3`; current child interpreter lacks `aiohttp` and `openai`.
- Agent A cannot run, so Polymarket, news, FRED rates, OKX refresh path, and latest_data merge do not refresh.
- US stocks updater cannot run because `aiohttp` import fails.
- Commodity/forex collector exists but is not integrated into orchestrator and has an old `/opt/data/polymarket_arbitrage` default path.
- There is no single fresh `data/market_data.json` unified cross-asset feed.

Working pieces:

- `risk_snapshot.json` refreshes.
- Historical OKX / US / commodity data is sufficient for RiskEngine to produce 13 assets.
- Older `latest_data.json`, `okx_data.json`, and `commodity_forex_data.json` contain partial cross-asset data.

### look side

Issues:

- Checked API routes do not read market data files.
- The visible market panel uses mock crypto/Polymarket/news data.
- Cross-asset assets from `risk_snapshot.json` or `latest_data.json` are not exposed to the UI through the checked API routes.

Working pieces:

- look can read `polymarket_arbitrage` runtime directory for review/execution/log data.
- Hardcoded paths point to the correct project data/logs directories for the routes checked.

## 7. Minimal Fix Suggestions

No fixes were applied in this audit.

Recommended minimal sequence:

1. **Fix polymarket_arbitrage runtime interpreter first.**
   - Ensure orchestrator child processes use the same venv interpreter as `main.py`, or ensure bare `python3` has required dependencies.
   - This is the first blocker because fresh data is currently not being produced.

2. **Verify Agent A and US stocks updater refresh files.**
   - Expected fresh outputs:
     - `latest_data.json.polymarket_markets`
     - `latest_data.json.google_news`
     - `latest_data.json.fed_rate`
     - `latest_data.json.okx`
     - `latest_data.json.us_stocks`
     - `okx_data.json`

3. **Decide whether commodity/forex belongs in P2 active pipeline.**
   - If yes, minimally wire the existing collector or explicitly generate a unified file.
   - Fix the collector base path before relying on it.

4. **Expose one read-only market-data API in look.**
   - Minimal look-side change should read existing files rather than invent UI:
     - `latest_data.json`
     - `okx_data.json`
     - `commodity_forex_data.json`
     - `risk_snapshot.json`
   - This can be a backend API-only change first; UI expansion can wait.

5. **Only after fresh upstream data exists, update look display mapping.**
   - Replace or augment mock BTC/ETH/SOL data with real API output.
   - Avoid broad dashboard redesign.

## 8. Next Side To Fix First

Fix **polymarket_arbitrage side first**.

Reason: look cannot reliably display cross-asset data that is stale, missing, or not refreshed. The immediate upstream blocker is the child-process interpreter/dependency mismatch causing Agent A and US stock collection to fail before writing current data.

After upstream produces fresh cross-asset files, fix look's read path so it consumes those files instead of crypto-only mock data.
