# Phase 3i — Kelly + Markowitz 仓位 sizing 建议

> Learning Runtime PRD §11 优先级 4「Markowitz：多信号组合」+ 5「Kelly：仓位 sizing/风险控制」。
> `runtime/position_sizing.py`：把前三个真实模型的产物拼成**仓位建议**。沿用既有骨架，
> **建议产物 `enforced=False`**，绝不默认接入仓位。

---

## 1. 定位

把三模型产物组合成 sizing：
- **边（expected return）** ← cointegration 研究候选（Phase 3f）的 `expected_edge`；
- **方差** ← GARCH 预测波动（Phase 3h）`forecast_vol²`；
- **regime** ← HMM（Phase 3g）`current_regime` 做风险缩放（turbulent→0.5 / normal→0.75 / calm→1.0）。

## 2. 方法（numpy-only 确定性）

- **Kelly 分数**（每信号绝对仓位占比）：`f = clamp(κ·μ/σ², 0, F_MAX) × regime_scaler`。
  分数 Kelly κ=0.25、单仓上限 F_MAX=0.25、负边归零、long-only。
- **Markowitz 权重**（多信号相对配置）：`w ∝ Σ⁻¹μ`，long-only 截断后归一（和=1；全非正边→全 0）。
  Σ 由方差对角（+ 可选相关矩阵）构成，`pinv` 兜底奇异；权重对 μ 同比缩放不变（量纲鲁棒）。

输出每条：`sized_fraction`（Kelly×regime）、`markowitz_weight`、`variance_source`(garch/default)、
`regime`、`kelly_raw`、`models_used=[...,"kelly","markowitz"]`、`rationale`。

## 3. 关键护栏

- **`enforced=False`**：写 `data/sizing_suggestions.json` + 影子表，**不接入 agent_m/executor/paper_probe 仓位**。
  当前 paper_probe 仍用固定 ×0.25；接成真正 sizing = 后续 env 门控独立步骤（Phase 5，需评审）。
- **边量纲（Phase 5 已校准）**：cointegration 候选现额外产出无量纲 `expected_return`
  （=(1−φ)·|z|·spread_std/入场价）+ `entry_price`；本模块改**收益率空间 Kelly**（μ=`expected_return`，
  价格单位 GARCH 方差经入场价归一 `(vol/price)²`），旧候选无 `entry_price` 安全退化。详见 PHASE5_ENFORCEMENT.md §9。

## 4. 改动清单（全加法）

| 文件 | 改动 |
|---|---|
| `runtime/position_sizing.py` | **新增** kelly_fraction / markowitz_weights / suggest / compute |
| `runtime/schema.sql` | 新增表 `sizing_suggestions`；schema_version → `0.3.11-phase3i-sizing` |
| `runtime/_shadow.py` | `upsert_sizing_suggestions`（快照重建）+ `query_sizing_suggestions` |
| `runtime/datastore.py` | 门面 `write_sizing_suggestions` + `__all__` |
| `orchestrator.py` | 周期末 GARCH 之后 best-effort 钩子 |
| `runtime/api.py` | `GET /sizing-suggestions` |
| `tests/test_position_sizing.py` | **新增 8 单测** |

## 5. 验证

| 判据 | 方式 | 结果 |
|---|---|---|
| schema 建 `sizing_suggestions` + 最终 0.3.11 | stdlib sqlite3 | ✅ |
| datastore→shadow upsert/query | stdlib | ✅ 1 行回填、sized_fraction/variance_source 正确 |
| 模块 + 单测语法 | `py_compile` | ✅ |
| **Kelly + Markowitz 数学**（纯 stdlib 镜像） | 合成 μ/σ²/regime | ✅ Kelly 封顶 0.25/负边归零/turbulent 缩半；Markowitz 归一/long-only/低方差更高权重/全负边→0 |
| numpy 单测（8 个，含 markowitz pinv）| **待 numpy 环境** | ⏳ 本机无法执行 |

**非破坏**：惰性导入；钩子在 broad try/except 内；只读三模型 json 产物，不碰审批/执行/仓位。

复现（需 numpy）：`PA_SHADOW_DB=1 python3 -m runtime.position_sizing`；`pytest tests/test_position_sizing.py -v`。
