# Pre-Live Validation Plan

Date: 2026-05-09

Purpose: define the checks required before any real Polymarket order is allowed.

This document is a plan only. It does not approve real trading.

## Current Gate

Status: not approved for live trading.

Dry-run observation is complete enough to move to planning:

- Multiple dry-run cycles completed with exit code 0.
- Latest observed bucket pattern: `success=0`, `dry_run=2`, `simulated=0`, `failed=0`.
- Result statuses were all `dry_run`.
- `us_stocks` persisted in `data/latest_data.json`.
- Fresh observation found no timeout, schema, path, or import errors after the Python PATH fix.
- Smoke baseline remains `44 passed, 2 warnings`.

## Hard Rules

- Do not place real orders until the user explicitly approves the live probe step.
- Do not start containers during validation unless the user separately approves that action.
- Do not deploy.
- Do not modify `config/llm_config.json` keys.
- Do not run `main.py --mode once` for live validation without an explicit environment and risk checklist.
- Keep `EXECUTOR_DRY_RUN=1` for all pre-live checks except the final user-approved live probe.

## Phase 1: Environment And Dependency Lock

Goal: prevent a repeat of the Homebrew Python / missing dependency issue.

Checks:

1. Confirm the dry-run script pins the expected interpreter:
   `/Users/libo/.hermes/home/scripts/polymarket_arbitrage_script.sh`
2. Confirm child processes resolve `python3` to the dependency-bearing Python via PATH.
3. Run smoke with the pinned interpreter:
   `/usr/bin/python3 -m pytest tests/test_smoke.py -v`
4. Run one dry-run cycle through the script:
   `/Users/libo/.hermes/home/scripts/polymarket_arbitrage_script.sh`

Pass criteria:

- Smoke passes.
- Dry-run completes.
- `data/execution_results.json` has `success=0`.
- If `total > 0`, every result status is `dry_run`.
- No fresh `Traceback`, `ModuleNotFoundError`, timeout, schema, or path errors in the latest orchestrator cycle.

## Phase 2: Account And Tool Readiness

Goal: verify the trading tool can read state without placing orders.

Allowed commands:

- `pm-trader --help`
- `pm-trader balance`
- read-only market lookup commands, if supported by the installed `pm-trader`

Pass criteria:

- Commands are read-only.
- Authentication is valid.
- Balance output is parseable.
- No command places or cancels orders.

## Phase 3: Signal Quality Gate

Goal: prevent a live probe from using stale or low-quality signals.

Checks:

1. Inspect `data/approved_signals.json`.
2. Require no more than one candidate for the first live probe.
3. Candidate must have:
   - explicit `market_id`
   - explicit `direction`
   - explicit `price`
   - explicit `position_size`
   - Agent M approval in the current cycle
4. Reject signals that depend only on stale data or unverifiable market assumptions.

Pass criteria:

- Exactly one live-probe candidate is selected.
- Candidate rationale is written down before execution.
- User explicitly approves the chosen candidate.

## Phase 4: Risk Limits

These values must be confirmed by the user before live probe:

- First live probe count: 1 order maximum.
- First live probe notional: user-confirmed cap required.
- Daily maximum orders: user-confirmed cap required.
- Daily maximum loss: user-confirmed cap required.
- Stop condition: any failed, partial, unexpected, or unparseable execution stops validation.

Default recommendation until user decides:

- First live probe cap: minimum viable amount supported by `pm-trader` and Polymarket.
- Daily maximum orders during probe: 1.
- Daily maximum loss during probe: equal to the first-probe cap.

## Phase 5: User-Approved Live Probe

This phase is blocked until the user explicitly approves it.

Before running:

1. Re-run Phase 1 checks.
2. Re-run Phase 2 read-only account check.
3. Re-confirm selected signal and notional cap with the user.
4. Temporarily disable dry-run only for the single approved command path.

Pass criteria:

- Exactly one intended order is submitted.
- Result is recorded.
- No follow-up orders are automatically placed.
- `data/execution_results.json` and logs clearly separate live result from prior `dry_run` cycles.

## Phase 6: Post-Probe Review

Immediately after any approved live probe:

1. Inspect execution result and account state.
2. Confirm no unintended orders.
3. Confirm logs and data files are parseable.
4. Confirm learning/training inputs do not mix dry-run trades with live trades.
5. Decide whether to stop, revert to dry-run, or plan a second probe.

## Current Next Step

Run Phase 1 and Phase 2 only. Do not proceed to Phase 3 or beyond until the user asks for live-readiness review.
