# Current Status

Project: `/Users/libo/.hermes/polymarket_arbitrage`

Primary plan: `../FIX_PLAN.md`

This project is a Hermes-installed Polymarket arbitrage system. The current work is repair-first, topology-later.

## Current Goal

Finish the repair plan in `FIX_PLAN.md` before changing the broader architecture.

## Immediate Next Step

P0/P1 offline repair and controlled dry-run startup are complete as of 2026-05-08:

- P0-pre entrypoint confirmation recorded in `FIX_PLAN.md`.
- #4/#3 executor exception and counting fixes completed.
- `data/historical_trades_100.json` quarantined.
- `EXECUTOR_DRY_RUN` and `PM_TRADER_PATH` support added.
- Smoke tests added; `pytest`/`requests`/`aiohttp` installed in the user Python environment and `python3 -m pytest tests/test_smoke.py -v` passed (29 tests).
- Root executors are now thin wrappers around `executors/`.
- Core runtime paths use `_paths.py`.
- LLM fallback map now merges config overrides and filters placeholders.
- Added `agents/agent_codex.py` as a pre-release code review gate. It reviews a Hermes session requirement plus changed files, writes `data/codex_review_results.json` and `data/deployment_gate.json`, and appends a `code_review` message to Hermes shared `messages.json`.
- Agent Codex gate was hardened and self-reviewed: fail-closed gate, atomic review/gate writes, locked shared-message writes, request schema checks, line-numbered file context, git-diff kind handling, and `main()` non-APPROVE exit code are covered by smoke tests.
- Controlled dry-run single cycle completed with `EXECUTOR_DRY_RUN=1` and `PM_TRADER_PATH=/tmp/mock_pm_trader.sh`; final run completed all orchestrator steps successfully and `data/execution_results.json` showed `success=0`, `dry_run=2`, `failed=0`.
- Main runtime agents used by `orchestrator.py:run_once()` now respect `_paths.get_base_dir()` / `PA_BASE_DIR` instead of defaulting to `/opt/data/polymarket_arbitrage`.

2026-05-09 Codex follow-up:

- Confirmed `main.py --mode once` imports root `orchestrator.Orchestrator` and calls the same `run_once()` path used by the controlled dry-run check.
- Ran `EXECUTOR_DRY_RUN=1 PM_TRADER_PATH=/tmp/mock_pm_trader.sh python3 main.py --mode once`; the scan completed successfully and `data/execution_results.json` showed `success=0`, `dry_run=2`, `simulated=0`, `failed=0`.
- Updated `/Users/libo/.hermes/home/scripts/polymarket_arbitrage_script.sh` to force `EXECUTOR_DRY_RUN=1`, support both `/opt/data/polymarket_arbitrage` and the host project path, and made it executable.
- Ran `/Users/libo/.hermes/home/scripts/polymarket_arbitrage_script.sh`; the scan completed successfully and `data/execution_results.json` again showed `success=0`, `dry_run=2`, `simulated=0`, `failed=0`.
- Checked scheduling: user crontab is absent; no Hermes/Polymarket launchd job was found. A Codex thread heartbeat named `Hermes dry-run observation` is active every 30 minutes for dry-run observation only.
- 2026-05-09 12:06 heartbeat exposed a PATH-sensitive Python issue: the script's bare `python3`/orchestrator subprocesses resolved to Homebrew Python 3.13, which lacked `aiohttp` and `openai`. The script now exports `PATH="/usr/bin:/bin:/usr/sbin:/sbin:$PATH"` and runs `/usr/bin/python3 main.py --mode once`; follow-up dry-run completed cleanly with `success=0`, `dry_run=2`, `failed=0`, and smoke remains `44 passed, 2 warnings`.
- 2026-05-09 dry-run observation completed multiple clean cycles after the PATH fix. The Codex heartbeat `Hermes dry-run observation` has been deleted to stop repeated observation runs.
- Added `docs/pre_live_validation_plan.md`. Current next step is Phase 1/2 only: environment/dependency lock and read-only account/tool readiness. Live probe remains blocked pending explicit user approval.
- 2026-05-09 Agent M #9 review found a cache-key issue and a stale `execution_results.json` issue. Codex completed the follow-up directly after user asked it to continue:
  - `review_cache.py` cache key now includes market identity and `position_size`.
  - `executors/signal_executor.py` now writes fresh zero-result execution output when no approved signals exist.
  - Smoke is now `49 passed, 2 warnings`.
  - Dry-run confirmed `approved=0/rejected=9` from Agent M fail-closed LLM connection errors now produces `execution_results.json` with `total=0`, `dry_run=0`, `failed=0`, `results=[]`.
- 2026-05-09 external-network dry-run confirmed the LLM connection errors were Codex sandbox-network related, not an Agent M logic/config failure. With network access, Agent M reviewed 9 signals, approved 5 and rejected 4. Vegas Golden Knights and the two NBA Finals extreme-YES signals were approved after position preprocessing to 19%. Execution stayed dry-run only: `success=0`, `dry_run=5`, `failed=0`.
- Do not place real orders until the user explicitly approves a separate real-trading validation plan.

2026-05-10 Codex E2E follow-up:

- Read the E2E audit in `docs/agent_collab_handoff.md` and implemented the highest-priority fail-closed fixes.
- `orchestrator.py` now bootstraps missing `data/positions.json` as `[]`.
- `orchestrator.py` now checks `data/signals.json` freshness before Agent M. Default max age is `7200` seconds and can be overridden with `SIGNAL_MAX_AGE_SECONDS`.
- If signals are missing, invalid, empty, or stale, `orchestrator.py` skips Agent M and buy execution, clears `data/approved_signals.json`, writes `data/review_results.json` with `status=skipped`, and writes fresh zero `data/execution_results.json` with `status=skipped`.
- `agents/agent_k_v2.py` and `agents/agent_j.py` now add `generated_at` to newly created signals.
- `agents/agent_i.py` now checks `agent_k_v2_YYYYMMDD.log` instead of the nonexistent `agent_k_YYYYMMDD.log`.
- Smoke baseline is now `/usr/bin/python3 -m pytest tests/test_smoke.py -q` → `53 passed, 2 warnings`.
- Safe dry-run wrapper verification completed on 2026-05-10 09:12-09:13. Because `signals.json` was stale (`age=318299s`, max `7200s`), Agent M and buy execution were skipped. Final files: `approved_signals.json=[]`; `execution_results.json` has `status=skipped`, `total=0`, `success=0`, `dry_run=0`, `failed=0`, `results=[]`.
- Residual non-trading issue: Agent P and Agent G still hit `ModuleNotFoundError: No module named 'pm_trader'` when invoking `/Users/libo/.hermes/home/.local/bin/pm-trader`; fix the pm-trader Python/PYTHONPATH/data-dir environment before live readiness.

2026-05-10 Codex runtime-environment follow-up:

- `_paths.py` now exposes `get_pm_trader_env()`, adding Hermes `pm_trader` site-packages to `PYTHONPATH` and defaulting `PM_TRADER_DATA_DIR` to `/Users/libo/.hermes/home/.pm-trader` when present.
- Agent P, Agent G, Agent P stop-loss, the canonical buy/sell executors, `orchestrator.py` balance reads, `orchestrator_realtime.py` history reads, and `scripts/dump_pm_history.py` now pass `get_pm_trader_env()` to pm-trader subprocesses.
- Agent P now persists the latest portfolio to `data/positions.json`; latest safe dry-run wrote 15 positions.
- Agent B now writes `logs/agent_b_YYYYMMDD.log`, including the no-Polymarket-data early exit.
- Smoke baseline is now `/usr/bin/python3 -m pytest tests/test_smoke.py -q` → `59 passed, 2 warnings`.
- Safe dry-run wrapper verification completed on 2026-05-10 14:06-14:08:
  - Agent M and buy execution were still skipped by stale-signal guard (`age=335978s`, max `7200s`).
  - `approved_signals.json=[]`.
  - `execution_results.json` has `status=skipped`, `total=0`, `success=0`, `dry_run=0`, `failed=0`, `results=[]`.
  - Agent P read 15 positions and wrote a fresh `positions.json`.
  - Agent G loaded 45 trade-history rows.
  - Agent B wrote a fresh log and no longer appears as `no_logs`.
  - No fresh `ModuleNotFoundError: No module named 'pm_trader'` occurred in the 14:08 cycle.
  - Remaining health issues are expected: `signals.json` is stale, and Agent M is stale because it was intentionally skipped.

Next planned item:

- Fix the data acquisition / signal regeneration path so a fresh `signals.json` can be produced; keep stale-signal guard active.
- Then decide whether to move to P2 runtime cleanup, topology refactor planning, or a separately approved live probe.
- Do not place real orders until the user explicitly approves a separate real-trading validation plan.

## Agent Codex Usage

Create `data/codex_review_request.json` from `docs/codex_review_request.example.json`, then run:

```bash
python3 agents/agent_codex.py --request data/codex_review_request.json
```

Release should proceed only when `data/deployment_gate.json` has `"status": "open"` and the Hermes/main-model discussion agrees with the review.

Latest Agent Codex self-check:

- `python3 agents/agent_codex.py --request data/codex_review_request.json`
- Result: `APPROVE`, `data/deployment_gate.json` has `"status": "open"`.

## Hard Rules

- Do not start the container until P0/P1 smoke tests pass.
- Do not place real orders during verification.
- Use `EXECUTOR_DRY_RUN=1` and, when needed, `PM_TRADER_PATH=/tmp/mock_pm_trader.sh`.
- Do not modify or rotate `config/llm_config.json` keys in this repair round.
- Prefer fixing the real runtime path first, then converge duplicate entrypoints with thin wrappers.
- Use new logs, not old logs, to judge whether P2 runtime issues still exist.

## Known Entrypoint Split

- `orchestrator.py` calls root `signal_executor.py` and root `sell_executor.py`; it has `run_once()` and is best for controlled one-cycle checks.
- `orchestrator_advanced.py` calls `executors/signal_executor.py` and `executors/sell_executor.py`; it runs an infinite loop.
- `orchestrator_realtime.py` also calls `executors/`.

## Existing Plan File

The detailed repair plan is already saved at:

`/Users/libo/.hermes/polymarket_arbitrage/FIX_PLAN.md`

For a new conversation, ask Codex:

> Read `docs/current_status.md` and `FIX_PLAN.md`, then continue from the next incomplete item.
