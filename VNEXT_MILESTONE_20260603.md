# VNext 里程碑收口 — 2026-06-03

> 本轮把项目从「JSON 文件流水线」推进到「JSON 事实源 + SQLite 影子库 + FastAPI Runtime + 研究/复盘闭环」，Phase 0 → 3d 全部实现，绝大多数已主机验证。
> 一句话：**PRD 的 Runtime API 化 + 研究→试错→复盘→进化闭环，骨架已全部到位，且全程没破 dry-run 安全底线。**

---

## 1. 全景（Phase 0 → 3d）

| Phase | 内容 | 状态 |
|---|---|---|
| 0 | 写入收敛：5 核心写者 → `runtime.datastore` 单写门面 | ✅ 主机验证 |
| 1 | SQLite 影子库 + 周期刷新钩子（JSON 仍事实源，DB 旁路） | ✅ 主机验证 |
| 2a | Canonical market identity（markets 维表，持仓 29→22 去重） | ✅ 主机验证 |
| 2b | Paper Runtime API（FastAPI，带锁写复用 orchestrator.lock） | ✅ 主机验证 |
| 3a | Agent G → Postmortem 引擎（逐笔结构化复盘） | ✅ 主机验证 + 3 轮幂等 |
| 3b | Agent P → 波动退出 + 每市场价格历史 | ✅ 主机验证 + 6 轮观察 |
| 3c | Agent B → Research/hypothesis（派生 + B prompt 原生） | ✅ 主机验证 |
| 3d | Agent M → 三级 risk grading（approve/paper_probe/reject） | ✅ 全周期签收完成（2026-06-04，见 SESSION_STATE_20260604.md） |

---

## 2. PRD 对照

| PRD 模块 | 落地情况 |
|---|---|
| Layer 1 Runtime API | ✅ FastAPI `runtime/api.py`：GET signals/reviews/positions/trades/markets/postmortems/hypotheses/status；POST paper/open\|close（带单写锁）；admin reconcile/generate |
| Layer 2 Database | ✅ SQLite 影子库 10 表（见 §3），JSON 仍事实源、DB 旁路可重建 |
| Layer 3 Agent Runner | 部分：agent 仍由 orchestrator 串行调度；写入已统一走门面 |
| Agent B → Research | ✅ hypothesis（方向/置信/预期边/持仓时长/失败条件），B prompt 原生输出 |
| Agent M → risk grading | ✅ 三级 approve/paper_probe/reject，不再一票否决 |
| Agent P → 退出归因 | ✅ 止损/时间/**波动退出** + **真实最高水位 trailing**（high_water 回撤跟踪）+ 真实 exit attribution |
| Agent G → Postmortem | ✅ 逐笔复盘引擎（hypothesis/expected_edge/failure_reason/liquidity\|timing\|model_issue） |
| Event Runtime | ✅ `event_logger` + runtime_events 表（signal.generated/risk.rejected/risk.paper_probe/execution.dry_run/…） |
| 新交易哲学（小额试错） | ✅ paper_probe 小仓（×0.25）受控试错，全程 dry_run |
| Dashboard / Mobile（Phase 5） | ✅ 已接（2026-06-04）：Web 加 `/positions`（better-sqlite3 直读 canonical）+ `/research`（含 3c-2 对照）；Mobile = bot 发送自包含 HTML（仓位 canonical/三级/假设/失败原因） |

---

## 3. 新增 Runtime 层（`runtime/`）

模块：`datastore`（唯一写门面）· `_shadow`（SQLite 影子写 + 自迁移 `_migrate`）· `schema.sql` · `ingest`（回填+对账）· `market_identity`（canonical 主键）· `locking`（单写锁）· `api`（FastAPI）· `postmortem` · `price_history` · `hypothesis`。

影子库 10 表：`signals / reviews / paper_orders / paper_positions / paper_trades / runtime_events / markets / postmortems / market_prices / hypotheses`（+ `schema_meta`，版本 `0.3.2-phase3c`）。

闭环数据接缝：`hypotheses(signal_uid) → signals → paper_positions → postmortems(signal_uid)`，已实测产生 join。

---

## 4. 全程守住的不变量（安全底线）

1. **JSON 是唯一事实源**，SQLite 纯旁路、可重建；dry-run 链路完全不经过 DB。
2. **单写者**：所有 live 写入走 `datastore` 门面；API 写复用 `orchestrator.lock`（周期跑时 409）。
3. **dry-run 护栏 `success=0` 从未破**——包括 3d 的 paper_probe（仍 dry_run）。
4. **学习不污染**：只学 `success/failed`，probe/dry_run/simulated 天然隔离。
5. **加法优先、可回滚、单点验证**：每步先沙箱端到端、再主机收口；调度始终安全停止（未恢复 launchd）。

---

## 5. 验证状态

- 沙箱：每个 runtime 模块/纯函数端到端验证（门面双写、canonical 合并、锁 409、postmortem 确定性归因、波动 helper、hypothesis 派生+原生、`_grade` 真值表 9/9）。
- 主机：smoke 全程 **71 passed**；schema 自迁移逐版本通过；多轮 dry-run 观察（paper_positions 恒 22、market_prices 线性、postmortems 幂等、护栏 success=0）。
- 一个轻量修复入档：3.9 兼容（API 注解 `Optional[X]`）、smoke `agent_codex` 模型断言对齐。

---

## 6. 剩余尾巴 / 下一步候选

按价值/风险排序：

1. ~~**3d 全周期签收**：等/触发一轮 agent_b 成功的 fresh-signals 周期，看 M 三级在完整 orchestrator 内分流~~ → **已完成 2026-06-04**：真实 orchestrator step13/14 路径上复现 approved=0/paper_probe=5/rejected=3，success=0 护栏不破，smoke 71。详见 SESSION_STATE_20260604.md。
2. ~~**trailing 真实最高水位**~~ → **已完成 2026-06-04**：agent_p 新增 `_peak_pnl_from_history`，按持有方向取 price_history 的 yes/no_price 序列 `high_water` 算真实峰值浮盈，trailing 改为「从真实峰值回撤 ≥ trailing_percent 才卖」（无足够历史回退旧行为）。单测真值表 + 28 agent_p 测试 + smoke 71 全过。详见 PHASE3B_AGENT_P_VOLATILITY.md。
3. ~~**临时键 reconcile 自动化**~~ → **已完成 2026-06-04**：`upgrade_provisional_positions` 拓宽到裸 slug + question 匹配（仅升级到纯数字 id、防 COALESCE 污染平仓 pnl），接入 `ingest.backfill()` 末尾 → 覆盖 orchestrator 周期末 + standalone 重建。实测 22→20 去重、幂等、无回归。详见 PHASE2A_PROVISIONAL_RECONCILE.md。
4. ~~**Next.js dashboard 切 canonical 视图**~~ → **已完成 2026-06-04**：新增独立 `/positions` 页 + `/api/positions`（better-sqlite3 直读 runtime.db canonical 持仓，去重 22 行而非裸 JSON 2213 条），tsc 0 错误。详见 PHASE5_CANONICAL_POSITIONS.md。
5. ~~**PRD Phase 5**：Mobile 视图~~ → **已完成 2026-06-04**：PRD Mobile 原生视图定为「Telegram bot 发送自包含 HTML」（`report` 命令 + `mobile_report.py`），补成完整视图覆盖 仓位(canonical)/三级风险/假设/失败原因(3c-2 对照)。详见 PHASE5_DASHBOARD_RESEARCH.md §3c。
6. ~~**3c-2 后续**：B 的 failure_conditions 用于复盘对照~~ → **已完成 2026-06-04**：复盘引擎按 signal_uid 取 hypothesis，逐条判定失败条件是否发生 + 整体 verdict（confirmed/refuted/loss_unexplained/no_prediction/inconclusive），schema 0.3.3、ingest 补回填 hypotheses、dashboard /research 露出。详见 PHASE3C2_FAILURE_CONDITION_REVIEW.md。

---

## 7. 给未来会话的接续指引

1. 读 `CLAUDE.md`（已含 runtime 层 + 三级 grading + 各 Phase 长期事实）。
2. 读最新 `SESSION_STATE_*.md`。
3. 各 Phase 细节见对应 `PHASE0_*.md / PHASE2A_*.md / PHASE2B_*.md / PHASE3A~D_*.md` + `VNEXT_GAP_ANALYSIS.md`。
4. 影子库随时可重建：`PA_BASE_DIR="$PWD" venv/bin/python3 -m runtime.ingest`；schema 升级后删 `data/runtime.db` 重建。
5. 纪律不变：改 live 写入走门面、不新增裸 `json.dump`；执行层始终 `EXECUTOR_DRY_RUN=1`；API 注解禁用 PEP 604 `X|None`（主机 venv 3.9）。
