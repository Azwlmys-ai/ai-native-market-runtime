# Conversation Handoff

This file summarizes the prior Codex conversation so future sessions do not need the full chat history.

## What Was Audited

Codex performed a read-only scan of:

- Project files under `/Users/libo/.hermes/polymarket_arbitrage`
- Config files under `config/`
- Logs under `logs/`
- Data JSON files under `data/`
- Core orchestrator, agent, collector, and executor scripts

No code was modified during the audit.

## Key Findings

1. Many files hardcode `/opt/data/polymarket_arbitrage` and `/opt/data/home/.local/bin/pm-trader`, while the host path is `/Users/libo/.hermes/polymarket_arbitrage` and `pm-trader` exists at `/Users/libo/.hermes/home/.local/bin/pm-trader`.
2. `config/llm_config.json` and historical markdown files contain plaintext key material. User said Hermes gateway key handling is separate; do not change keys in this repair round.
3. `executors/signal_executor.py` has exception paths that reference `signal["signal"]`, but approved signals are flat dicts.
4. `executors/signal_executor.py` returns `status == "success"` for real success but previously counted only `"simulated"` as success.
5. Root `signal_executor.py` / `sell_executor.py` differ from `executors/` versions.
6. `data/historical_trades_100.json` is not JSON; it contains `pm-trader history` CLI error output mentioning unsupported `--format`.
7. Logs show previous `regime_detector.py` timeouts.
8. Logs show previous `us_stocks_updater.py` timeouts.
9. Logs show repeated A-share data loading failures.
10. Agent M has been very conservative; changes to its prompt should wait for backtesting.
11. `llm_helper.py` has hardcoded fallback logic while `llm_config.json` also has a `fallback_map`.
12. Logs and backups lack rotation/retention policy.

## Architecture Opinion

The system has a reasonable conceptual pipeline:

`Collectors -> Agents -> Agent M review -> approved signals -> Executors -> position management -> review/learning`

The main weakness is engineering topology rather than intelligence:

- Too many loose JSON handoffs without strict schema.
- Multiple entrypoints and duplicate executors.
- Weak state machine around order execution.
- Runtime path assumptions are environment-coupled.
- Learning should remain a sidecar until data and execution are stable.

Topology optimization should come after the repair plan.

## Current Repair Plan

The detailed repair plan is stored at:

`/Users/libo/.hermes/polymarket_arbitrage/FIX_PLAN.md`

It is currently titled:

`Polymarket Arbitrage 修复计划 (v3.1 — 终版)`

## 2026-05-08 Repair Progress

Completed offline repair items:

- P0-pre confirmed actual path: Hermes scheduled/script entry calls `main.py --mode once`, which imports root `orchestrator.py`; root orchestrator now reaches wrapper executors.
- P0 fixed executor exception paths, dry-run support, status counting, and quarantined corrupted `data/historical_trades_100.json`.
- Added `scripts/dump_pm_history.py` for validated pm-trader history JSON dumps.
- Added `tests/test_smoke.py`; installed `pytest`/`requests`/`aiohttp` in the user Python environment and `python3 -m pytest tests/test_smoke.py -v` passed (29 tests).
- P1 #5 changed root `signal_executor.py` and `sell_executor.py` into compatibility wrappers around `executors/`.
- P1 #1 added `_paths.py` and migrated core runtime path resolution.
- P1 #11 changed `llm_helper.py` to merge config fallback overrides while filtering placeholders.
- Added `agents/agent_codex.py` as a pre-release code review gate. It uses `agent_codex` in `config/llm_config.json`, writes review/gate JSON files, and posts a `code_review` message to Hermes shared `messages.json`.
- Added `docs/codex_review_request.example.json` as the request template.
- Hardened Agent Codex after Claude/Codex review: fail-closed on LLM/request/parse failures, preemptive blocked pending gate, atomic JSON writes, locked `messages.json` updates, request schema validation, tests in prompt/payload/gate/metadata, line-numbered file context, git-diff status tuple handling, and non-APPROVE `main()` exit code.
- Added `docs/agent_collab_handoff.md` for file-based Codex/Claude Code collaboration and context-budget rules.
- Calibrated Agent Codex file context limit to avoid always-blocking medium project files while retaining `[truncated]` fail-closed behavior.
- Controlled dry-run exposed remaining `/opt/data/polymarket_arbitrage` defaults in orchestrator main-chain agents; migrated `agent_a`, `regime_detector`, `strategy_manager`, `capital_adapter`, `agent_d`, `agent_e`, `agent_f`, `agent_h`, `agent_j`, `agent_i`, `agent_k_v2`, and `agent_okx_funding` to `_paths.get_base_dir()` / `PA_BASE_DIR` and `parents=True` directory creation.
- Installed `aiohttp` in the user Python environment so `us_stocks_updater` and `agent_a` can run on the host.
- `python3 -m pytest tests/test_smoke.py -v` now passes 29 tests.
- Final controlled dry-run command completed successfully:
  `EXECUTOR_DRY_RUN=1 PM_TRADER_PATH=/tmp/mock_pm_trader.sh python3 -c "from orchestrator import Orchestrator; Orchestrator().run_once()"`
- Final dry-run result: all orchestrator steps completed, and `data/execution_results.json` showed `total=2`, `success=0`, `dry_run=2`, `failed=0`.
- Agent Codex self-reviewed the path/dry-run fixes and returned `APPROVE`; `data/deployment_gate.json` has `status=open`.

Next planned item is Claude Code review of the temporary Codex implementation via `docs/agent_collab_handoff.md`, then either P2 runtime cleanup or topology refactor planning. Do not place real orders without explicit user approval.

## Recommended Next Session Prompt

Use this short prompt in the project:

> Read `docs/current_status.md`, `docs/conversation_handoff.md`, and `FIX_PLAN.md`. Continue from P0-pre. Do not start the container or place real orders.

Updated prompt for Claude Code review:

> Read `docs/agent_collab_handoff.md`, then review the Codex-temporary implementation and the final dry-run results. Do not start containers, deploy, or place real orders.
