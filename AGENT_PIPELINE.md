# Agent Pipeline

This document records the current frozen pipeline. It is descriptive, not a request to expand the system.

## Active Runtime Pipeline

| Step | Component | Input | Output | Current status | Active |
|---:|---|---|---|---|---|
| 0 | `collectors/us_stocks_updater.py` | external market APIs/config | runtime stock data | connected as collector | Yes |
| 1 | `agents/agent_a.py` | market/news/weather sources | `data/latest_data.json` | connected | Yes |
| 2 | `agents/regime_detector.py` | market data | regime assessment | connected, LLM-dependent | Yes |
| 3 | `agents/strategy_manager.py` | learning report, positions | strategy config | connected | Yes |
| 4 | `agents/capital_adapter.py` | strategy/risk context | allocation guidance | connected, LLM-dependent | Yes |
| 5 | `agents/agent_b.py` | latest data, learned prompt context | `data/intelligence_report.json` | connected | Yes |
| 6 | `agents/agent_k_v2.py` | market data, rule database | value signals | connected, rule-based | Yes |
| 7 | `agents/agent_d.py` | market prices | no-risk arbitrage candidates | connected, LLM-dependent | Yes |
| 8 | `agents/agent_e.py` | Polymarket/OKX BTC data | BTC arbitrage signals | connected, LLM/API-dependent | Yes |
| 9 | `agents/agent_f.py` | OKX and market data | cross-platform signals | connected, LLM/API-dependent | Yes |
| 10 | `agents/agent_h.py` | wallet data | wallet-follow signals | connected, LLM-dependent | Yes |
| 11 | `agents/agent_okx_funding.py` | OKX funding data | funding-rate signals | connected, LLM/API-dependent | Yes |
| 12 | `agents/agent_j.py` | candidate signals and data sources | validation output | connected, LLM-dependent | Yes |
| 12.5 | orchestrator consolidation | agent signal files | `data/signals.json` | connected | Yes |
| 12.6 | `risk/risk_engine.py` | runtime market/position data | `data/risk_snapshot.json` | connected lightweight risk layer | Yes |
| 13 | `agents/agent_m.py` | `signals.json`, risk snapshot, learning KB | `review_results.json`, `approved_signals.json` | connected, cache enabled | Yes |
| 14 | buy execution path | approved signals | `execution_results.json` | dry-run guarded | Yes |
| 15 | `agents/agent_p.py` | positions, learning KB | position/sell review | connected | Yes |
| 16 | sell execution path | sell signals/positions | sell execution output | dry-run guarded | Yes |
| 17 | `agents/agent_g.py` | trade history, rejected signals | learning report and KB | connected, fallback learning enabled | Yes |
| 18 | `agents/agent_i.py` | logs/runtime files | health report | connected, LLM-dependent | Yes |

## Non-Active Or Experimental Agents

These files exist but are not part of the frozen orchestrator runtime:

| Component | Purpose | Current status | Active |
|---|---|---|---|
| `agents/agent_b_enhanced.py` | Agent B variant | experimental/legacy | No |
| `agents/agent_b_enhanced_v2.py` | Agent B variant | experimental/legacy | No |
| `agents/agent_b_optimized.py` | Agent B variant | experimental | No |
| `agents/agent_learning.py` | offline learning script | manual tool | No |
| `agents/agent_n.py` | load-balancer concept | redundant with Agent M cache/concurrency | No |
| `agents/agent_codex.py` | development code review gate | development workflow only | No |
| `agents/agent_cn_stocks.py` | China stock analysis | not wired into orchestrator | No |
| `agents/agent_validator.py` | strategy validation | manual tool | No |
| `agents/agent_vibe.py` | external strategy generation integration | not wired into orchestrator | No |
| `agents/agent_stock_trader.py` | stock trading path | not active | No |
| `agents/agent_okx_trader.py` | OKX trading path | not active | No |
| `agents/agent_p_stop_loss.py` | Agent P variant | not active | No |
| `agents/arbitrage_simulator.py` | simulation/backtest utility | not active runtime | No |
| `agents/historical_arbitrage_miner.py` | historical analysis utility | not active runtime | No |
| `agents/multi_platform_collector.py` | collector variant | not active runtime | No |

## Current Freeze State

- No new Agent should be added in this stage.
- No new model should be added in this stage.
- Orchestrator should remain stable and unexpanded.
- Runtime status is dry-run only.
