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
- `runtime/schema.sql` — 表：signals(3f-loop 加 models_used 列)/reviews/paper_orders/paper_positions/paper_trades/runtime_events + markets(2a) + postmortems(3a) + hypotheses(3c) + market_prices(3b) + model_effectiveness(3e) + rule_weights(3e-2) + correlation_signals(3f) + regime_states(3g) + regime_effectiveness(3g-loop) + volatility_states(3h) + sizing_suggestions(3i) + enforcement_audit(5)。库文件 `data/runtime.db`，可用 `PA_DB_PATH` 覆盖位置。**新增整表（非加列）用 `CREATE TABLE IF NOT EXISTS` 即可由 `_migrate` 的 executescript 自动建，不必登记 `_EXPECTED_COLUMNS`（那个只为给旧表补列）。**
- `runtime/price_history.py` — 每市场价格历史 + 波动率/最高水位（Phase 3b）。事实源 `data/market_price_history.json`（orchestrator 步骤 1.5 每周期 append，滚动 60 点，无条件写）+ 影子 `market_prices` 表。agent_p 波动退出读事实源(不依赖 DB)；`should_volatility_exit` 样本<5 不触发。**真实最高水位 trailing（2026-06-04 完成）**：`agent_p._peak_pnl_from_history` 按持有方向取 yes/no_price 序列 `high_water` 算真实峰值浮盈，trailing 改为「从真实峰值回撤 ≥ trailing_percent 才卖」(样本<3 或无映射回退旧「达 trigger 即止盈」行为)。
- **Agent M 三级 risk grading（Phase 3d）**：`agents/agent_m.py` 由二元 approve/reject 改为 approve/paper_probe/reject。确定性 `_grade()` 裁定（硬规则拒绝前置）：失败概率>=60→REJECT；35<=fp<60 且健全(有 data_sources+logic_chain)→PAPER_PROBE；fp<35 且 LLM=APPROVE 且健全→APPROVE。probe 信号 position_size ×0.25 + `grade=paper_probe`，进 approved_signals 照常执行但**仍 dry_run（success=0 护栏不破）**。`_shadow.upsert_reviews` 读 `probe_signals` 记 PAPER_PROBE；事件 `risk.paper_probe`。学习隔离靠 status=dry_run（只学 success/failed）。
- `runtime/hypothesis.py` — Agent B 研究假设提取（Phase 3c-1）。每信号确定性派生结构化假设(方向/置信/预期边/持仓时长/失败条件)，写 `data/hypotheses.jsonl` + 影子 `hypotheses` 表；orchestrator 步骤 12.5b 无条件生成。**原生 holding_horizon_days/failure_conditions 优先**(为 3c-2 扩 B prompt 预留，source derived→agent_b)。经 signal_uid 与 signals/postmortems 闭环。`GET /hypotheses`。
  - **Phase 3c-2 失败条件对照（2026-06-04 已沙箱验证）**：复盘引擎按 signal_uid 取 hypothesis，对每条 `failure_conditions` 判定「是否发生」+ 整体 `hypothesis_verdict`（confirmed/refuted/loss_unexplained/no_prediction/inconclusive），写 postmortems 新列 + jsonl。schema→`0.3.3-phase3c2`（postmortems 加 `hypothesis_verdict` 列，已登记 `_EXPECTED_COLUMNS`）。**ingest 已补回填 hypotheses**（删库重建后对照仍可用；postmortems 不回填，靠复盘引擎重跑带 verdict）。dashboard `/research` 复盘卡片露出对照徽章 + 逐条发生/未发生。详见 PHASE3C2_FAILURE_CONDITION_REVIEW.md。
- `runtime/postmortem.py` — Agent G 复盘引擎（Phase 3a）。逐笔已平仓 join 原始信号 → 结构化复盘(hypothesis/expected_edge/failure_reason/liquidity|timing|model_issue)，写 `data/postmortems.jsonl` + 影子表。确定性 fallback 默认（沙箱可验）；LLM 增强需 `use_llm`/`PA_POSTMORTEM_LLM=1`（主机）。orchestrator 周期末自动确定性生成。`GET /postmortems`。
- `runtime/model_effectiveness.py` — 模型/规则有效性聚合（Phase 3e，Learning Runtime 第一块）。把 postmortems × 模型标签（当前= signals.`learned_rule_match`/`source`，经 signal_uid join）按 **rule/family/agent 三尺度**聚合：胜率/盈亏/edge兑现/verdict分布/问题率/decay → 确定性有效性裁定(`effective/ineffective/marginal/decayed/inconclusive/insufficient`)。写 `data/model_effectiveness.json` 事实源 + 影子 `model_effectiveness` 表（schema→`0.3.4-phase3e`，**快照语义整表重建**，无 stale key）。orchestrator 周期末**复盘之后**重算（`PA_SHADOW_DB=1`，best-effort）。`GET /model-effectiveness?scope=rule|family|agent`。纯确定性、加法、只读 postmortems 不碰 dry_run。⚠ signals 表 `learned_rule_match` 经 `_j()` 存成带引号 JSON 文本，聚合用 `_unwrap()` 去引号。**未来接真正 models_used 时只换标签来源，聚合骨架不变**。详见 PHASE3E_MODEL_EFFECTIVENESS.md。
- `runtime/rule_weights.py` — 规则权重建议（Phase 3e-2，「淘汰失效模型」雏形）。读 `data/model_effectiveness.json` → 每条规则/族给 weight 乘子 + 处置标签（确定性策略：effective 1.10/keep；insufficient 1.00/**explore（样本不足绝不淘汰）**；ineffective 0.50/down_weight；decayed 0.25/**retire_candidate 仍不归零**）。写 `data/rule_effectiveness.json` 建议产物 + 影子 `rule_weights` 表（schema→`0.3.5-phase3e-weights`，快照重建）。orchestrator 周期末 model_effectiveness 之后重算。`GET /rule-weights?scope=rule|family`。**关键护栏：产物带 `enforced=false`，未接入 agent_b 交易链路，信号生成/过滤零变化**；真正 enforcement（按 weight 压仓/跳过）= 后续 env 门控独立步骤（Phase 5），需单独评审。详见 PHASE3E_MODEL_EFFECTIVENESS.md §5b。
- `runtime/cointegration.py` — 协整/spread 研究模型（Phase 3f，**第一个真实模型**，numpy-only）。读 `data/market_price_history.json`，配对 OLS 对冲比 + spread z-score + Pearson + AR(1) 半衰期（Engle-Granger 轻量版，避开 statsmodels）→ 带**真实 `models_used=["cointegration"]`** + evidence + failure_conditions 的研究候选。写 `data/correlation_signals.json` + 影子 `correlation_signals` 表（SCHEMA→`0.3.14-phase5-explore-tier`：候选加 `entry_price` + 无量纲 `expected_return`=(1−φ)·|z|·spread_std/入场价 供 sizing 校准 + `tier` 字段；快照重建）。orchestrator 周期末 rule_weights 之后重算（`PA_SHADOW_DB` 块内）。`GET /correlation-signals`。**防伪相关护栏**：两腿都在动 + 不同取值数≥4 + |corr|≥0.8 + |z|≥2 + 0<半衰期≤20；点少时（当前每序列~10点）多数被剔除，候选随价格历史累积增多。**探索层（PRD §6 弱关联低风险试错，env 门控 `PA_COINT_EXPLORE=1` 默认关）**：放松 corr≥0.5/|z|≥1.5（`PA_COINT_EXPLORE_CORR`/`_Z` 可调）出 `tier=exploration` 候选——**置信封顶 35**（→Agent M 路由 paper_probe）+ 追加弱关联 failure_condition + `to_pipeline_signals` 用更小 probe 仓位 0.02；**半衰期(平稳性)过滤不放松**（价差仍须均值回归）；门控关时 `tier=research` 行为零回归。让 by_model 学习器事后验证/降权弱关联边。**关键护栏：研究工具(PRD §10)，`enforced=false`，不接入 live executor/agent_b**；接入交易链路 = 后续 env 门控独立步骤。⚠ 主机需 numpy，缺则钩子 best-effort 跳过。冷启动/无真实联动→0 候选属正确（模型拒绝从噪声造边）；自举/诊断用 `scripts/bootstrap_cointegration_from_cache.py`。详见 PHASE3F_COINTEGRATION.md / RUNBOOK_COINTEGRATION_LOOP.md。
  - **Phase 3f-loop 真实模型端到端闭环（2026-06-05）**：让协整经 review→execute→postmortem→学习。**安全层（默认生效）**：`signals` 表加 `models_used` 列（已登记 `_EXPECTED_COLUMNS`），`upsert_signals` 写入；`model_effectiveness` 增 **`by_model` 尺度**（join `signals.models_used` 按真实模型聚合，闭环归因终点）；schema→`0.3.7-phase3f-loop`。**风险层（env 门控 `PA_COINT_SIGNALS=1`，默认关）**：`cointegration.to_pipeline_signals()` 把候选转成带 `models_used`+健全性字段的小仓位 probe 方向性信号，orchestrator 步骤 12.5 门控合入；默认关→信号链路零变化。**⚠ 开启即注入可成交信号，仅在 `EXECUTOR_DRY_RUN=1` 受控验证下开，需评审后才主机开。** **评审修复（同日）**：Fix1 配对原子完整性——协整两腿带 `pair_id`，`cointegration.enforce_pair_integrity` + orchestrator 步骤 13.5（Agent M 后/执行前，门控）剔除裸腿（经 `datastore.put_approved_signals`）；Fix2 edge 单位——leg `expected_value` 改无量纲预期收益率，`model_effectiveness` 加方向感知 `realized_return`（NO 取反）+ 无量纲 `edge_realization`。
  - **Phase 3f-x 跨资产协整（PRD §9，2026-06-05）**：Polymarket × 外部资产（加密/美股/宏观）。新增 `datastore.record_asset_prices`→`data/asset_price_history.json`（{symbol:[{ts,price,kind}]} 滚动 60，json 事实源不落影子）+ `price_history.load_asset_history/asset_series_for`；orchestrator 步骤1.5 从 latest_data 抽 okx/us_stocks/btc_funding 无条件记录。`cointegration.find_cross_asset_candidates` 复用 `analyze_pair`（OLS 吸收量纲），出 `pair_type=pm_asset`+`anchor_asset`，**只有 PM 腿 tradeable**（资产是外生锚不可成交）；桥对 pm_asset 只发 1 条 PM 方向性信号（`pair_id=None`，过完整性门），`models_used=["cointegration"]` 照常进 by_model。冷启动 n_assets=0 待累积。详见 PHASE3F_COINTEGRATION.md §5d。
- `runtime/regime_effectiveness.py` — regime 有效性聚合（Phase 3g-loop，PRD §13「哪个 regime 有效」，**numpy-free**）。把 postmortems 按市场 regime 标签（join `regime_states.json` 当前 regime，作开仓 regime **代理**）分桶，**复用 `model_effectiveness` 全部指标计算**（DRY）出每 regime 胜率/盈亏/edge兑现/decay/有效性裁定。写 `data/regime_effectiveness.json` + 影子 `regime_effectiveness` 表（schema→`0.3.9`，快照重建）。orchestrator 周期末 regime 之后重算。`GET /regime-effectiveness`。无 regime_states（主机无 numpy 未产出）→ 全归 unknown 诚实降级。`enforced=False` 不接入交易链路。未来升级=持久化逐周期 regime 历史按 opened_at join。详见 PHASE3G_HMM_REGIME.md §6。
- `runtime/garch.py` — GARCH(1,1) 波动率聚集研究模型（Phase 3h，**第三个真实模型**，PRD §11 优先级3，numpy-only）。去均值差分收益 → **方差目标化** GARCH(1,1)（omega=V·(1−α−β)，(α,β) 二维网格 MLE，平稳约束 α+β≤0.985，确定性 argmax，避开 arch/scipy）。出 persistence/long_run_vol/current_vol/**forecast_vol**(1步)/risk_state(elevated/normal/calm)/vol_trend/clustering/vol_spike，`models_used=["garch"]`。与 HMM 互补（regime 给离散态、GARCH 给连续波动）。写 `data/volatility_states.json` + 影子 `volatility_states` 表（schema→`0.3.10`，快照重建）。orchestrator 周期末 regime 有效性之后重算。`GET /volatility-states?risk_state=...`。**研究工具 enforced=False，不接入交易链路**。⚠ 需 numpy。详见 PHASE3H_GARCH.md。
- `runtime/position_sizing.py` — Kelly+Markowitz 仓位建议（Phase 3i，PRD §11 优先级4/5，numpy-only）。组合三模型：边←cointegration `expected_edge`、方差←GARCH `forecast_vol²`、regime←HMM 做风险缩放。**Kelly**：`f=clamp(κ·μ/σ²,0,F_MAX)×regime_scaler`（κ=0.25,F_MAX=0.25,负边归零）；**Markowitz**：`w∝Σ⁻¹μ` long-only 归一（pinv 兜底）。**Phase 5 边量纲校准**：μ 用候选无量纲 `expected_return`、价格单位 GARCH 方差经入场价归一为 `(vol/price)²`，收益率空间 Kelly（SCHEMA→`0.3.13-phase5-edge-calib`；旧候选无 entry_price 安全退化）。写 `data/sizing_suggestions.json` + 影子 `sizing_suggestions` 表（快照重建）。orchestrator 周期末 GARCH 之后重算。`GET /sizing-suggestions`。**关键护栏：建议产物 `enforced=False`**；接 enforcement=Phase 5 纸面强制层（见下 `runtime/enforcement.py`）。⚠ 需 numpy。详见 PHASE3I_SIZING.md / PHASE5_ENFORCEMENT.md §9。
- `runtime/enforcement.py` — **纸面强制层（Phase 5，把 learning 产物接回交易行为，stdlib-only）**。在 orchestrator 汇总 `signals.json`、写盘前调用：按 `data/rule_effectiveness.json`（rule weight 乘子，按 `learned_rule_match`→rule/family join，复用 `model_effectiveness._rule_family`）+ `data/sizing_suggestions.json`（Kelly×regime `sized_fraction`，按 `pair_id`/`signal_uid`→`market_id` join）调整每条信号 `position_size`。顺序：sizing 设基准→weight 乘子→clamp[floor,max]→**默认只降险**(≤原始)。写 `data/enforcement_audit.json` + 影子 `enforcement_audit` 表（schema→`0.3.12-phase5-enforce`，快照重建）+ 每条改动信号内 `enforcement` 证据。`GET /enforcement-audit`。**env 门控（默认全关→恒等零回归）**：`PA_ENFORCE_SIZING=1`/`PA_ENFORCE_WEIGHTS=1`/`PA_ENFORCE_LEARNING=1`（便捷=两者）；`PA_SIZING_FLOOR`(0.005,**绝不归零探针**)/`PA_ENFORCE_MAX_SIZE`(0.10,绝对硬上限)/`PA_ENFORCE_ALLOW_SCALE_UP=1`(默认只降险)。**关键护栏：只改 position_size，不绕过 Agent M 审查、不绕过 executor dry-run（`success` 仍由 `EXECUTOR_DRY_RUN` 决定）；仅在 `EXECUTOR_DRY_RUN=1` 受控验证下开。** 详见 PHASE5_ENFORCEMENT.md。
- `runtime/regime_hmm.py` — HMM 市场状态识别研究模型（Phase 3g，**第二个真实模型**，PRD §11 优先级2 + §13 regime 学习，numpy-only）。对价格序列**一阶差分**做 K=2 高斯 HMM（确定性分位数初始化 + 带 scaling 的 Baum-Welch EM + Viterbi 解码），按方差升序贴标签 calm/turbulent，当前 regime=末点解码态。产出带**真实 `models_used=["hmm"]`** + evidence(transition_matrix/states/separation/posterior) + failure_conditions 的研究产物：写 `data/regime_states.json` + 影子 `regime_states` 表（schema→`0.3.8-phase3g-hmm-regime`，快照重建）。同时分析 PM 市场(yes_price) 与外部资产(price)。orchestrator 周期末**协整之后**重算（`PA_SHADOW_DB` 块内）。`GET /regime-states?regime=calm|normal|turbulent`。输出 `regime_shift`（刚切换）/`news_driven`（turbulent+末点异常跳变）/`regime_confident`（方差分离≥1.5 且后验≥0.6）。**防伪 regime 护栏**：MIN_OBS=10 + 不同取值≥4 + 序列在动；分离/后验不足只标 not_confident 不剔除。**关键护栏：研究工具(PRD §10)，`enforced=false`，不接入 live executor/agent_b**；regime 喂 sizing/风控 = 后续 env 门控独立步骤。⚠ 主机需 numpy，缺则钩子 best-effort 跳过。详见 PHASE3G_HMM_REGIME.md。
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

# 装依赖（见 requirements.txt；numpy 为 runtime 真实模型必需）
# macOS SSL 证书报错时加 --trusted-host pypi.org --trusted-host files.pythonhosted.org
pip install -r "$ROOT/requirements.txt"

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
- `SESSION_STATE_20260605.md` — Phase 3e 模型有效性 + 3e-2 规则权重 + 3f 协整 + 3f-loop 闭环 + **3g HMM regime + 3g-loop regime 有效性 + 3h GARCH 波动率 + 3i Kelly/Markowitz sizing**（4 个新研究模型/学习器，全 `enforced=false` 研究/建议产物，schema→0.3.11；3g-loop+全接线 stdlib 已验证，HMM/GARCH/sizing 算法镜像已验证、numpy 单测待主机 env）+ **Phase 5 纸面强制层 enforcement（learning 产物接回 position_size，env 门控默认全关，schema→0.3.12；17 单测 + 全 237 测试通过 + dry-run 端到端已验证）**
- `SESSION_STATE_20260604.md` — Phase 3d 全周期签收（Agent M 三级分流在真实 orchestrator 路径复现）
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
