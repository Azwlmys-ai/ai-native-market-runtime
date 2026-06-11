# Phase 3g — HMM 市场状态识别研究模型

> Learning Runtime PRD §11 优先级 2「HMM」+ §13「regime 学习」的第一块落地。
> 继协整（Phase 3f）之后的**第二个真实统计模型**：`runtime/regime_hmm.py`。
> 严格沿用 3f 的「研究工具 + `enforced=False` + 影子表 + orchestrator 周期末钩子 + 单测」骨架，全加法、非破坏。

---

## 1. 定位（PRD 对齐）

- PRD §11 优先级 2：**HMM** 用于 market regime / 状态识别 / 新闻驱动检测。
- PRD §13：learning agent 学习「哪个 regime 有效」——本阶段先产出**结构化 regime 标签**，
  regime 有效性学习闭环（regime × postmortem 归因）是后续 `3g-loop`（见 §6）。
- PRD §10：模型是**研究工具**，不是直接交易策略 → 产物 `enforced=False`，不接入 live executor / agent_b。

---

## 2. 方法（Baum-Welch EM + Viterbi，numpy-only）

对一条价格序列 p（Polymarket 市场 yes_price 或外部资产 price，取最近 ≤80 点）：

1. **观测** = 一阶差分 `o[t] = p[t] − p[t−1]`（预测市场概率移动幅度；价格在 [0,1]，用绝对变动而非对数收益）。
2. **K 态高斯 HMM**（默认 K=2）：每态 `(mu_k, var_k)` 高斯发射 + 转移矩阵 A + 初始分布 pi。
3. **确定性初始化**：按观测分位数切 K 组定 mu/var（无随机）；方差地板 `VAR_FLOOR_REL·全局方差` 防 EM 塌缩。
4. **Baum-Welch EM**：带 scaling 的前向后向（数值稳定，逐行减 max 后加回 → 真实 loglik），迭代至 loglik 收敛或 `MAX_ITER=80`。
5. **Viterbi** 对数空间解码最可能状态序列；**当前 regime = 末点状态**。
6. **贴标签**：按方差升序 → 方差最小=`calm`，最大=`turbulent`（K=3 中间=`normal`）。

确定性（同输入同输出，已单测）：固定初始化 + 固定迭代 + 无随机。

### 产物字段（PRD §8 可解释 schema）

每条 regime 研究产物含：`models_used=["hmm"]` / `method` / `series_id` / `series_kind`
（pm_market / crypto / us_stock / macro）/ `current_regime` / `regime_shift`（末点是否刚切换）/
`news_driven`（turbulent 态 + 末点 |变动| ≥ `NEWS_SIGMA·turbulent_std`）/ `regime_confident` /
`regime_posterior` / `evidence`（states[mean/std/weight/self_transition/expected_duration]、
transition_matrix、separation、posterior_certainty、current_volatility、loglik）/
`confidence`（封顶 90）/ `expected_edge=0.0`（regime 是状态描述非方向下注，sizing 消费在后续闭环）/
`failure_conditions` / `data_sufficiency`。

---

## 3. 防伪 regime 护栏（点少必须）

当前每序列仅 ~10 点，噪声极易被当 regime。故：

- 序列真的在动（`std>EPS`）且不同取值数 `>= MIN_DISTINCT(4)`；
- 观测数 `>= MIN_OBS(10)`（序列长度 ≥ 11），否则 `analyze_series` 返回 None；
- 两态方差分离 `separation = turbulent_std/calm_std < SEPARATION_MIN(1.5)`
  或末点后验确定度 `< 0.6` → 标 `regime_confident=False`（诚实降级，不剔除）；
- 每条打 `data_sufficiency`（`n_obs >= 25` 为 medium，否则 low）。

---

## 4. 改动清单（全加法）

| 文件 | 改动 |
|---|---|
| `runtime/regime_hmm.py` | **新增**：HMM 引擎（init/forward-backward/fit/viterbi）+ analyze_series + compute |
| `runtime/schema.sql` | 新增表 `regime_states`；schema_version → **0.3.8-phase3g-hmm-regime** |
| `runtime/_shadow.py` | `upsert_regime_states`（**快照语义整表重建**）+ `query_regime_states(regime=...)` |
| `runtime/datastore.py` | 门面 `write_regime_states`（json 事实源 + 影子 best-effort）+ 登记 `__all__` |
| `orchestrator.py` | 周期末**协整之后**加 best-effort 钩子（`PA_SHADOW_DB=1` 时 `regime_hmm.compute()`） |
| `runtime/api.py` | `GET /regime-states?regime=calm\|normal\|turbulent` |
| `tests/test_regime_hmm.py` | **新增 7 单测** |

- 新表是 `CREATE TABLE IF NOT EXISTS`（非加列）→ `_migrate` 的 executescript 自动建，**不必登记 `_EXPECTED_COLUMNS`**。
- 旧库下次 `_migrate` 自动建新表；不动任何既有表。
- 影子写为快照语义（整表 DELETE+INSERT），无 stale key；可删 `data/runtime.db` 重建。

---

## 5. 验证

本会话主机环境**无 numpy 且 PyPI 不可达（SSL 证书拦截）**，与 CLAUDE.md 既有注记一致
（「主机需 numpy，缺则钩子 best-effort 跳过」）。故按可执行/不可执行分层验证：

| 判据 | 方式 | 结果 |
|---|---|---|
| schema 自迁移建 `regime_states` + bump 0.3.8 | stdlib sqlite3 新建库 | ✅ 表 18 列、版本正确 |
| datastore json 落盘 + 影子 upsert/query + regime 过滤 + 排序 | stdlib（datastore/_shadow 不依赖 numpy） | ✅ 2 行回填、turbulent/calm 过滤命中、regime_shift 排序在前 |
| 模块 + 单测语法 | `py_compile` | ✅ 通过 |
| **HMM 算法正确性**（同方程纯 stdlib 镜像） | 合成两段 calm→turbulent 序列 | ✅ separation=33.5、turbulent 尾正确解码、末点跳变触发 news_driven |
| numpy 单测 `tests/test_regime_hmm.py`（7 个） | **待 numpy 环境** | ⏳ 本机无法执行 |

> ⏳ **主机签收差**：在有 numpy 的环境（即先前跑出 194 passed 的同一环境）执行
> `pytest tests/test_regime_hmm.py tests/test_smoke.py -v` + `PA_SHADOW_DB=1 python3 -m runtime.regime_hmm`。
> 算法镜像已确证方程正确，numpy 版与镜像同方程。

### 非破坏论证

- `regime_hmm` 仅被**惰性导入**（orchestrator 的 `PA_SHADOW_DB` try-块内 + 单测）。
  `runtime.datastore`/`_shadow`/`api` 模块加载**不依赖 numpy**（已实测无 numpy 下导入成功）。
- orchestrator 钩子在既有 broad try/except 内 → numpy 缺失/任何失败被吞、记日志，周期不受影响。
- 不碰审批/执行/学习行为；只读价格历史 json，产出独立研究产物。dry-run 链路完全不经过。

复现：
```bash
# stdlib 验证（无需 numpy）：schema + shadow + datastore 已在本会话跑通
# 算法/单测（需 numpy）：
PA_SHADOW_DB=1 python3 -m runtime.regime_hmm
pytest tests/test_regime_hmm.py -v
curl 'localhost:8848/regime-states?regime=turbulent'   # 主机起 API 后
```

---

## 6. 续作 — Phase 3g-loop：regime 有效性学习（已落地）

PRD §13「哪个 regime 有效」的聚合底座。**新增** `runtime/regime_effectiveness.py`：
把 postmortems 按交易所在市场的 regime 标签分桶，**复用 `model_effectiveness` 的全部
指标计算**（`_blank_acc`/`_accumulate`/`_finalize`，DRY），算每个 regime 的胜率/盈亏/
edge兑现/问题率/decay/有效性裁定。

- **标签来源（诚实代理）**：postmortem 经 `canonical_market_id` join `data/regime_states.json`
  的**当前** regime，作为「开仓时 regime」代理（短数据+少交易，未持久化逐周期 regime 历史）。
  未来升级：持久化 regime 时间序列，按 opened_at join regime-at-open，标签一换骨架不变。
- 新增表 `regime_effectiveness`（schema→`0.3.9-phase3g-loop-regime-eff`，快照重建）+ datastore
  门面 `write_regime_effectiveness` + orchestrator 周期末 regime 之后钩子 + `GET /regime-effectiveness`。
- **numpy-free**：纯读 postmortems + regime_states.json；无 regime_states（如主机无 numpy）→ 全归 unknown，诚实降级。
- `enforced=False`，学习产物，不接入交易链路。

**验证（本机可执行，numpy-free）**：✅ 端到端 compute 跑通——calm 桶 3win→effective、turbulent 桶
3loss→ineffective；无映射→unknown；无 regime_states→全 unknown。新增 `tests/test_regime_effectiveness.py` 4 单测。

## 7. 下一步（teed up）

- **regime-at-open 历史**：持久化逐周期 regime → 精确归因（替换当前 proxy）。
- **GARCH（优先级 3）→ 见 PHASE3H_GARCH.md（已落地）**。
- **Kelly/Markowitz sizing（优先级 4/5）→ 见 PHASE3I_SIZING.md（已落地，建议产物 enforced=false）**。
