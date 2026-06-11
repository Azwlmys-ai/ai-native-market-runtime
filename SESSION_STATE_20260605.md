# SESSION_STATE 2026-06-05 — Phase 3e 模型有效性聚合器落地

> 本轮单一目标（按用户「直接开始实现」指示 + 新 PRD「Learning Runtime 阶段」）：
> 交付 Learning Runtime 的「学习模型有效性」第一块——`runtime/model_effectiveness.py` 聚合器。
> 结论：**已落地并验证。三尺度有效性快照在真实 postmortems 上跑通，单测 8 passed，smoke 71 passed（合计 79）。修复一个真实数据 bug。**

---

## 1. 背景与选型（核实后决策）

落地前核实，确认直接做「学习器」会架空：
- 信号**无** PRD §8 结构化 `models_used`；量化模型（协整/HMM/GARCH/Markowitz/Kelly）**代码里基本未实现**，
  当前信号来自 agent_b 规则匹配（`learned_rule_match`）。
- 真实可用「模型/策略标签」= 信号的 `learned_rule_match` + `source`(agent)；postmortems 带 `signal_uid` 可 join 回 signals 影子表取标签。

用户选择「模型有效性聚合器」路线 → 用**当前真实可用归因**搭聚合骨架；未来接 `models_used` 时骨架不变（只换标签来源）。

---

## 2. 交付（详见 PHASE3E_MODEL_EFFECTIVENESS.md）

- **新增** `runtime/model_effectiveness.py`：确定性聚合 postmortems × 模型标签 → 三尺度（rule/family/agent）有效性快照。
  - 指标：胜率/总均盈亏/均预期边/edge兑现/置信/问题率/verdict分布/decay/有效性裁定。
  - 裁定硬规则：`insufficient`(n<3)/`inconclusive`(全flat)/`decayed`(近窗胜率↓≥0.20)/`effective`(胜率≥.55且盈亏>0)/`ineffective`(胜率≤.35或盈亏<0)/`marginal`。
- `runtime/schema.sql`：新增表 `model_effectiveness`；schema_version → **0.3.4-phase3e**。
- `runtime/_shadow.py`：`upsert_model_effectiveness`（**快照语义：整表 DELETE+INSERT**，避免 stale key）+ `query_model_effectiveness`。
- `runtime/datastore.py`：门面 `write_model_effectiveness`（json 事实源 + 影子 best-effort），登记进 `__all__`。
- `orchestrator.py`：周期末复盘**之后**加 best-effort 钩子（`PA_SHADOW_DB=1` 时 `model_effectiveness.compute()`）。
- `runtime/api.py`：`GET /model-effectiveness?scope=rule|family|agent`。
- `tests/test_model_effectiveness.py`：**新增 8 单测**。

---

## 3. 验证（沙箱 = 主机同一挂载）

| 判据 | 结果 |
|---|---|
| 新单测 | ✅ 8 passed（标签派生/裁定/decay/family/jsonl降级落盘） |
| smoke 回归 | ✅ 71 passed（与基线一致），合计 79 passed |
| 真实数据 standalone | ✅ 12 笔 postmortems → json + 影子表 8 行，`attribution_source=shadow_join_signals` |
| schema 自迁移 | ✅ 自动建新表，bump 到 0.3.4-phase3e，旧表未动 |

**修复的真实 bug**：signals 影子表 `learned_rule_match` 经 `_j()` 存成 JSON 文本（带引号），
聚合读回需 `_unwrap()` 去引号，否则 family 切成 `"mid_range`。已修 + 测试覆盖。

**数据观察（非缺陷）**：现有 12 笔复盘多为 flat / -1.0 小额（含 Test Market 等调试痕迹），
多数 signal_uid 在 signals 影子表无对应行 → 标签降级 `unknown`，裁定如实给 insufficient/ineffective。
机制已就绪，待 paper_probe 放量后才有统计意义。

---

## 4. 安全/非破坏

- 改动**全加法**：不碰审批/执行/学习行为；只读 postmortems（不碰 dry_run 执行结果）。
- 运行前备份 `data/runtime.db(+wal)` 到 `/tmp/pa_3e_backup`；新表 + `data/model_effectiveness.json` 为本阶段预期持久产物，原始 postmortems/signals/positions 未动。
- 影子表纯旁路，可删 `runtime.db` 重建（ingest 回填后重跑 compute 即可）。

---

## 5. 给未来会话

- 复现：`PA_SHADOW_DB=1 python3 -m runtime.model_effectiveness`（沙箱/主机通用，主机用 venv/bin/python3）。
- 测试：`pytest tests/test_model_effectiveness.py tests/test_smoke.py -v`。
- 下一步候选（PRD 顺序）：
  1. 接**真正的 models_used**：实现协整/spread 或 Kelly 写入信号链路，让标签升级为真实模型（聚合骨架不变）。
  2. **关联强度学习**：market correlation / regime 有效性，复用本表模式起 `correlation_effectiveness`。
  3. ~~learning agent 消费~~ → **已做（见下 §6）**。
  4. dashboard `/research` 加「模型有效性 + 规则权重建议」卡片。

---

## 6. 续作 — Phase 3e-2：规则权重建议（淘汰失效模型雏形）

承上「learning 侧消费 model_effectiveness」，本轮继续落地，但**刻意只建议、不强制**（对齐 PRD「大量低风险试错」）。

- **新增** `runtime/rule_weights.py`：读 `data/model_effectiveness.json` → 每条规则/族给 weight 乘子 + 处置标签 + 理由。
  - 策略：effective→1.10/keep；marginal|inconclusive→1.00/keep；**insufficient→1.00/explore（样本不足绝不淘汰）**；ineffective→0.50/down_weight；decayed→0.25/**retire_candidate（仍不归零）**。
- 新增表 `rule_weights`（schema→**0.3.5-phase3e-weights**，快照语义整表重建）+ datastore 门面 `write_rule_weights`（写 `data/rule_effectiveness.json` 建议产物）+ orchestrator 周期末 model_effectiveness 之后钩子 + `GET /rule-weights`。
- **关键护栏**：产物带 `enforced=false`，**未接入 agent_b 交易链路**，信号生成/过滤零变化。真正 enforcement = 后续 env 门控独立步骤（Phase 5），需单独评审。

验证：`tests/test_rule_weights.py` **4 passed**；合计 **83 passed**（71 smoke + 8 + 4）。真实数据 standalone → `rule_effectiveness.json` + 影子 6 行，`ineffective`→down_weight 0.5、`insufficient`→explore 1.0。

复现：`PA_SHADOW_DB=1 python3 -m runtime.model_effectiveness && PA_SHADOW_DB=1 python3 -m runtime.rule_weights`。

---

## 7. 续作 — Phase 3f：协整/spread 研究模型（第一个「真实模型」）

承「接真正的 models_used」，本轮实现系统**第一个真实统计模型**，让标签从规则名升级为真实 `models_used=["cointegration"]`。

- **新增** `runtime/cointegration.py`（numpy-only 确定性）：读 `market_price_history.json`，配对 OLS 对冲比 + spread z-score + Pearson + AR(1) 半衰期 → 研究候选信号（带 `models_used`/`source_markets`/`evidence`/`failure_conditions`，PRD §8 schema）。避开 statsmodels。
- **防伪相关护栏**（点少必须）：两腿都在动 + 不同取值数≥4 + 点数≥8 + |corr|≥0.8 + |z|≥2 + 0<半衰期≤20；每条打 `data_sufficiency`。
- 新增表 `correlation_signals`（schema→**0.3.6-phase3f-cointegration**，快照重建）+ datastore 门面 `write_correlation_signals` + orchestrator 周期末钩子 + `GET /correlation-signals`。
- **关键护栏**：研究工具（PRD §10），产物 `enforced=false`，**不接入 live executor / agent_b**。接入交易链路 = 后续 env 门控独立步骤。

验证：`tests/test_cointegration.py` **5 passed**；合计 **88 passed**。真实数据 standalone：100 市场→护栏后 5 序列/10 对/**0 候选**（10 点+多数不动，正确剔除 ±1.0 伪相关；待价格历史累积后才有候选）。⚠ 主机需 numpy，缺则钩子 best-effort 跳过。

复现：`PA_SHADOW_DB=1 python3 -m runtime.cointegration`。

---

## 8. 续作 — Phase 3f-loop：真实模型端到端闭环

把协整候选接成端到端可学习：候选 → 带 `models_used` 的信号 → review → execute → postmortem → **model_effectiveness 按真实模型归因**。分两层：

**安全层（归因骨架，additive，默认生效）**
- `signals` 表加 `models_used` 列（注册 `_EXPECTED_COLUMNS`，旧库 ALTER 补列）；`upsert_signals` 写入；schema→**0.3.7-phase3f-loop**。
- `model_effectiveness` 增 **`by_model` 尺度**（join `signals.models_used`，按真实模型聚合，一笔可计入多模型）——闭环归因终点。`GET /model-effectiveness?scope=model`。

**风险层（协整→信号桥，env 门控 `PA_COINT_SIGNALS=1`，默认关）**
- `cointegration.to_pipeline_signals()` 把候选转成带 `models_used` + Agent M 健全性字段（data_sources/logic_chain）的小仓位 probe 方向性 leg 信号；`market_meta_from_latest()` 富化价格。
- orchestrator 步骤 12.5 env 门控合入；默认关 → 信号链路零变化。**⚠ 可成交信号，仅应在 `EXECUTOR_DRY_RUN=1` 受控验证下开启，需评审后才在主机开。**

验证：`tests/test_cointegration_loop.py` **2 passed**（端到端：候选→pipeline 信号→影子 models_used→同 signal_uid 的 win postmortem→`by_model.cointegration` 归因该 win）。全量 `pytest tests/ --ignore=test_account_watchdog` **181 passed**（watchdog 15 errors = 沙箱无法 unlink 挂载文件 `data/emergency_state.json`，**环境问题，与本改动无关**，已确认）。真实 DB schema→0.3.7、`signals.models_used` 已补、`by_model` 上线（当前空，尚无协整成交，符合预期）。

复现闭环（隔离）：`pytest tests/test_cointegration_loop.py -v`；主机受控：`EXECUTOR_DRY_RUN=1 PA_SHADOW_DB=1 PA_COINT_SIGNALS=1` 跑 run_once。

---

## 9. 受控端到端验证（2026-06-05，沙箱，非破坏）

沙箱跑不全 18 步真实 run_once（联网采集 + Agent M 子进程需密钥），故按 3d 签收同款方法：**隔离 base_dir + 隔离影子库 + 合成协整候选**，直接驱动**真实** orchestrator/executor 方法，不触真实 data/、不联网、不下单。

新增 `tests/test_cointegration_loop_orchestrator.py`（**3 passed**），逐条验证真实路径：

| 判据 | 结果 | 证据 |
|---|---|---|
| 门控开→真实 `_consolidate_signals_for_review` 注入协整 probe 信号 | ✅ | signals.json 含 `source=cointegration`、`models_used=["cointegration"]`、价格从 latest_data 富化 |
| 影子 `signals.models_used` 落列 | ✅ | `SELECT models_used FROM signals WHERE source='cointegration'` 命中 cointegration |
| **门控关（默认）→零注入** | ✅ | 同路径无任何 cointegration 信号 |
| 真实 `SignalExecutor` dry_run → **success=0** | ✅ | `total=2 success=0 dry_run=2`，statuses 全 dry_run |
| by_model 闭环归因 | ✅ | 造一笔 win postmortem 后 `by_model` 出现 `cointegration`（n=1,win=1） |

一次性可读全链路演示（隔离目录、跑完即清理）确认：协整候选(z=4.74,corr=0.96) → 真实汇总注入 2 条 probe → 真实 executor 0 成功/2 dry-run → `by_model.cointegration` 归因。

全量回归：`pytest tests/ --ignore=test_account_watchdog` → **184 passed**（watchdog 15 errors = 沙箱无法 unlink 挂载文件 `data/emergency_state.json` 的环境问题，与本改动无关）。

**结论**：Learning Runtime 完整闭环（协整发现 → 带依据信号 → 风控分级 → dry-run 成交 → 复盘 → by_model 学习）在**真实代码路径**上受控复现，护栏（门控默认关、success=0）全部成立。主机最终签收只差：venv 装 numpy + 真实 run_once 下 `EXECUTOR_DRY_RUN=1 PA_COINT_SIGNALS=1` 跑一轮（需评审）。

---

## 10. 自评审 + 两个 🟠 修复（同日）

对全会话改动做了独立评审。结论：无阻断缺陷，安全层（models_used 列 + by_model）通过可常开；风险层（协整桥）有条件通过维持默认关。标记并**已修复**两个语义 🟠：

- **Fix1 配对原子完整性**：协整两腿独立进 pipeline，若只批一腿成裸方向单。修：每腿加 `pair_id/pair_role/pair_partner_market`；`enforce_pair_integrity` 孤腿整对丢弃；orchestrator 步骤 13.5（Agent M 后、执行前，env 门控）经 `datastore.put_approved_signals` 重写执行器输入。
- **Fix2 edge 单位校准**：协整 `expected_value` 改无量纲预期收益率（`|z|·spread_std/price`，原价差移动入 evidence）；`model_effectiveness` 加方向感知 `realized_return`（NO 取反，经真实数据确认 entry/exit=yes 价）+ `avg_realized_return`，`edge_realization` 改无量纲收益率比值。

验证：`tests/test_cointegration_fixes.py` **8 passed**；全量 `--ignore=test_account_watchdog` **191 passed**。受控演示孤腿剔除成立。

剩余低优先项（记录、未做）：跨周期去重/冷却、TOP_K 放量调参、降级价格腿跳过、shadow `_CONN` 测试 fixture 统一——均 dry-run 无碍，主机 enforcement 前再处理。

---

## 11. 续作 — Phase 3f-x：跨资产协整（Polymarket × 外部资产，PRD §9）

落实「一个市场变化→去别的市场找信号」（BTC→Polymarket 概率）。复用协整引擎，新增数据底座 + 跨资产配对 + 桥单腿处理。

- **数据底座**：`datastore.record_asset_prices` → `data/asset_price_history.json`（{symbol:[{ts,price,kind}]} 滚动 60，json 事实源）；`price_history.load_asset_history/asset_series_for`；orchestrator 步骤1.5 从 latest_data 抽 okx(crypto)/us_stocks/btc_funding 无条件记录。
- **跨资产配对**：`cointegration.find_cross_asset_candidates` 复用 `analyze_pair`（OLS 吸收量纲）；`_build_cross_asset_signal` 出 `pair_type=pm_asset` + `anchor_asset`，**只有 PM 腿 tradeable**；`compute` 合并 pm_pm+pm_asset。
- **桥单腿**：`to_pipeline_signals` 只发 tradeable 腿；pm_asset → 1 条 PM 方向性信号，`pair_id=None`（自动过完整性门），`models_used=["cointegration"]` 照常进 by_model。

验证：`tests/test_cointegration_cross_asset.py` **3 passed**；全量 **194 passed**。演示 BTC↔PM 候选 z=4.56/corr=0.99 → 桥出 1 条 PM 腿（dir=NO, anchor=BTC）。真实数据 n_assets=0（asset_price_history 待 orchestrator 累积，冷启动预期）。

复现：`PA_SHADOW_DB=1 python3 -m runtime.cointegration`（n_assets>0 需先跑过带新步骤1.5的周期）。

---

## 12. 续作 — Phase 3g：HMM 市场状态识别（第二个「真实模型」，PRD §11 优先级 2）

用户在本轮 PRD 复盘后选定下一步做 **HMM regime**。严格沿用 3f 协整的「研究工具 + `enforced=False` + 影子表 + orchestrator 周期末钩子 + 单测」骨架，全加法非破坏。

- **新增** `runtime/regime_hmm.py`（numpy-only 确定性）：价格序列一阶差分 → K=2 高斯 HMM（分位数确定性初始化 + 带 scaling 的 Baum-Welch EM + Viterbi 解码）→ 按方差贴标签 calm/turbulent，当前 regime=末点解码态。产出 `models_used=["hmm"]` + evidence(transition_matrix/states/separation/posterior) + failure_conditions（PRD §8 schema），含 `regime_shift`/`news_driven`/`regime_confident`。同时分析 PM 市场(yes_price) + 外部资产(price)。
- **防伪 regime 护栏**：MIN_OBS=10 + 不同取值≥4 + 序列在动；方差分离<1.5 或后验<0.6 → 标 not_confident（不剔除）；每条打 data_sufficiency。
- 新增表 `regime_states`（schema→**0.3.8-phase3g-hmm-regime**，快照整表重建，非加列无需登记 `_EXPECTED_COLUMNS`）+ datastore 门面 `write_regime_states` + `_shadow.upsert/query_regime_states` + orchestrator 周期末**协整之后**钩子 + `GET /regime-states?regime=...`。
- **关键护栏**：研究工具（PRD §10），`enforced=False`，**不接入 live executor / agent_b**。regime 喂 sizing/风控/regime 有效性学习 = 后续 3g-loop env 门控独立步骤。

**验证（本机无 numpy + PyPI 不可达，分层验证）**：
- ✅ stdlib（datastore/_shadow 不依赖 numpy）：schema 自迁移建 `regime_states`(18 列) + bump 0.3.8；synthetic 报告经 `write_regime_states` → json 落盘 + 影子 2 行；`query_regime_states` 默认排序（regime_shift 在前）+ regime 过滤（turbulent/calm）全命中。
- ✅ `py_compile` 模块 + 单测语法通过。
- ✅ **HMM 算法纯 stdlib 同方程镜像**：合成 calm→turbulent 序列 → separation=33.5、turbulent 尾正确解码、末点 0.25 跳变触发 news_driven。numpy 版与镜像同方程。
- ⏳ **主机签收差**：在有 numpy 的环境跑 `pytest tests/test_regime_hmm.py tests/test_smoke.py -v`（新增 7 单测）+ `PA_SHADOW_DB=1 python3 -m runtime.regime_hmm`。

**非破坏**：`regime_hmm` 仅惰性导入（orchestrator try-块内 + 单测）；runtime 其余模块加载不依赖 numpy（已实测）；钩子在既有 broad try/except 内，numpy 缺失被吞、周期不受影响。详见 PHASE3G_HMM_REGIME.md。

下一步候选：3g-loop（regime × postmortem 归因 → regime_effectiveness）/ GARCH（优先级 3）/ Kelly·Markowitz sizing（优先级 4/5）。

---

## 13. 续作 — Phase 3g-loop / 3h / 3i（用户「依次都做」一次性交付）

按 PRD §11/§13 顺序，一口气补齐 regime 学习闭环 + GARCH + sizing。三块都沿用「研究/建议产物 + `enforced=False` + 影子表 + orchestrator 周期末钩子 + 单测」骨架，全加法非破坏。orchestrator 周期末钩子链现为：复盘 → model_effectiveness → rule_weights → cointegration → regime_hmm → **regime_effectiveness → garch → position_sizing**。

**Phase 3g-loop — regime 有效性学习（`runtime/regime_effectiveness.py`，numpy-free）**
- postmortems × 市场 regime（join `regime_states.json` 当前 regime 作开仓 regime **代理**）分桶，**复用 model_effectiveness 指标计算**（DRY）→ 每 regime 胜率/盈亏/decay/有效性裁定。
- 表 `regime_effectiveness`（schema→0.3.9）+ datastore `write_regime_effectiveness` + `GET /regime-effectiveness`。无 regime_states→全 unknown 降级。
- ✅ **本机端到端跑通**（numpy-free）：calm 3win→effective、turbulent 3loss→ineffective、无映射→unknown、无文件→全 unknown。`tests/test_regime_effectiveness.py` 4 单测。

**Phase 3h — GARCH(1,1) 波动率（`runtime/garch.py`，numpy-only）**
- 方差目标化 GARCH(1,1)：omega=V·(1−α−β)，(α,β) 二维网格 MLE，平稳约束 α+β≤0.985，确定性 argmax（避开 arch/scipy）。出 persistence/forecast_vol/risk_state/vol_trend/clustering/vol_spike，`models_used=["garch"]`。与 HMM 互补。
- 表 `volatility_states`（schema→0.3.10）+ `write_volatility_states` + `GET /volatility-states`。`tests/test_garch.py` 7 单测。

**Phase 3i — Kelly+Markowitz sizing（`runtime/position_sizing.py`，numpy-only）**
- 组合三模型：边←cointegration、方差←GARCH forecast_vol²、regime←HMM 缩放。Kelly `clamp(κ·μ/σ²,0,F_MAX)×scaler`；Markowitz `w∝Σ⁻¹μ` long-only 归一（pinv）。
- 表 `sizing_suggestions`（schema→0.3.11）+ `write_sizing_suggestions` + `GET /sizing-suggestions`。`tests/test_position_sizing.py` 8 单测。
- **关键护栏**：建议产物 `enforced=False`，**不接入 agent_m/executor/probe 仓位**（probe 仍固定×0.25）；接 enforcement=Phase 5 env 门控 + 边量纲校准，需评审。

**验证（已用临时 numpy venv 完成主机签收，2026-06-05）**：
- ✅ **本轮 4 个新测试文件 26/26 passed**（3g 7 + 3g-loop 4 + 3h 7 + 3i 8）。
- ✅ **全量回归 220 passed**（`pytest tests/ --ignore=tests/test_account_watchdog.py`；上轮基线 194 + 新增 26 = 220；watchdog 仍为已知沙箱挂载环境问题，与本轮无关）。其中 smoke 71 passed、协整/有效性套件 29 passed。
- ✅ **真实数据 standalone**（`PA_SHADOW_DB=1 python3 -m runtime.<mod>`）：4 模块全部无错运行。冷启动如实表现——regime_hmm/garch `n_considered=0`（每序列价格历史~10 点 < MIN_OBS+1=11，护栏正确拒噪）；position_sizing `n_candidates=0`（correlation_signals 冷启动空）；regime_effectiveness 12 笔历史 postmortems 全归 unknown（无 regime_states，诚实降级，verdict=decayed）。机制全就绪，待价格历史累积后才有统计意义。
- ✅ **真实 runtime.db 迁移**：0.3.7 → **0.3.11-phase3i-sizing**，4 张新表（regime_states/regime_effectiveness/volatility_states/sizing_suggestions）已建。运行前已备份 DB 到 `/tmp/pa_3ghi_backup`。
- 环境备注：本机 venv 是 homebrew externally-managed（PEP 668）无 numpy；用 `/tmp/pa_test_venv`（python3 -m venv + pip `--trusted-host` 绕过 macOS CA 证书问题）装 numpy 2.4.6/pytest 9.0.3 + aiohttp/requests/pandas/openai 跑全套。
- ✅ `py_compile` + lint 全清；runtime 包无 numpy 仍可导入（非破坏）。

详见 PHASE3G_HMM_REGIME.md §6 / PHASE3H_GARCH.md / PHASE3I_SIZING.md。

---

## 14. 新增 requirements.txt（依赖固化）

项目此前无依赖清单（靠隐性环境）。本轮扫描全库 import 后新增 `requirements.txt`：
- 核心：`numpy>=2.0`（runtime 真实模型必需）/ `requests>=2.31` / `aiohttp>=3.9` / `openai>=1.40` / `pandas>=2.2`；
- Paper API：`fastapi>=0.110` / `uvicorn>=0.27`；测试：`pytest>=8.0`；
- 可选数据源（注释，惰性 import）：yfinance / ccxt / longbridge。
- 排除未实际 import 的 yaml/dotenv/pydantic（pydantic 经 fastapi 传递）。
- 版本为已验证下限（本轮 220 passed 跑在 numpy 2.4.6 / pytest 9.0.3）；`pip install --dry-run` 在 Python 3.13 解析通过（fastapi 0.136.3/uvicorn 0.49.0）。
- CLAUDE.md「常用命令」已加安装行 + macOS SSL `--trusted-host` 提示。

---

## 15. Phase 5 — 纸面强制层 enforcement（learning 产物接回交易行为）

PRD 下一阶段。把 Phase 3 一直停在 `enforced=False` 建议层的两个 learning 产物第一次接进 paper 信号链路，
闭合「发现→交易→复盘→学习」回路——严格限定在 paper/dry-run。

- `runtime/enforcement.py`（**stdlib-only**，门控关时恒等）：在 orchestrator 汇总 `signals.json`、写盘前调整每条信号 `position_size`。
  - sizing（`PA_ENFORCE_SIZING=1`）：用 `sized_fraction` 作基准，join `pair_id`/`signal_uid`→`sizing.signal_uid`，回退 `market_id`。
  - weight（`PA_ENFORCE_WEIGHTS=1`）：`base×weight`，join `learned_rule_match`→rule/family（复用 `model_effectiveness._rule_family`）。
  - 顺序：sizing→weight→clamp[floor,max]→**默认只降险**(≤原始)。`PA_ENFORCE_LEARNING=1` 便捷=两者。
- 接线：`orchestrator._consolidate_signals()` 汇总后/`put_signals` 前，`any_enabled()` 为真才调（best-effort，异常按原始信号继续）。
- 存储：`write_enforcement_audit` 门面 + 表 `enforcement_audit`（schema→**0.3.12-phase5-enforce**）+ `GET /enforcement-audit` + 每条改动信号内 `enforcement` 证据。
- **关键护栏**：只改 `position_size`，**不绕过 Agent M / executor dry-run**（`success` 仍由 `EXECUTOR_DRY_RUN` 定）；默认全关→零回归；只降险（≤原始≤MAX_SIZE=0.10）；**绝不归零探针**（floor=0.005）；仅 `EXECUTOR_DRY_RUN=1` 受控验证下开。
- 数据流：learning 产物周期末重算，本层下一周期读取——学习滞后一周期，正确可解释。

**验证（临时 numpy venv，2026-06-05）**：
- ✅ `tests/test_enforcement.py` **17/17 passed**（门控关恒等、sizing 三种 join、floor 不归零、max 硬上限、降险/放大、weight 降权/family 回退/keep 不放大、组合、gates env、落审计、冷启动）。
- ✅ **全量回归 237 passed**（220 + 17，`--ignore=tests/test_account_watchdog.py`），零回归。
- ✅ dry-run 端到端（隔离 `PA_DB_PATH`）：sizing 0.05→0.02（turbulent）/ weight 0.08→0.04（down_weight）/ 无命中 0.05 不变；schema 迁移 0.3.11→**0.3.12-phase5-enforce**，`enforcement_audit` 影子表正确落 2 行。
- ✅ `py_compile` + lint 全清。

**未做（需评审/真金授权）**：边量纲校准为无量纲收益率；Phase 4 live probe（真实小额下单 / live 风控 / 自动止损）。

**校准验证（`scripts/enforcement_calibration_sim.py`，隔离沙箱跑 3 轮，全程 dry-run，不碰真实 data/DB）**：
- A 真实基线：8 条真实 signals 全 weight 命中但全 `w=1.0`(explore)、sizing 候选 0 → **净改动 0**（冷启动如实，非缺陷）。
- B sizing 校准扫描（真实 kelly_fraction）：🔴 **关键发现——`expected_edge≳0.005` 时 Kelly 即撞 F_MAX 饱和**（边是价格单位代理、量纲偏大），sizing 退化为「一律 F_MAX×regime」。**sizing live 前必须先把边校准为无量纲收益率**；在此之前不建议开 `PA_ENFORCE_SIZING`。
- C live 情景端到端：sizing 降险≤原始 / down_weight 0.25→0.025 / 负边→floor 0.005(不归零) / 无命中不变；影子 `enforcement_audit` 落 3 行（schema 0.3.12）。机制正确。
- 🟡 weight 强制安全但近乎惰性：唯一 down_weight 是 `unknown`（postmortem 兜底标签），与 live `learned_rule_match`(mid_range_*) 不对齐 → 实际 0 改动；需积累更多带规则归因的 paper 反馈。

详见 PHASE5_ENFORCEMENT.md §8-10。新增 `scripts/enforcement_calibration_sim.py`（可重复跑的离线校准沙箱）。

**边量纲校准修复（采纳「先校准」后实施，2026-06-05）**：
- `cointegration` 候选新增 `entry_price`（代表腿当前价位）+ 无量纲 `expected_return`=(1−φ)·|z|·spread_std/入场价（AR(1) 每步预期回归收益率，与 realized_return 同量纲）；`expected_edge`（价格单位）保留 traceability。SCHEMA→`0.3.13-phase5-edge-calib`。
- `position_sizing` 改**收益率空间 Kelly**：μ 用 `expected_return`、价格单位 GARCH 方差经入场价归一 `(vol/price)²`，μ/σ² 量纲一致；旧候选无 entry_price 安全退化（向后兼容）。SCHEMA→`0.3.13`。
- 效果（z×vol 校准扫描）：饱和格 **OLD 9/9 → NEW 4/9**——高 vol 格脱离 F_MAX 恢复区分度；低 vol+强边仍撞 F_MAX（stat-arb 单步 Sharpe 本就高，κ=0.25+F_MAX 封顶按设计兜底，非 bug）。
- 单测 +3（`_dimensionless_edge`/收益率空间 suggest/向后兼容）；全量 **240 passed**，零回归；lint 清。
- 仍未做（需真实候选数据评估）：更小 κ / 持有期一致 σ²（按 half_life 累积）的进一步去饱和。

---

## 探索层 tier + 第一批候选喂闭环（"先跑出第一批候选喂闭环"，2026-06-05）

**诊断（为何 0 候选）**：磁盘真实/历史数据均无真实跨市场联动——
- 线上 `data/market_price_history.json`：100 序列各仅 10 个近似常量快照（多数 flat），无动态。
- 项目历史数据集（`data/historical/`：真实 OKX 币价 K 线 + crypto/股票锚定 PM 模拟历史，每市场 1440 小时点）：回填跑真实协整 21 市场/294 对/4 资产，**全体最大 |corr|≈0.69 < 0.8**（跨 stride 1/6/24 一致），连锚定市场都几乎不跟锚资产走 → 模型**正确拒绝**从噪声造边。
- 网络（拉真实 PM/币价历史）被代理硬封 403，本环境无法回填真实数据。
- 结论：当前环境无诚实办法出真实研究候选；放水降阈值=黑盒噪声喂闭环，不做。

**探索层（PRD §6 paper_probe 弱关联低风险试错；env 门控 `PA_COINT_EXPLORE=1` 默认关）**：
- `cointegration`：`_is_candidate(st, corr_min, z_min)` 参数化；`_classify_tier` 分 research(严格 0.8/2.0)/exploration(放松 0.5/1.5，`PA_COINT_EXPLORE_CORR`/`_Z` 可调)/None；**半衰期(平稳性)过滤恒定不放松**。
- 候选加 `tier` 字段；exploration **置信封顶 35**（`EXPLORE_CONF_CAP`→Agent M 路由 paper_probe）+ 追加弱关联 failure_condition。`find_candidates`/`find_cross_asset_candidates` 报 `n_candidates_research`/`_exploration` + `explore_enabled`，research 优先排序。
- `to_pipeline_signals`：exploration 用更小 probe 仓位 0.02（研究层 0.05），signal 带 `tier` + logic_chain 注记。SCHEMA→`0.3.14-phase5-explore-tier`。
- 门控关 → `tier=research`，行为**零回归**。

**自举/诊断工具** `scripts/bootstrap_cointegration_from_cache.py`（隔离 sandbox，不碰线上 `data/`）：回填 OKX 币价+历史 PM → 跑真实协整；0 候选时打印「卡在哪个护栏 + corr/z 分布 + top 配对」诊断；`--explore` 开探索层；`--demo` 注入**合成**共动配对演示探索层端到端。
- 验证：`--explore --demo` → exploration 候选 corr=0.595/z=2.21/conf=35.0 → `to_pipeline_signals` 出 2 条 ps=0.02 paired probe（`models_used=cointegration`）；门控关 + 同合成对 → 0 候选（gate 正确）。

**测试**：`tests/test_cointegration.py` +5（弱关联仅探索层收/门控默认关零回归/门控开出低置信探索 probe/平稳性过滤与层无关/pipeline 探索更小仓位+tier）；`tests/` **192 passed**（`test_smoke` 需外部 longbridge SDK，环境缺，预存非本次回归），lint 清。

**主机 runbook** `RUNBOOK_COINTEGRATION_LOOP.md`：真实路径（主机累积真实 PM 历史/回填真实币价 → `PA_COINT_SIGNALS=1` 喂闭环 dry-run）+ 探索层冷启动加速 + Phase 5 强制层；安全边界（全门控默认关、全程 dry-run、不绕 Agent M、不放水研究阈值）。

---

## 16. Phase 5 主机开闸（「按照 PRD 执行下一步」，2026-06-05）

协整已出货（7 sizing / 14 coint 信号）后，在 **dry-run** 下默认开启纸面强制层，闭合 learning→仓位回路：

- `scripts/run_host_loop.sh` 默认 `PA_ENFORCE_LEARNING=1`（`PA_ENFORCE_LEARNING=0` 可关）；周期末打 `[enforce]` 摘要。
- 新增 `scripts/verify_enforcement_live.py`：开闸前只读演练（22 信号：sizing 命中 16、weight 8、**净改动 0**——只降险 + Kelly>probe 的预期冷启动表现）。
- `RUNBOOK_COINTEGRATION_LOOP.md` §2c、`PHASE5_ENFORCEMENT.md` §10 已更新。

## 17. Phase 4 — Live Probe（用户已授权，2026-06-05）

- **新增** `runtime/live_probe.py`：双重门控（`PA_LIVE_PROBE=1` + 非 `EXECUTOR_DRY_RUN`）、probe 过滤、USD/周期/日限额、risk_snapshot 阻断、`STOP_TRADING` 日亏损熔断；urgent 止损卖单优先。
- **接线**：`signal_executor` 无授权 → `blocked_no_live_gate`；`sell_executor` STOP_TRADING 下仅放行 urgent；orchestrator 日志区分 `live_probe` / `live_unauthorized`。
- **脚本** `scripts/run_live_probe_loop.sh`（与 dry-run `run_host_loop.sh` 分离）；文档 `PHASE4_LIVE_PROBE.md`。
- **测试** `tests/test_live_probe.py`。
- **未做**：全量 non-probe auto-live；pm-trader 成交回报精细 PnL 对齐。
