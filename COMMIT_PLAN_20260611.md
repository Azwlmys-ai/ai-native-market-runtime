# 提交分组清单（2026-06-11，按当前主机状态修订）

> 当前分支：`main`；HEAD：`a0b44b6`。
> Git 主机视图可写且可靠，`.git/index.lock` 已清理。
> 每组 `git add <列出的路径>` 后先执行 `git diff --cached --stat`，确认范围再单独 commit。
> 已被 `.gitignore` 覆盖的（`data/ logs/ backups/ __pycache__ *.pyc config/llm_config.json`）不会进暂存。

---

## ⛔ 先处理 .gitignore（避免把数据/产物提交进去）

把以下追加到 `.gitignore`（都是生成产物/基准输出，不是源码）：

```gitignore
# 研究试验/验证输出（基准、trial、validation 产物）
research/agent_g_trial_outputs/
research/p0b_trial_outputs/
research/p0c_validation/
research/p0d_trial_outputs/
research/model_sandbox/*.json
research/model_sandbox/*.md      # 模型沙箱生成的报告；若想留快照则删掉这两行手动 add
# 带日期的 observation 快照（产物，非文档）
docs/observation/baseline_*.json
docs/observation/daily_*.md
```

**别提交**：`package-lock.json`（根目录无 `package.json`，文件仅含空 packages，dashboard/ 自带 lock）。建议删除，但不要把 `package-lock.json` 加入全局 ignore，以免将来根目录真正引入 Node 项目时漏提交 lockfile。

---

## A. 测试对账 ✅ 已提交

Commit：`a0b44b6 test: reconcile suite with Phase 4 live-gate + executor dedup`

包含：
- `paper_pnl.py`
- `executors/signal_executor.py`
- `tests/test_smoke.py`
- `tests/test_observation_catalog.py`
- `tests/test_observation_backfill.py`
- `tests/test_observation_learning.py`

验证：正式 `tests/` 回归（排除环境受限 watchdog）为 **355 passed**。

## B. Learning Runtime 模型/学习/enforcement 源码（Phase 3e–5）
```bash
git add runtime/model_effectiveness.py runtime/rule_weights.py \
        runtime/regime_hmm.py runtime/regime_effectiveness.py \
        runtime/garch.py runtime/position_sizing.py \
        runtime/enforcement.py runtime/live_probe.py \
        runtime/_shadow.py runtime/api.py runtime/datastore.py \
        runtime/schema.sql runtime/price_history.py \
        orchestrator.py executors/sell_executor.py requirements.txt
git commit -m "feat: Learning Runtime models + enforcement (Phase 3e–5)"
```
（注：`runtime/cointegration.py`、`signal_merge.py`、observation/model_sandbox 模块若已 TRACKED 则不在此列；`git add` 只会捡到真正改动的。）

## C. 模型/闭环测试
```bash
git add tests/test_model_effectiveness.py tests/test_rule_weights.py \
        tests/test_cointegration.py tests/test_cointegration_cross_asset.py \
        tests/test_cointegration_fixes.py tests/test_cointegration_loop.py \
        tests/test_cointegration_loop_orchestrator.py \
        tests/test_regime_hmm.py tests/test_regime_effectiveness.py \
        tests/test_garch.py tests/test_position_sizing.py \
        tests/test_enforcement.py tests/test_live_probe.py \
        tests/test_agent_b_probe.py tests/test_historical_replay.py \
        tests/test_llm_reliability.py
git commit -m "test: cover Phase 3e–5 models, loop, dedup/throttle, live-probe"
```

## D. Agents + LLM helper（支撑 probe/live/research 的改动）
```bash
git add agents/agent_a.py agents/agent_b.py agents/agent_e.py \
        agents/agent_f.py agents/agent_g.py \
        agents/historical_arbitrage_miner.py llm_helper.py
git commit -m "feat: agent probe/hedged-race + LLM routing updates"
```

## E. 运行/验证脚本
```bash
git add scripts/bootstrap_cointegration_from_cache.py \
        scripts/collect_final_validation_cycle.py \
        scripts/cross_market_brief_cron.sh scripts/cross_market_brief_health.sh \
        scripts/enforcement_calibration_sim.py \
        scripts/final_validation_run_24.sh \
        scripts/parallel_paper_cross_market_24.sh \
        scripts/run_host_loop.sh scripts/run_live_probe_loop.sh \
        scripts/summarize_agent_b_validation.py scripts/summarize_final_validation.py \
        scripts/validate_agent_b_hedged_race.sh \
        scripts/validate_agent_b_hedged_race_full.sh \
        scripts/validate_agent_b_timeout_fix.sh \
        scripts/verify_enforcement_live.py
git commit -m "chore: host loop / validation / live-probe scripts"
```

## F. research 工具脚本 + analytics 源码（仅源码，产物已 ignore）
```bash
git add analytics/ \
        research/build_earnings_actual_calendar.py research/build_event_calendars.py \
        research/build_history_datasets.py research/earnings_actual_dates.py \
        research/export_shared_trades.py research/history_paths.py \
        research/run_event_memory_gap_analysis.py research/run_historical_replay_pipeline.py \
        research/data_utilization_matrix.csv \
        research/cross_market/ research/crypto_ecosystem/
git commit -m "feat: research tooling (history datasets, cross-market, analytics)"
```

说明：
- `analytics/__pycache__/` 已被现有 ignore 规则排除。
- `research/cross_market/schema.sql` 是源码。
- `research/cross_market/launchd/*.plist` 是部署配置，不是运行产物；确认主机路径符合预期后可随本组提交。

## G. 文档 + 会话状态
```bash
git add PHASE3E_MODEL_EFFECTIVENESS.md PHASE3F_COINTEGRATION.md \
        PHASE3G_HMM_REGIME.md PHASE3H_GARCH.md PHASE3I_SIZING.md \
        PHASE4_LIVE_PROBE.md PHASE5_ENFORCEMENT.md RUNBOOK_COINTEGRATION_LOOP.md \
        SESSION_STATE_20260605.md COMMIT_PLAN_20260611.md CLAUDE.md .gitignore \
        docs/observation/OBSERVATION_WINDOW.md \
        research/dxy_continuity.md research/funding_continuity.md \
        research/pm_crypto_tape_continuity.md
git commit -m "docs: Phase 3e–5 design notes, runbook, session state"
```

---

## 提交后自检
```bash
git status --short
# 若 .gitignore 已提交且 package-lock.json 已删除，期望为空。
# 若 package-lock.json 尚未删除，期望只剩：?? package-lock.json

venv/bin/python3 -m pytest tests -q --ignore=tests/test_account_watchdog.py
# 当前基线：355 passed；host-only observation 数据缺失时可能出现少量 skipped。
```

## 每组提交前的固定检查

```bash
git diff --cached --name-only
git diff --cached --stat
```

禁止使用 `git add -A` 或 `git add .`；工作区同时存在源码、研究产物和日期快照，只按上述精确路径暂存。
