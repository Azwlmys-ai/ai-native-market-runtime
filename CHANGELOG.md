# Changelog

All notable changes to this project are documented here.

Format based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

---

## [1.0-stable-observation] — 2026-06-10

### Added

- **Agent B Hedged Race V1** — `call_llm_hedged_race()` in `llm_helper.py`
  - T=0 Grok only; T=45s hedge DeepSeek Flash; 90s FIRST_COMPLETED deadline
  - Daemon-thread hedge so loser calls do not block subprocess exit
  - Per-run telemetry: `data/agent_b_race_stats.json`
- **Final Validation scripts**
  - `scripts/final_validation_run_24.sh` — parallel Paper + Cross Market + Crypto Beta
  - `scripts/collect_final_validation_cycle.py` — per-cycle telemetry
  - `scripts/summarize_final_validation.py` — 24-cycle merged summary
  - `scripts/validate_agent_b_hedged_race.sh` — 12-cycle Agent B validation
- **Cross Market Research V0** — independent brief cron (us-cn, cn-us)
- **Crypto Ecosystem Beta Attribution V0** — BTC-driven beta reports
- **Documentation**
  - `PROJECT_STATUS.md`, `ARCHITECTURE.md`, `CHECKPOINT_FINAL_VALIDATION.md`

### Fixed

- **Agent B LLM hang** — timeout rate reduced from ~83% to **0%** (24-cycle validation)
- **Subprocess hang on hedge** — non-daemon loser thread blocked orchestrator 180s kill; fixed with `_submit_daemon()`

### Validated

- **Final Validation 24/24** — Paper Loop + Cross Market + Crypto Beta parallel
  - Paper Loop: 24/24 exit=0
  - Agent B: 0% timeout, grok winner 24/24, hedge_triggered 2
  - Cross Market: 24/24 brief pairs
  - Crypto Beta: 24/24 report sets
  - Postmortems: 28 (≥25 target met)
  - No real trading path pollution
- **STATUS:** `STABLE OBSERVATION PHASE`

### Changed

- `agents/agent_b.py` — calls `call_llm_hedged_race()` instead of serial `call_llm_sync()`
- `orchestrator.py` — Agent B subprocess timeout 180s (buffer above race deadline)

---

## [0.9-beta] — 2026-06 (pre-hedged-race)

### Known issues (resolved in 1.0)

- Agent B Grok requests hung at 120s/180s orchestrator timeout
- Serial fallback never helped (subprocess killed before DeepSeek ran)
- signals/cycle dropped to ~7 on timeout cycles

---

## Earlier

See git history and phase documents:

- `PHASE0_CONTRACTS.md`, `PHASE3E`–`PHASE3I`, `PHASE4_LIVE_PROBE.md`, `PHASE5_ENFORCEMENT.md`
- `SESSION_STATE_*.md` for session checkpoints
