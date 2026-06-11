# Phase 3h — GARCH(1,1) 波动率聚集研究模型

> Learning Runtime PRD §11 优先级 3「GARCH」。继协整（3f）、HMM regime（3g）之后的
> **第三个真实统计模型**：`runtime/garch.py`。沿用既有「研究工具 + `enforced=False` +
> 影子表 + orchestrator 周期末钩子 + 单测」骨架，全加法、非破坏。

---

## 1. 定位（PRD 对齐）

- PRD §11 优先级 3：**GARCH** 用于波动率聚集 / 风险状态变化。
- 与 HMM regime（3g）互补：**regime 给离散状态**（calm/turbulent），**GARCH 给连续波动幅度预测**。
- 喂 Kelly/Markowitz sizing（Phase 3i）：用 `forecast_vol²` 做仓位风险标定。
- PRD §10：研究工具，`enforced=False`，不接入 live executor / agent_b。

## 2. 方法（方差目标化 GARCH(1,1) + 网格 MLE，numpy-only）

观测 = 去均值一阶差分收益 `r[t] = (p[t]−p[t−1]) − mean`。
条件方差递归：`sigma2[t] = omega + alpha·r[t−1]² + beta·sigma2[t−1]`。

**方差目标化**：长期方差 = 样本方差 V → `omega = V·(1−alpha−beta)`，把 3 参降为 (alpha,beta)
二维。在平稳约束 `alpha+beta ≤ 0.985` 的网格上最大化高斯对数似然 → **确定性 argmax**
（无随机、无迭代优化器，短序列稳健，避开 arch/scipy）。

输出（每序列）：`alpha/beta/omega/persistence`、`long_run_vol`、`current_vol`、
`forecast_vol`（1 步预测）、`vol_ratio=forecast/long_run`、`risk_state`（elevated/normal/calm）、
`vol_trend`（rising/falling/stable）、`clustering`（persistence≥0.5 且 alpha>0）、
`vol_spike`（末点 |r| ≥ 长期波动·2）；`models_used=["garch"]` + evidence + failure_conditions（PRD §8）。

## 3. 防伪护栏

序列在动（std>eps）+ 不同取值数≥4 + 观测数≥10；alpha+beta≈0 视为无 ARCH 效应；每条打 data_sufficiency。

## 4. 改动清单（全加法）

| 文件 | 改动 |
|---|---|
| `runtime/garch.py` | **新增** GARCH(1,1) 引擎（fit_garch 网格 MLE / analyze_series / compute）|
| `runtime/schema.sql` | 新增表 `volatility_states`；schema_version → `0.3.10-phase3h-garch` |
| `runtime/_shadow.py` | `upsert_volatility_states`（快照重建）+ `query_volatility_states(risk_state=...)` |
| `runtime/datastore.py` | 门面 `write_volatility_states` + `__all__` |
| `orchestrator.py` | 周期末 regime 有效性之后 best-effort 钩子 |
| `runtime/api.py` | `GET /volatility-states?risk_state=elevated\|normal\|calm` |
| `tests/test_garch.py` | **新增 7 单测** |

新表 `CREATE TABLE IF NOT EXISTS` 自动建，无需登记 `_EXPECTED_COLUMNS`。

## 5. 验证

本机无 numpy + PyPI 不可达（与 CLAUDE.md 注记一致），分层验证：

| 判据 | 方式 | 结果 |
|---|---|---|
| schema 建 `volatility_states` + bump 0.3.10/最终 0.3.11 | stdlib sqlite3 | ✅ |
| datastore→shadow upsert/query + risk_state 过滤 | stdlib | ✅ 1 行回填、elevated 命中、calm 空 |
| 模块 + 单测语法 | `py_compile` | ✅ |
| **GARCH 拟合正确性**（同方程纯 stdlib 镜像） | 合成真实 GARCH 序列（α=.15,β=.8） | ✅ 网格 MLE 恢复高 persistence、clustering=True、forecast vs long_run 合理 |
| numpy 单测 `tests/test_garch.py`（7 个）| **待 numpy 环境** | ⏳ 本机无法执行 |

**非破坏**：惰性导入（orchestrator try-块 + 单测）；钩子在 broad try/except 内，numpy 缺失被吞；只读价格历史。

复现（需 numpy）：`PA_SHADOW_DB=1 python3 -m runtime.garch`；`pytest tests/test_garch.py -v`。
