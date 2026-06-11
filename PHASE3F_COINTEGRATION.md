# Phase 3f — 协整 / spread 研究模型（第一个「真实模型」）

> 目标（对应新 PRD 第十一节第一优先级 + §9 跨市场关联发现 + §10「模型是研究工具」）：
> 让系统拥有第一个**真实统计模型**，不再只有 agent_b 的规则匹配。由此 Learning Runtime
> 的模型标签从「规则名（learned_rule_match）」升级为**真实 `models_used=["cointegration"]`**。

---

## 1. 交付物

| 文件 | 改动 |
|---|---|
| `runtime/cointegration.py` | **新增**。numpy-only 确定性协整/spread 引擎：配对 OLS 对冲比 + spread z-score + Pearson + AR(1) 半衰期 → 研究候选信号。 |
| `runtime/schema.sql` | **新增表** `correlation_signals`；schema_version → `0.3.6-phase3f-cointegration`。 |
| `runtime/_shadow.py` | `upsert_correlation_signals`（快照语义整表重建）+ `query_correlation_signals`。 |
| `runtime/datastore.py` | 门面 `write_correlation_signals`（写 `data/correlation_signals.json` 研究产物 + 影子）。 |
| `orchestrator.py` | 周期末 rule_weights **之后**调 `cointegration.compute()`（`PA_SHADOW_DB` 块内，best-effort）。 |
| `runtime/api.py` | `GET /correlation-signals`。 |
| `tests/test_cointegration.py` | **新增 5 单测**（合成数据）。 |

---

## 2. 方法（Engle-Granger 轻量版，仅 numpy）

对一对市场价格序列 a、b（对齐末 N 点，事实源 = Phase 3b 的 `market_price_history.json`）：

1. **对冲比 beta**：OLS 把 a 回归到 b（`a ≈ beta·b + c`）。
2. **spread** = `a − beta·b`；记 mean / std；当前点 `z = (spread[-1] − mean) / std`。
3. **相关** `corr = Pearson(a, b)`。
4. **AR(1) 系数 phi**：`spread[t]` 回归 `spread[t-1]`；**半衰期** = `−ln2 / ln(phi)`（0<phi<1 才有意义）。
5. **均值回归判据**：0<phi<1（spread 收敛）+ |corr| 高 + |z| 越界 → 配对回归研究候选。

避开 `statsmodels`（主机 venv Python 3.9，依赖最小化），全部用 numpy 实现，纯确定性、沙箱可单测。

### 输出信号 schema（PRD §8 可解释结构）
```json
{
  "models_used": ["cointegration"],
  "method": "engle_granger_lite",
  "source_markets": ["<id_a>", "<id_b>"],
  "direction": "spread_revert",
  "legs": [{"market_id": "<rich>", "expectation": "down"}, {"market_id": "<cheap>", "expectation": "up"}],
  "evidence": {"beta": .., "corr": .., "spread_mean": .., "spread_std": .., "zscore": .., "ar1_phi": .., "half_life": .., "n_points": ..},
  "confidence": 0-90,
  "expected_edge": <预期价差压缩>,
  "failure_conditions": ["相关性破裂", "spread 非平稳/走宽", "流动性骤降", "样本不足"],
  "data_sufficiency": "low|medium"
}
```

---

## 3. 防伪相关护栏（点少时必须）

当前每序列仅 ~10 点，极易出现 ±1.0 伪相关。故要求：

- 两腿都**真的在动**（`std > eps`）且**不同取值数 ≥ 4**（`MIN_DISTINCT`，拦截 2-3 值序列的伪 ±1.0）；
- 点数 ≥ 8（`MIN_POINTS`）；`|corr| ≥ 0.8`；`|z| ≥ 2.0`；`0 < half_life ≤ 20`；
- 候选按 `|z|` 排序取头部 `TOP_K=20`；每条打 `data_sufficiency`（n<20 → low）。

---

## 4. 关键纪律

- **研究工具，非交易策略**（PRD §10）：产出写入独立产物 `data/correlation_signals.json` + 影子表，
  **`enforced=false`，不接入 live executor / agent_b 信号链路**。
- 把候选喂进真正的 signals→review→execute 链路 = 后续 **env 门控的独立步骤**，需单独评审（同 3e-2）。
- 纯确定性、numpy-only、加法产物，不改任何交易行为；JSON 仍是事实源，影子表可重建。

---

## 5. 验证（2026-06-05 沙箱）

- 单测：`pytest tests/test_cointegration.py` → **5 passed**（对冲比还原/半衰期单调/伪相关护栏/合成协整对成候选/compute 落盘）。合计 **88 passed**（71 smoke + 8 + 4 + 5）。
- 真实数据 standalone（`PA_SHADOW_DB=1 python3 -m runtime.cointegration`）：
  - 100 市场 → 护栏后 **5 个**有效序列、评估 **10 对**、**0 候选**。
  - 这是**正确且诚实的结果**：10 点、多数序列近乎不动，无统计稳健的协整候选；
    护栏正确剔除了原始探索中见到的 ±1.0 伪相关对（其不同取值数 <4）。
  - schema 自迁移到 `0.3.6-phase3f-cointegration`，表 + json 产物已建。
- ⚠ **主机依赖**：本模块需 `numpy`（沙箱 2.2.6 可用）。主机 venv 若缺则 orchestrator 钩子会 best-effort 跳过（不影响周期）；建议主机 venv `pip install numpy`。

> 随 Phase 3b 价格历史滚动累积（每市场最多 60 点）+ paper_probe 放量，
> 有效序列与候选会增多，模型才进入有统计意义的工作区。

---

## 5b. Phase 3f-loop — 真实模型端到端闭环（2026-06-05 续）

把协整候选接成**端到端可学习**：候选 → 带 `models_used` 的信号 → review → execute → postmortem → **model_effectiveness 按真实模型归因**。分两层，安全层默认生效、风险层 env 门控默认关。

### 安全层（归因骨架，additive，默认生效）
| 改动 | 说明 |
|---|---|
| `signals` 表加 `models_used` 列 | 注册 `_EXPECTED_COLUMNS`（旧库 ALTER 补列）；`upsert_signals` 写 `_j(models_used)`。schema→`0.3.7-phase3f-loop`。 |
| `model_effectiveness` 增 `by_model` 尺度 | join 取 `signals.models_used` → 按**真实模型**聚合（一笔可计入多模型）。这是闭环归因终点：协整在此被学习。`GET /model-effectiveness?scope=model`。 |

### 风险层（协整→信号桥，env 门控 `PA_COINT_SIGNALS=1`，默认关）
- `cointegration.to_pipeline_signals(report, market_meta)`：把候选转成**方向性 leg 信号**（cheap leg 预期涨→YES、rich leg 预期跌→NO），带 `models_used=["cointegration"]` + Agent M 健全性所需的 `data_sources`/`logic_chain`，小仓位（0.05 probe 量）。
- `market_meta_from_latest()`：从 `latest_data.json` 富化 leg 价格/名称/slug。
- orchestrator 步骤 12.5（信号汇总）**env 门控**合入：`PA_COINT_SIGNALS=1` 才把 probe 信号 extend 进 `fresh_signals`；默认关 → 信号链路零变化。
- ⚠ **这些是可成交信号**：开启时必须配 `EXECUTOR_DRY_RUN=1` 做受控验证；live 下会经 Agent M 分级 + dry_run 护栏，但仍属交易行为，需评审后才在主机开启。

### 验证（2026-06-05）
- 端到端归因测试 `tests/test_cointegration_loop.py` **2 passed**：合成候选→`to_pipeline_signals`(带 models_used)→`put_signals`(影子 `signals.models_used` 落列)→合成同 `signal_uid` 的 win postmortem→`model_effectiveness` 的 **`by_model` 出现 `cointegration` 且归因该 win**。
- 全量：`pytest tests/ --ignore=test_account_watchdog` → **181 passed**（watchdog 15 errors 为沙箱无法 unlink 挂载文件 `data/emergency_state.json` 的环境问题，**与本改动无关**）。
- 真实 DB：schema 自迁移到 `0.3.7-phase3f-loop`，`signals.models_used` 列已补；`by_model` 尺度上线（当前空——尚无协整成交，符合预期）。
- 默认关验证：`PA_COINT_SIGNALS` 未设时 orchestrator 信号汇总不变（smoke 全过）。

---

## 5c. 评审修复项（2026-06-05，两个 🟠 落地）

自评审标记的两个语义问题已修复，仍全程 env 门控 + dry-run + 加法。

### Fix1 — 配对原子完整性（协整两腿同进同出）
**问题**：协整是价差套利，但桥把候选拆成两条独立方向性腿；若 Agent M 只批一腿 → 裸方向赌注，交易的东西 ≠ 模型 edge。
**修复**：
- `to_pipeline_signals` 给每腿加 `pair_id`（=候选 uid，两腿共享）/`pair_role`/`pair_partner_market`。
- `enforce_pair_integrity(signals) -> (kept, dropped)`：协整腿按 pair_id 分组，仅当本腿 + partner 腿都在场才保留整对，孤腿整对丢弃；非协整信号原样通过。
- orchestrator **步骤 13.5**（Agent M 后、执行前，env 门控）应用，经新门面 `datastore.put_approved_signals` 重写 approved_signals.json（只改执行器输入，不改 review_results 审计记录）。Agent M 透传原始 signal dict（`[r["signal"] for r in approved]`），故 pair 字段在 approved 阶段可见。

### Fix2 — edge 单位校准（无量纲收益率）
**问题**：协整 `expected_edge=|z|·spread_std` 是价差价格单位，而 `edge_realization` 拿它除以美元 realized_pnl，口径错配。
**修复**：
- 协整 leg `expected_value` 改为**无量纲预期收益率** `min(1, |z|·spread_std / leg_price)`；原价差移动保留在 `evidence.expected_spread_move`。
- `model_effectiveness` 加**方向感知** `_realized_return`（YES=`(exit-entry)/entry`，NO 取反——经真实数据确认 entry/exit 是 yes 价、NO 在 yes 价跌时盈利）+ `avg_realized_return`；`edge_realization = avg_realized_return / avg_expected_edge`（两侧同为收益率）。保留 `avg_realized_pnl`（美元）作参考。

### 验证
- 新增 `tests/test_cointegration_fixes.py` **8 passed**（配对元信息/完整对存活/孤腿丢弃/非协整透传/收益率口径/方向感知 realized_return/无量纲 edge_realization）。
- 全量 `pytest tests/ --ignore=test_account_watchdog` → **191 passed**。
- 受控演示：完整对 kept=2/dropped=0；Agent M 只批一腿 → kept=0/dropped=1（裸腿剔除）。

---

## 5d. Phase 3f-x — 跨资产协整（Polymarket × 外部资产，PRD §9）

落实 PRD §9「一个市场变化 → 去别的市场找信号」（BTC 波动 → Polymarket 概率）。复用同一协整引擎，把 Polymarket 概率序列与 collectors 已采的外部资产序列配对。

### 数据底座（新增）
- `datastore.record_asset_prices(points)` → `data/asset_price_history.json`（`{symbol:[{ts,price,kind}]}` 滚动 cap=60，json 事实源，不落影子）。
- `price_history.load_asset_history` / `asset_series_for` 读取。
- orchestrator 步骤 1.5：从 `latest_data` 抽 `okx`(crypto spot)、`us_stocks`(price)、`btc_funding_rate`(macro) **无条件**记录（与 market_price_history 同周期、best-effort）。

### 跨资产配对
- `cointegration.find_cross_asset_candidates`：每个 Polymarket 市场(yes_price) × 每个外部资产序列，**复用 `analyze_pair`**（OLS 对冲比吸收量纲差异，corr/z/半衰期量纲无关）。
- `_build_cross_asset_signal`：`pair_type="pm_asset"` + `anchor_asset`/`anchor_kind`；两腿中**只有 Polymarket 腿 tradeable=True**（外部资产是外生锚，本系统不可成交）。`compute()` 把 pm_pm + pm_asset 候选合并，报告含 `n_candidates_pm_pm`/`n_candidates_pm_asset`/`n_assets`。

### 桥的处理（单可成交腿）
- `to_pipeline_signals` 只对 `tradeable` 腿发信号：pm_asset → **1 条** Polymarket 方向性信号（z>0→pm 偏贵→NO；z<0→YES），`pair_id=None`（单腿，配对完整性 N/A，自动过门），`source_markets=[pm, asset]`、`anchor_asset` 透传。`models_used=["cointegration"]` 照常 → 经 by_model 学习。

### 验证
- `tests/test_cointegration_cross_asset.py` **3 passed**（资产历史 roundtrip / 跨资产候选发现 / 桥只发 PM 腿且过完整性门）。全量 **194 passed**。
- 受控演示：BTC↔Polymarket 候选 z=4.56 corr=0.99 half_life=1.9 → 桥产出 1 条 PM 腿信号（dir=NO, anchor=BTC, pair_id=None）。
- 真实数据当前 `n_assets=0`：`asset_price_history.json` 待 orchestrator 新步骤 1.5 滚动累积（与 Phase 3b 同冷启动），属预期。

---

## 6. 下一步候选

- ✅ **闭环模型标签**：已完成（见 §5b，Phase 3f-loop）——归因骨架默认生效，协整→信号桥 env 门控默认关。
- **主机受控验证 + 评审开启桥**：主机 venv 装 numpy；`EXECUTOR_DRY_RUN=1 PA_SHADOW_DB=1 PA_COINT_SIGNALS=1` 跑 `run_once`，确认 probe 信号经 Agent M 分级 + dry_run（success=0），平仓后 `by_model.cointegration` 出现真实样本。评审通过再考虑 live。
- **更多模型**（PRD 第十一节）：HMM（regime）、GARCH（波动聚集）、Markowitz（组合）、Kelly（仓位）——复用本模块的「确定性引擎 + 研究产物 + 影子表 + models_used 归因」骨架。
- ✅ **跨资产 spread**：已完成（见 §5d，Phase 3f-x）——Polymarket × 加密/美股/宏观。
- **dashboard**：`/research` 加「协整候选（含跨资产）」卡片（读 `GET /correlation-signals`）。
- **加固待办**（enforcement 前）：跨周期去重/冷却、TOP_K 调参、降级腿跳过、shadow `_CONN` 测试 fixture 统一。

---

## §5e 探索层 tier（Phase 5 / PRD §6 弱关联低风险试错，2026-06-05）

**动机**：冷启动期真实数据稀薄、严格阈值（corr≥0.8）常 0 候选；PRD §6 主张**大量低风险 paper_probe 攒反馈**而非等高置信。故加 env 门控的探索层，让弱关联也能以低置信小额 probe 进闭环，由 `model_effectiveness.by_model` 事后验证/降权。

**实现（`runtime/cointegration.py`，SCHEMA→`0.3.14-phase5-explore-tier`）**：
- `_is_candidate(st, corr_min=CORR_MIN, z_min=Z_MIN)` 参数化阈值；`_explore_cfg()` 读 `PA_COINT_EXPLORE`（默认关），阈值 `PA_COINT_EXPLORE_CORR`(0.5)/`PA_COINT_EXPLORE_Z`(1.5) 可覆盖。
- `_classify_tier(st, explore)`：过严格→`research`；否则过放松且探索开→`exploration`；都不过→None。
- **半衰期(平稳性)过滤恒定**：只放松相关/偏离，价差仍须均值回归（不追非平稳趋势）。
- 候选加 `tier`；exploration **置信封顶 `EXPLORE_CONF_CAP=35`**（→Agent M 路由 paper_probe）+ 首条 failure_condition 标注弱关联与待复盘验证。
- `to_pipeline_signals`：exploration 用 `EXPLORE_POSITION_SIZE=0.02`（研究层 0.05），signal 带 `tier` + logic_chain 注记。
- 报告新增 `n_candidates_research`/`n_candidates_exploration`/`explore_enabled`；research 优先排序。
- **门控关 → `tier=research`，行为零回归**（单测保证）。

**自举/诊断**：`scripts/bootstrap_cointegration_from_cache.py`（隔离 sandbox，不碰线上 `data/`）回填 `data/historical/` 真实 OKX 币价 + 历史 PM → 跑真实协整；0 候选时打印护栏诊断；`--explore` 开探索层、`--demo` 注入合成共动配对演示端到端。

**当前数据现实**：线上 10 个 flat 快照、历史数据集最大 |corr|≈0.69——真实/探索阈值均 0 候选属**正确**（模型拒绝从噪声造边）。出真实候选需主机累积真实联动价格，见 `RUNBOOK_COINTEGRATION_LOOP.md`。

**单测**：`tests/test_cointegration.py` +5（弱关联仅探索层收 / 门控默认关零回归 / 门控开出低置信探索 probe / 平稳性过滤与层无关 / pipeline 探索更小仓位+tier）。
