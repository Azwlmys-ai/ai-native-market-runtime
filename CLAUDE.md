# CLAUDE.md — Polymarket Arbitrage 项目记忆

> **语言规范（强制）**：所有输出统一使用简体中文；禁止日语；代码注释、报告、总结、终端解释全部使用中文，保留必要英文技术术语。

> 给未来 Claude 会话的项目入门文档。新会话开头读这个文件 + 最新的 `SESSION_STATE_*.md`,就能快速接续工作,不必重新审计。
>
> 修改原则:本文件只放**长期不变**的事实和规约。每次会话的进度/决定写到 `SESSION_STATE_<YYYYMMDD>.md`。

---

## 项目是什么

Polymarket 套利系统:多 agent + LLM 驱动,采集 Polymarket 行情 + 加密 + 美股 + A 股 + 港股 + 大宗商品,生成跨平台套利信号,经 Agent M 风险审查后由 `pm-trader` 执行下单。

主要目录:
- `agents/` — 各路 LLM agent(Agent A/B/D/E/F/G/H/I/J/K/M/P 等)
- `collectors/` — 行情采集(polygon/finnhub/yfinance/sina/tencent/longbridge/okx 等)
- `executors/` — 下单执行(`signal_executor.py`、`sell_executor.py`)
- `config/` — `system_config.json`(系统路径)、`llm_config.json`(LLM 路由)
- `data/` — 信号、审查结果、执行结果、历史数据
- `logs/` — 各 agent 和 orchestrator 的日志(每日一个文件)
- `backups/` — 整系统备份

---

## 关键路径

**这是个 Docker 项目**,容器内路径 ≠ 主机路径:

| 用途 | 容器内 | macOS 主机 |
|---|---|---|
| 项目根 | `/opt/data/polymarket_arbitrage` | `/Users/libo/.hermes/polymarket_arbitrage` |
| pm-trader | `/opt/data/home/.local/bin/pm-trader` | `/Users/libo/.hermes/home/.local/bin/pm-trader` |

代码里大量 hardcode `/opt/data/...`,这是 #1 待修问题。在主机上直接跑会找不到路径(已在 FIX_PLAN.md 里有迁移方案)。

---

## 入口分叉(重要)

**不止一个 orchestrator,且调用的 executor 不一致**(P0-pre 必须确认实际跑的是哪条):

| Orchestrator | 调用的 executor | 模式 |
|---|---|---|
| `orchestrator.py:180` | 根目录 `signal_executor.py` / `sell_executor.py` | 有 `run_once()`,适合受控单周期 |
| `orchestrator_advanced.py:245` | `executors/signal_executor.py` / `executors/sell_executor.py` | `while True` 主循环 |
| `orchestrator_realtime.py:207` | `executors/...` 下版本 | 实时 |

四个执行器文件(根目录 2 个 + executors/ 下 2 个)**MD5 都不同**,功能有差异。**修一处不能假设另一处也修了**。

---

## 配置和 LLM 路由

- 项目用 `polymarket_arbitrage/config/llm_config.json` 路由 LLM(里面有 xAI key + pawmaas 中转 key 的明文,#2 待治理,**用户已确认本轮不轮换**)
- LLM 调用入口:`llm_helper.py`,函数 `call_llm_sync(agent_id, prompt, ...)`
- fallback 逻辑当前**只走代码内 `FALLBACK_MAP`**,`llm_config.json` 里的 `fallback_map` 是死配置(#11 待修)

**注意区分**(这是历史教训):
- `~/.hermes/config.yaml` 和 `~/.hermes/.env` 是 **Hermes Gateway 自己的配置**,跟本项目独立
- 本项目的 LLM 调用**不读** Hermes gateway 的 .env / config.yaml,只读 `polymarket_arbitrage/config/llm_config.json`
- 2026-05-08 把 Hermes gateway 主模型改成 pawmaas/claude-opus-4-7 时,**没动** `polymarket_arbitrage/config/llm_config.json`,这是用户决策

---

## 运行时写入层（Phase 0 起，2026-06-02 已主机验证）

VNext 改造已落地「单写者门面 + SQLite 影子库」。**所有 live 文件写入统一走 `runtime/datastore.py` 门面**，不再各模块直接 `open(w)/json.dump`：

- `runtime/datastore.py` — 唯一写入门面（模块函数，非类）。json 永远先写、写成功即算成功；shadow 写在其后、best-effort、失败只记日志绝不抛。函数带 `base_dir` 可选参（保测试隔离）。
- `runtime/_shadow.py` — SQLite 影子写；默认关，`PA_SHADOW_DB=1` 才生效。持仓三套 schema 由 `_canon_pos()` 集中归一。**Phase 2a 起 uid 用 canonical_market_id**（见下）。
  - **schema 迁移**：`_migrate()` 轻量自迁移（无 Alembic）。**新增列必须登记到 `_EXPECTED_COLUMNS`**（靠 `ALTER ADD COLUMN` 补旧库），不能只改 `CREATE TABLE`（对旧表是 no-op）；依赖新列的索引要放 `_migrate` 在补列后建，别放 schema.sql。
  - **canonical market identity**（`runtime/market_identity.py`）：canonical key = Polymarket 数字 id；`markets` 维表累积 id↔slug↔question（latest_data 权威 + 业务记录 harvest）；resolve = id→slug→question→临时键 `slug:<x>`。影子库是可重建旁路，**schema 升级后建议删 `data/runtime.db` 重建**（旧 uid 行不会自动迁移）。
    - **临时键 reconcile 自动化（2026-06-04）**：`_shadow.upgrade_provisional_positions()` 把非数字 canonical（`slug:`/裸 slug/`q:`）持仓按精确 slug 或 question 升级合并到权威**纯数字** id（真·slug-only 市场不动）。已接入 `ingest.backfill()` 末尾 → 覆盖 orchestrator 周期末（在复盘前）+ standalone 重建 + FastAPI `/admin/reconcile-provisional`。**防污染**：权威已平仓行存在时只删重复 provisional，不让其 `0/空` 值经 `_upsert_position` 的 `COALESCE(excluded,…)` 冲掉真实平仓 pnl。详见 PHASE2A_PROVISIONAL_RECONCILE.md。
- `runtime/schema.sql` — 表：signals/reviews/paper_orders/paper_positions/paper_trades/runtime_events + markets(2a) + postmortems(3a)。库文件 `data/runtime.db`，可用 `PA_DB_PATH` 覆盖位置。
- `runtime/price_history.py` — 每市场价格历史 + 波动率/最高水位（Phase 3b）。事实源 `data/market_price_history.json`（orchestrator 步骤 1.5 每周期 append，滚动 60 点，无条件写）+ 影子 `market_prices` 表。agent_p 波动退出读事实源(不依赖 DB)；`should_volatility_exit` 样本<5 不触发。**真实最高水位 trailing（2026-06-04 完成）**：`agent_p._peak_pnl_from_history` 按持有方向取 yes/no_price 序列 `high_water` 算真实峰值浮盈，trailing 改为「从真实峰值回撤 ≥ trailing_percent 才卖」(样本<3 或无映射回退旧「达 trigger 即止盈」行为)。
- **Agent M 三级 risk grading（Phase 3d）**：`agents/agent_m.py` 由二元 approve/reject 改为 approve/paper_probe/reject。确定性 `_grade()` 裁定（硬规则拒绝前置）：失败概率>=60→REJECT；35<=fp<60 且健全(有 data_sources+logic_chain)→PAPER_PROBE；fp<35 且 LLM=APPROVE 且健全→APPROVE。probe 信号 position_size ×0.25 + `grade=paper_probe`，进 approved_signals 照常执行但**仍 dry_run（success=0 护栏不破）**。`_shadow.upsert_reviews` 读 `probe_signals` 记 PAPER_PROBE；事件 `risk.paper_probe`。学习隔离靠 status=dry_run（只学 success/failed）。
- `runtime/hypothesis.py` — Agent B 研究假设提取（Phase 3c-1）。每信号确定性派生结构化假设(方向/置信/预期边/持仓时长/失败条件)，写 `data/hypotheses.jsonl` + 影子 `hypotheses` 表；orchestrator 步骤 12.5b 无条件生成。**原生 holding_horizon_days/failure_conditions 优先**(为 3c-2 扩 B prompt 预留，source derived→agent_b)。经 signal_uid 与 signals/postmortems 闭环。`GET /hypotheses`。
  - **Phase 3c-2 失败条件对照（2026-06-04 已沙箱验证）**：复盘引擎按 signal_uid 取 hypothesis，对每条 `failure_conditions` 判定「是否发生」+ 整体 `hypothesis_verdict`（confirmed/refuted/loss_unexplained/no_prediction/inconclusive），写 postmortems 新列 + jsonl。schema→`0.3.3-phase3c2`（postmortems 加 `hypothesis_verdict` 列，已登记 `_EXPECTED_COLUMNS`）。**ingest 已补回填 hypotheses**（删库重建后对照仍可用；postmortems 不回填，靠复盘引擎重跑带 verdict）。dashboard `/research` 复盘卡片露出对照徽章 + 逐条发生/未发生。详见 PHASE3C2_FAILURE_CONDITION_REVIEW.md。
- `runtime/postmortem.py` — Agent G 复盘引擎（Phase 3a）。逐笔已平仓 join 原始信号 → 结构化复盘(hypothesis/expected_edge/failure_reason/liquidity|timing|model_issue)，写 `data/postmortems.jsonl` + 影子表。确定性 fallback 默认（沙箱可验）；LLM 增强需 `use_llm`/`PA_POSTMORTEM_LLM=1`（主机）。orchestrator 周期末自动确定性生成。`GET /postmortems`。
- `runtime/ingest.py` — 从现有 json 回填影子库 + 对账；只读 live json。`python3 -m runtime.ingest`。
- `runtime/api.py` — Paper Runtime API（FastAPI，Phase 2b）。GET 读影子 DB(canonical)；POST /paper/open|close 写经 paper_pnl→datastore。**POST 写端复用 `orchestrator.lock`（`runtime/locking.py`），周期跑时返回 409**——单写者不破。主机起：`PA_SHADOW_DB=1 uvicorn runtime.api:app --port 8848`（需 venv 装 fastapi uvicorn）。Next.js dashboard 仍只读 json。
  - ⚠ **主机 venv 是 Python 3.9**：FastAPI 运行时会 introspect 函数签名，故 API 端点参数注解**不能用 PEP 604 的 `X | None`**（即使有 `from __future__ import annotations` 也会炸），用 `Optional[X]`。
- **JSON 仍是唯一事实源**，DB 纯旁路，dry-run 链路完全不经过 DB。orchestrator 周期末有 best-effort 影子刷新钩子（`PA_SHADOW_DB=1` 时）。

已收敛的写者：`paper_pnl.py` / `agents/agent_p.py` / `agents/agent_m.py`(标准模式) / `executors/signal_executor.py` / `orchestrator.py`。
两个 deprecated orchestrator（advanced/realtime）已加头注释，唯一入口仍是 `main.py --mode once → orchestrator.run_once()`。

**新纪律**：改 live 写入时**改门面或调门面，不要新增直接 `json.dump` 到 data/**。根目录 `signal_executor.py` 已是 thin wrapper（re-export `executors/`），不必再“两份都改”。

下一步：Phase 2 — paper_pnl API 化 + canonical market identity（持仓缺统一市场主键：portfolio 多 `market_slug=""`、positions 无 `market_id`）。

---

## 当前修复状态

参见 [FIX_PLAN.md](./FIX_PLAN.md) v3.1 — 12 条已核实问题、优先级、smoke test、受控启动方案。

下一步入口:**先做 P0-pre 入口确认**,跑完把结果填到 FIX_PLAN.md 底部"执行记录"区,然后才动代码。

---

## 工作纪律(必读,踩过坑总结)

### 不要做
- ❌ **不要直接跑 orchestrator 真实交易循环**做"验证"。要测必须 `EXECUTOR_DRY_RUN=1`,并优先用 `orchestrator.py:run_once()` 单周期
- ❌ **不要为了 mock pm-trader 改 `config/system_config.json`**,会污染长期配置。改用环境变量 `PM_TRADER_PATH=/tmp/mock_pm_trader.sh`,跑完 unset
- ❌ **不要全项目大面积 sed 替换 `/opt/data`**。只迁核心链路(8 个文件,清单在 FIX_PLAN #1)
- ❌ **不要直接删重复执行器**,改 thin wrapper(可能有 cron / launchd / shell 历史调根目录)
- ❌ **不要把 `dry_run` 计入 `success`**。学习/绩效模块会把模拟当真实成交学坏

### 要做
- ✅ 改任何执行器代码,**两份都改**(根目录 + executors/),除非已经做过 wrapper 收敛
- ✅ 每次改完跑 `pytest tests/test_smoke.py -v`,全过才继续
- ✅ 每次会话结束写 `SESSION_STATE_<YYYYMMDD>.md`(沿用项目已有命名)
- ✅ 修复一项 → 更新 FIX_PLAN 底部"进度跟踪"表

### 状态分桶约定(避免污染学习样本)
执行结果 `status` 分 6 桶,**不可混用**:
- `success` — 真实成交成功
- `dry_run` — DRY_RUN 模式模拟,绝不下单
- `simulated` — 历史回测/调试模拟
- `failed` — 真实失败
- `timeout` — 超时
- `error` — 异常

下游学习模块**只学 `success` / `failed`**,必须过滤掉 `dry_run` / `simulated`。

---

## 常用命令

```bash
ROOT=/Users/libo/.hermes/polymarket_arbitrage

# 受控单周期(主推)
EXECUTOR_DRY_RUN=1 PM_TRADER_PATH=/tmp/mock_pm_trader.sh \
  python -c "from orchestrator import Orchestrator; Orchestrator().run_once()"

# Smoke test
pytest "$ROOT/tests/test_smoke.py" -v   # 全过才能继续

# 看核心链路日志
tail -f "$ROOT/logs/orchestrator_advanced_$(date +%Y%m%d).log"

# 跑完受控启动后 unset 环境变量
unset EXECUTOR_DRY_RUN PM_TRADER_PATH
```

---

## 历史会话索引

按时间倒序,看最近的就行:
- `SESSION_STATE_20260508.md` — 审计 12 条问题、定 FIX_PLAN v3.1、Hermes gateway 改 pawmaas
- `SESSION_STATE_20260507_0230.md`
- `SESSION_STATE_20260507.md`
- `SESSION_STATE_20260503.md`(注:有明文 key 痕迹,#2 治理时要清)

---

## 给未来 Claude 的 onboarding 指引

新会话第一步:
1. 读本文件(`CLAUDE.md`)
2. 读最新 `SESSION_STATE_*.md`(看上次到哪里)
3. 读 `FIX_PLAN.md` 的"执行记录"区,看 P0-pre 是否已确认入口
4. 如果用户没明确指令,从 FIX_PLAN 进度跟踪表里挑一项 ⏳ 状态的工作
