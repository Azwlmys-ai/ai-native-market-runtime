# Agent Collaboration Handoff

Purpose: file-based handoff between Codex and Claude Code for this Hermes project.

Rules:
- Codex role: review, define tasks, verify results, and update this file with the next request.
- Claude Code role: implement the requested patch, run offline tests, and write results back here.
- Do not start containers, deploy, or place real orders.
- Do not modify `config/llm_config.json` keys.
- Prefer touching only files listed in the active task.
- After each implementation, Claude Code updates "Claude Result" and leaves questions under "Needs Codex".
- After each review, Codex updates "Codex Review" and either marks task complete or writes the next task.

Context budget rules for Claude Code:
- Read this handoff first, then read only files listed under "Allowed files" unless blocked.
- Do not rescan the whole repository unless the active task explicitly asks for it.
- Keep tool output short: use targeted `sed`/`rg`, not broad dumps.
- Before making edits, restate the minimal plan in 3–6 bullets.
- After finishing one active task, write a compact result back to "Claude Result" and stop.
- If context is getting large or several handoff rounds have accumulated, make this file self-contained, compress completed history, and continue from a fresh Claude Code session.
- Prefer one small patch per round. Do not batch unrelated improvements.

---

## Project State (as of 2026-05-09)

**Completed fixes:**

| Priority | Item | Status |
|---|---|---|
| P0 | Executor exception/status counting fixes + `EXECUTOR_DRY_RUN` safety path | ✅ done |
| P0 | Corrupt `historical_trades_100.json` quarantined + validated history dump path added | ✅ done |
| P0 | Path migration core chain (8 files, `/opt/data` → `get_base_dir()`) | ✅ done |
| P0-pre | Orchestrator entry-point confirmed (`orchestrator.py` + `run_once()`) | ✅ done |
| P1 | Executor wrapper convergence (root thin wrappers → `executors/`) | ✅ done |
| P1 | LLM fallback wired in code (not dead config) | ✅ done |
| P2 #8 | `us_stocks_updater` 25 s total budget + per-source timeout + degraded fallback | ✅ done |
| P2 #8 follow-up | Agent A preserves `us_stocks` field when writing `latest_data.json` | ✅ done |
| P2 #10 | `agent_cn_stocks.py` path migration (`/opt/data` → `get_base_dir()`) | ✅ done |
| P2 #10 follow-up | `analyze_arbitrage()` coerces string `outcome_prices`; skips non-numeric | ✅ done |
| P2 #10 test | Smoke test strengthened: `change_pct=-4.0`, asserts 1 signal, `polymarket_price==0.61`, `polymarket_action=="SELL"` | ✅ done |
| P3 #12 | `scripts/rotate_logs.py` dry-run-first log rotation with gzip archive + collision-safe naming | ✅ done |
| Agent Codex gate | Hardening + self-check + `MAX_FILE_CHARS=30000` + `collect_git_diff()` fix | ✅ done |
| P2 #9 | Agent M: `classify_signal()` + `_preprocess_signal()` position-cap + strengthened whitelist prompt + offline backtest script + cache/empty-result follow-up | ✅ done |

**Deferred:**
- P2 #7 `regime_detector` — no fresh timeout evidence; defer until it shows up in logs.
- P3 #2 Key governance — user confirmed: not rotating this cycle.

**Smoke test baseline:** `49 passed, 2 warnings` (local env, after FIX_PLAN #9 + cache/empty-result follow-up).  
**Controlled dry-run:** Full cycle completes; `us_stocks` persists in `latest_data.json`; execution stays dry-run only.

**2026-05-09 Codex follow-up:**
- Confirmed `main.py --mode once` reaches `orchestrator.Orchestrator().run_once()`.
- Ran `EXECUTOR_DRY_RUN=1 PM_TRADER_PATH=/tmp/mock_pm_trader.sh python3 main.py --mode once`: completed successfully with `success=0`, `dry_run=2`, `simulated=0`, `failed=0`.
- Updated `/Users/libo/.hermes/home/scripts/polymarket_arbitrage_script.sh` to force `EXECUTOR_DRY_RUN=1`, work on host or container paths, and be executable.
- Ran `/Users/libo/.hermes/home/scripts/polymarket_arbitrage_script.sh`: completed successfully with `success=0`, `dry_run=2`, `simulated=0`, `failed=0`.
- User crontab is absent and no Hermes/Polymarket launchd job was found. Codex heartbeat `Hermes dry-run observation` is active every 30 minutes for observation only.
- 2026-05-09 12:06 heartbeat found a PATH-sensitive Python regression after VS Code/Homebrew PATH changes: bare `python3` resolved to Homebrew Python 3.13, missing `aiohttp`/`openai`. The dry-run script now exports `/usr/bin` first and invokes `/usr/bin/python3`; 12:27 follow-up dry-run completed cleanly with `success=0`, `dry_run=2`, `failed=0`, and smoke is still `44 passed, 2 warnings`.
- 2026-05-09 external-network dry-run confirmed Agent M #9 is working: `5 approved / 4 rejected`, Vegas Golden Knights and two NBA Finals extreme-YES signals approved after position cap to 19%, execution stayed dry-run with `success=0`, `dry_run=5`, `failed=0`.
- Real-order validation remains a separate future plan; do not place real orders.

---

## Active Task For Claude Code

Status: COMPLETE — Code audit found all P0/P1 fixes already implemented. Remaining gaps documented below.

Allowed files (this round):
- `orchestrator.py`
- `agents/agent_b.py`
- `agents/agent_k_v2.py`
- `agents/agent_i.py`
- `agents/agent_p.py`
- `tests/test_smoke.py`
- `docs/agent_collab_handoff.md`

Do not touch:
- `config/llm_config.json`
- `executors/`
- `collectors/`
- `logs/` real files
- container/deployment/trading runtime

Problem:
- Codex local verification of Claude's Agent M #9 patch passed initially:
  - `/usr/bin/python3 -m pytest tests/test_smoke.py -v` → `47 passed, 2 warnings`
  - `/usr/bin/python3 scripts/backtest_agent_m.py` → exits 0 and reports Vegas as the known FN
- Dry-run validation then showed Vegas still rejected with `position_size=0.285` and no `_original_position_size`.
- Root cause: `ReviewCache.calculate_signal_hash()` ignored `market_id`, `market_name`, and `position_size`, so the capped 19% signal could hit old cached review results.
- Codex made an interim patch:
  - `review_cache.py`: hash now includes `market_id`, `market or market_name`, and `position_size`.
  - `review_cache.py`: cache dir creation now uses `parents=True`.
  - `tests/test_smoke.py`: added `test_review_cache_key_includes_market_and_position`.
  - Smoke after patch: `/usr/bin/python3 -m pytest tests/test_smoke.py -v` → `48 passed, 2 warnings`.
- Follow-up dry-run after cache-key fix forced fresh Agent M LLM reviews. LLM API calls hit `API 错误: Connection error`, so Agent M fail-closed to `0 approved / 9 rejected`. This is safe, but it exposed a second runtime bug:
  - `approved_signals.json` became empty.
  - `SignalExecutor.run()` returns early when no signals exist and does not rewrite `data/execution_results.json`.
  - As a result, `data/execution_results.json` still showed stale previous `dry_run=2`, which misleads dry-run/live readiness checks.

Resolution:
- `review_cache.py` now uses `parents=True` for `data/review_cache` and includes `market_id`, `market or market_name`, and `position_size` in the cache key.
- `executors/signal_executor.py` now writes a fresh zero-result `data/execution_results.json` when no approved signals exist.
- `tests/test_smoke.py` now covers both cache-key sensitivity and empty-signal execution-result overwrite.
- `/usr/bin/python3 -m pytest tests/test_smoke.py -v` passes: `49 passed, 2 warnings`.
- `/usr/bin/python3 scripts/backtest_agent_m.py` exits 0.
- Dry-run script verification completed: Agent M fail-closed to `approved=0/rejected=9` due LLM connection errors, `approved_signals.json` was empty, and `execution_results.json` correctly refreshed to `total=0`, `success=0`, `dry_run=0`, `simulated=0`, `failed=0`, `results=[]`.
- No real orders placed; no container/deploy action.

Next request:
- None for Claude. Use a new session handoff if continuing.

---

## Claude Result

### Round: P1-2 + P1-3 修复 (2026-05-10)

**文件改动：**

`agents/agent_m.py`（P1-2 — review_result 顶层 market_id）：
- `review_signal()` 正常路径（line ~270）：加 `"market_id": signal.get("market_id"), "market_name": signal.get("market_name")`
- `review_signal()` 异常路径（except 块）：同上
- `_review_concurrent()` 异常路径（并发错误 fallback）：同上
- 三处修改统一，所有 review_result 条目的 `market_id`/`market_name` 现在在顶层直接可访问

`agents/agent_b.py`（P1-3 — 键名修正 + 无数据 early return）：
- `generate_enhanced_prompt()`: `latest_data.get('markets', [])` → `latest_data.get('polymarket_markets', [])`（修正错误键名）
- `main()`: 加 early return + 日志，当 `polymarket_markets` 为空时不进行无意义 LLM 调用

`tests/test_smoke.py` — 新增 2 个测试 + 辅助函数：
1. `_load_agent_m_module()` — 返回可注入 `call_llm_sync` 的 stub module
2. `test_agent_m_review_result_exposes_market_id_at_top_level` — 验证正常路径（APPROVE）和异常路径（REJECT）均有顶层 `market_id`/`market_name`
3. `_load_agent_b_module()` — agent_b stub loader
4. `test_agent_b_skips_when_no_polymarket_markets` — 验证 `polymarket_markets=[]` 时 LLM 不被调用，打印 early-exit 日志

**测试结果（sandbox）：**
- `-k "agent_m_review_result_exposes or agent_b_skips"`: **2 passed**
- 排除 openai 依赖测试后全套: **31 passed, 2 warnings**（2 个 openai 失败均是预存在问题）
- `py_compile agents/agent_m.py agents/agent_b.py tests/test_smoke.py`: SYNTAX OK
- 本地预期：**51 passed, 2 warnings**（原 49 + 新 2）
- 无容器启动；无真实下单；无 config/llm_config.json 修改

---

### Round: E2E 端到端审计 (2026-05-10)

**审计范围：** 只读，无代码修改，无下单。  
**审计对象：** `data/` 文件快照 + 最近一次 orchestrator 运行日志 (2026-05-10 08:25–08:27)。

---

#### 链路整体状态

| 步骤 | Agent | 状态 | 说明 |
|---|---|---|---|
| scan | Agent A | ❌ 失败 | Polymarket / OKX / Google News 全部采集失败；仅 us_stocks 成功 |
| lag | Regime Detector | ⚠️ 降级 | confidence=20，原因："所有数据为0或缺失" |
| lag | Agent K v2 | ⚠️ 无操作 | markets=[] → 不写 signals.json；May 6 旧信号静默保留 |
| lag | Agent B | ⚠️ 无操作 | exit 0 但未产生 agent_b 日志文件；intelligence_report = 0 signals |
| report | Agent J | ⚠️ 未知 | 对 3.7 天旧信号做交叉验证，结论可信度存疑 |
| paper | Agent M | ⚠️ 全缓存 | cache_stats: hits=9, misses=0 (100%)；LLM 未调用；决策来自上次缓存 |
| paper | SignalExecutor | ⚠️ 执行干跑 | dry_run=5，但执行的是 May 6 旧信号 |
| evaluate | Agent I | ⚠️ 降级 | 正确报告：signals.json stale + positions.json 缺失；误报：agent_k no_logs |

---

#### P0 阻塞项（live 交易前必须修复）

**P0-A — 信号过期未拦截（最高优先级）**
- `signals.json` mtime = May 6，age = 88h / 3.7 天。
- 当 Polymarket 采集失败时，agent_k_v2 和 agent_b 均提前返回且**不覆写** `signals.json`，导致旧信号原地保留。
- orchestrator 无任何年龄检查，Agent M 直接审查旧信号，executor 直接执行。
- 信号内无 `timestamp` 字段，下游无法程序化判断新鲜度。
- **修复方向：** ① 每条信号写入时加 `generated_at` 字段；② orchestrator 在 Agent M 步骤前检查 signals.json age，超过阈值（建议 2h）且无新鲜 Polymarket 数据时跳过执行并记录 `skipped` 原因。

**P0-B — `positions.json` 永久缺失**
- `data/positions.json` 不存在；Agent P（持仓管理）和卖出逻辑依赖此文件。
- 无持仓记录 = 无法计算 P&L、无法触发止损、无法生成卖出信号。
- **修复方向：** 在 orchestrator 启动时（或 Agent P 首次运行时）若文件缺失则自动创建空持仓文件 `{}`。

---

#### P1 问题（影响可靠性）

**P1-1 — Agent I 健康监控命名错配**
- `agent_i.py` 监控列表：`["a","b","d","e","f","g","h","j","k","m","p"]`
- 实际日志文件：`agent_k_v2_YYYYMMDD.log`（不是 `agent_k_YYYYMMDD.log`）
- 结果：每次 agent_k_v2 正常运行，agent_i 仍报告 `agent_k: no_logs`（误报）。
- **修复方向：** 将监控列表中 `"k"` 改为 `"k_v2"`。

**P1-2 — `review_results.json` schema 嵌套**
- `approved_signals[i]` 结构为 `{signal: {...}, decision: ..., reason: ...}`，`market_id` 在 `.signal.market_id` 层，直接访问 `.market_id` 返回 `None`。
- 任何直接读 `review_results.json` 并用 `.market_id` 的消费者会得到 `None`（当前 batch 9 条均为 None）。
- **修复方向：** 在写入 `review_results.json` 时将 `market_id` / `market_name` 提升到顶层；或统一文档规范为"必须从 `.signal.market_id` 读"。

**P1-3 — Agent B May 10 无日志**
- orchestrator 报告 `✅ agent_b 执行成功`，但 `logs/agent_b_20260510.log` 不存在。
- May 6 最后一次成功日志显示 agent_b 写日志依赖有效数据路径；Polymarket 数据缺失时可能走了不写日志的早返回分支。
- **修复方向：** agent_b.py 无论走哪个分支都应写日志（即使是"无数据，跳过"一行）。

---

#### 观察项（不阻塞，但需关注）

- **经济陈旧性**：dry_run=5 执行了 NHL/NBA 信号，但价格和赔率可能在 3.7 天内已显著变化。不影响安全性（dry-run），但回测/学习样本会被污染为旧价格的"决策"。
- **EV 数量级异常**：approved_signals 中 NBA Finals YES EV=11661%，76ers EV 类似。超大 EV 是信号生成逻辑问题（历史 issue），非本次审计新发现，但应纳入信号质量过滤。
- **market_regime confidence=20**：制度识别等于盲猜，position_size_multiplier 仍是 1.0（未降级）。当数据全缺失时 multiplier 应该降为 0 或走保守模式。

---

#### 数据快照时间戳对齐

| 文件 | mtime | 内容时间戳 | 同批次？ |
|---|---|---|---|
| latest_data.json | May 10 00:26 | 2026-05-10T08:26:26 | ✅ |
| signals.json | May 6 08:48 | 无字段 | ❌ 滞后 88h |
| review_results.json | May 10 00:27 | 2026-05-10T08:27:09 | ✅（但审查旧信号）|
| approved_signals.json | May 10 00:27 | 无字段 | ✅（但内容来自 May 6）|
| execution_results.json | May 10 00:27 | 2026-05-10T08:27:09 | ✅（dry_run=5 on stale）|
| positions.json | — | — | ❌ 不存在 |

---

**结论：** 链路能闭环运行，但当 Polymarket API 不可用时会静默降级为"重放旧信号"模式。这在 dry-run 阶段可容忍，但 live 模式下会造成基于过期价格下单。P0-A（信号过期拦截）+ P0-B（positions.json bootstrap）是上线前必须修的两项。

### Round: FIX_PLAN #9 (partial) — Agent M 过严修复 (2026-05-09)

**Root cause analysis (offline, no LLM calls):**
- `data/review_results.json` (2026-05-09 capture, 9 signals, 2 approved / 7 rejected):
  - Vegas Golden Knights (NHL, NO @ 0.87, position=28.5%) — REJECTED with failure_prob=**18%**.
    Rejection reason explicitly stated: `position_size=28.5% > 20%` hard limit.
    This is the only heuristic false-negative (whitelist_extreme + failure_prob < 35% + actual REJECT).
  - NBA Finals YES @ 0.008-0.015, position=0.20 — REJECTED for "data source not directly related".
    Root cause: whitelist override language was "倾向于 APPROVE" (advisory), easily overridden by
    general strict criteria. Position at exactly 0.20 also triggered the hard limit.
  - 2028 Politics signals (not whitelist) — rejection is correct; no fix needed.

**Changes made:**

`agents/agent_m.py`:
1. Added `classify_signal(signal)` — static pure function; returns `is_whitelist`, `is_extreme_price`,
   `is_whitelist_extreme`, `is_arbitrage`. Extracted from inline logic for testability.
2. Added `_preprocess_signal(signal, cls)` — FIX_PLAN #9 "仓位 ≥20% 强制下调不拒绝":
   for whitelist_extreme or arbitrage signals with position_size ≥ 0.20, returns a shallow copy
   with position_size capped to 0.19. Original value preserved in `_original_position_size`.
   Normal signals returned unchanged.
3. `review_signal()` now calls `_preprocess_signal()` before the LLM call and uses `classify_signal()`
   instead of duplicated inline classification code.
4. Whitelist extreme-price prompt section strengthened: changed "倾向于 APPROVE" (advisory) to
   explicit mandatory APPROVE with note that general REJECT rules (EV > 100%, position, data source
   direct-relevance) **do not apply** to whitelist extreme-price signals.

`scripts/backtest_agent_m.py` (new):
- Offline evaluator: no LLM calls. Loads 3 historical test signal files + `review_results.json`.
- Reports classification stats (whitelist_extreme, arbitrage counts per dataset), position violations,
  and heuristic false-negatives from captured review results.
- Confirmed output: Vegas is the 1 heuristic FN; position cap fix resolves it.
- Usage: `python3 scripts/backtest_agent_m.py`

`tests/test_smoke.py` — 3 new tests (lines 1135–1275):
1. `test_agent_m_classify_signal_whitelist_extreme` — NHL NO/NBA YES/Politics/ARBITRAGE classification.
2. `test_agent_m_preprocess_caps_position_for_whitelist` — position cap: Vegas 28.5%→19%,
   NBA 20%→19%, Politics 22% unchanged, original signal not mutated.
3. `test_agent_m_backtest_script_runs_clean` — subprocess run exits 0, reports Vegas FN.

**Test result (sandbox, openai not installed):**
- `-k "agent_m"`: **3 passed**
- Full suite: 30 passed, 17 failed (17 pre-existing codex/llm_helper failures due to missing `openai` in sandbox — unchanged from before this patch)
- Expected on user local env (openai installed): **47 passed, 2 warnings** (was 44)

**What this fixes:**
- Vegas Golden Knights: after fix, position is capped to 19% before LLM evaluation; LLM sees
  failure_prob=18%, EV=11.97%, whitelist_extreme=True → should APPROVE.
- NBA Finals extreme-YES: position cap + stronger prompt → higher approval probability.
- No change to non-whitelist signals.

**What this does NOT fix (next round):**
- NBA exact data-quality rejection: even with capped position and stronger prompt language, the LLM
  may still reject for "data source not directly related to specific team". Needs prompt validation
  with real LLM run (requires dry-run cycle).
- FIX_PLAN #9 "失败概率 35-50% 接受减仓" — not yet implemented (separate low-risk prompt change).

---

## Needs Codex

**代码审计发现：所有 E2E 审计问题均已在代码中修复，无需 Claude Code 重复实现。**

已确认实现状态：
- ✅ P0-A 信号过期拦截：`orchestrator.py` 的 `_signals_ready_for_review()` + `SIGNAL_MAX_AGE_SECONDS=7200`，信号过期时写 `status=skipped` 到 `review_results.json` 和 `execution_results.json`
- ✅ P0-B positions.json bootstrap：`orchestrator.__init__` 调用 `_bootstrap_runtime_files()` 自动创建空 `[]`
- ✅ P1-1 Agent I 命名：`agents/agent_i.py` 监控列表已为 `"k_v2"`
- ✅ agent_k_v2 `generated_at`：两字段均写入
- ✅ agent_b `timestamp`：已写入；`_signals_ready_for_review` 同时接受 `generated_at` 和 `timestamp`
- ✅ Smoke tests：`test_orchestrator_bootstraps_positions_file`、`test_orchestrator_rejects_stale_signals_and_writes_fresh_skip_outputs`、`test_orchestrator_accepts_fresh_generated_at_signal`、`test_agent_i_checks_agent_k_v2_log_name` 均已存在

**P1-2 + P1-3 均已由 Claude Code 修复（见 Claude Result 最新 Round）。所有已知缺口关闭。**

1. Run `python3 -m pytest tests/test_smoke.py -v` on local env → confirm **51 passed, 2 warnings**.
2. Run `python3 scripts/backtest_agent_m.py` → confirm Vegas FN reported, no errors.
3. Optionally run one dry-run cycle (`/Users/libo/.hermes/home/scripts/polymarket_arbitrage_script.sh`)
   and check if Vegas Golden Knights now appears in `data/approved_signals.json`.
4. Decide: approve this partial #9 fix and either close #9 or write next sub-task (NBA data-quality
   prompt validation, or "failure_prob 35-50% → reduce position" rule).

---

## Codex Review (previous rounds, compressed)

- P3 #12 log rotation: APPROVED.
- 2026-05-09: `main.py --mode once` dry-run confirmed; scheduling script restored; 44 passed.

---

## Codex Review

Status: P3 #12 log rotation approved and closed.

Notes:
- Reviewed `scripts/rotate_logs.py`: stdlib-only, dry-run by default, supports `--logs-dir`, `--retention-days`, `--archive-dir`, and `--apply`.
- Confirmed only direct `*.log` files under the provided logs dir are processed.
- Confirmed apply mode gzip-archives old logs and collision-safe names avoid overwrites.
- Re-ran `python3 -m pytest tests/test_smoke.py -v`: `44 passed, 2 warnings`.
- Ran `python3 scripts/rotate_logs.py --logs-dir /tmp/nonexistent-hermes-logs`: dry-run exits 0 and touches no real logs.
- Ran apply mode only against a temporary `/tmp` logs dir and verified gzip content was readable.
- No real project logs were modified with `--apply`; no containers started; no real orders placed.
- P3 #2 key governance remains deferred by user.
- P2 #7 `regime_detector` remains deferred until fresh timeout evidence appears.

2026-05-09 continuation:
- `main.py --mode once` dry-run entry confirmed and tested.
- Dry-run scheduling script restored as a forced dry-run wrapper and tested.
- Dry-run observation heartbeat created in Codex app; no OS crontab/launchd scheduler was active at inspection time.
- Later observation found and fixed a PATH-sensitive Python issue in the dry-run script; multiple follow-up dry-runs were clean.
- Dry-run observation heartbeat was deleted after enough clean cycles.
- Added `docs/pre_live_validation_plan.md`.

2026-05-09 FIX_PLAN #9 Codex review:
- Local validation of Claude Agent M patch:
  - `/usr/bin/python3 -m pytest tests/test_smoke.py -v` initially passed: `47 passed, 2 warnings`.
  - `/usr/bin/python3 scripts/backtest_agent_m.py` passed and reported Vegas as known FN.
- Dry-run validation showed Vegas still rejected with uncapped `position_size=0.285`; cause was stale `ReviewCache` hit because cache key ignored market identity and `position_size`.
- Codex made interim cache-key patch and added a smoke test; smoke now passes `48 passed, 2 warnings`.
- Follow-up dry-run after cache-key patch forced fresh Agent M LLM calls; LLM API returned connection errors, so Agent M fail-closed to `0 approved / 9 rejected`.
- Safe behavior: no real orders; `approved_signals.json` became empty.
- New bug found: with zero approved signals, `executors/signal_executor.py` returns without rewriting `execution_results.json`, leaving stale previous `dry_run=2`. This is now assigned to Claude in the Active Task above.
- User asked Codex to continue, so Codex implemented the follow-up directly:
  - `executors/signal_executor.py` writes zero-result execution output on empty signals.
  - `tests/test_smoke.py` covers empty-signal overwrite and cache-key sensitivity.
  - Smoke is now `49 passed, 2 warnings`.
  - Dry-run confirms stale `execution_results.json` issue is fixed (`total=0`, `dry_run=0` when approved signals are empty).
- External-network dry-run then confirmed Agent M's earlier LLM `Connection error` was sandbox-network related. With network access, Agent M approved 5/9 signals; Vegas and NBA extreme-price approvals are now working, and execution remained dry-run only (`dry_run=5`).
