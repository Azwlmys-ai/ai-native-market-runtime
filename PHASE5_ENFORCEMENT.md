# Phase 5 — 纸面强制层（Learning 产物接回交易行为）

> Learning Runtime PRD §13「learning agent：淘汰失效模型」+ §11 优先级 4/5「Kelly/Markowitz sizing」
> + Phase 5「动态模型权重 / 自动淘汰失效模型」。
> `runtime/enforcement.py`：把 Phase 3 一直停在**建议层（`enforced=False`）**的两个 learning 产物
> 第一次接进 paper 信号链路，让 PRD §5/§6 的「发现→交易→复盘→学习」闭环真正把学习结论反馈回交易行为。

---

## 1. 定位

前面 Phase 3 所有 learning 产物都刻意只产出建议、不动交易：
- `data/rule_effectiveness.json`（`rule_weights`）—— 每规则/族一个 weight 乘子 + 处置标签；
- `data/sizing_suggestions.json`（`position_sizing`）—— 每候选一个 Kelly×regime `sized_fraction`。

本层在 orchestrator **汇总 `signals.json`、写盘之前**，按学习结论调整每条信号的 `position_size`：
- **动态权重 / 淘汰失效模型** ← rule weight 乘子（失效规则降权、衰减规则重降，但不归零）；
- **sizing** ← Kelly×regime 绝对仓位建议替换固定 probe 量。

> 这是把 Phase 3 的「学习」第一次闭合回「交易行为」的一步——但严格限定在 **paper / dry-run** 内。

## 2. 方法（stdlib-only 确定性，门控关时恒等）

对每条信号按顺序施加：

1. **sizing 基准**（`PA_ENFORCE_SIZING=1`）：用 `sized_fraction` 作仓位基准。
   join：优先 `pair_id`/`signal_uid`→`sizing.signal_uid`（协整候选），回退 `market_id`→`sizing.market_id`。
2. **weight 乘子**（`PA_ENFORCE_WEIGHTS=1`）：`base × weight` 缩放。
   join：`learned_rule_match`→`rule` 精确命中，回退 `family`（复用 `model_effectiveness._rule_family`，口径一致）。
3. **clamp**：地板 `SIZING_FLOOR`（正仓位探针**绝不归零**）→ 绝对硬上限 `MAX_SIZE`。
4. **降险上限**（默认）：最终 ≤ 原始仓位；`PA_ENFORCE_ALLOW_SCALE_UP=1` 才允许放大（仍 ≤ `MAX_SIZE`）。

无命中的信号原样保留（不写 `enforcement` 证据、不进审计）。

## 3. 关键护栏（与项目 dry-run 纪律一致）

- **默认全关 → 恒等零回归**：两个 env 门控都不设时，本层一字不改信号（当前行为完全不变）。
- **只改 `position_size` 一个字段**：**不绕过 Agent M 审查、不绕过 executor dry-run**；
  `success` 计数仍只由 `EXECUTOR_DRY_RUN` 决定（real 下单与本层无关）。
- **只降险（默认）**：最终仓位 ≤ 原始 ≤ `MAX_SIZE`(0.10)。
- **绝不归零探针**：正仓位至少保留 `SIZING_FLOOR`(0.005)——PRD：继续低风险试错拿数据，
  不因学习结论把信号彻底踢出试错池（与 rule_weights「decayed 仍不自动归零」一脉相承）。
- **可解释 / 可追踪**：每条改动写信号内 `enforcement` 证据（原始/最终仓位、命中的 weight/sizing、来源）；
  整轮写 `data/enforcement_audit.json` + 影子 `enforcement_audit` 表（schema→`0.3.12-phase5-enforce`，快照重建）。
- **⚠ 仅在 `EXECUTOR_DRY_RUN=1` 受控验证下开**；主机开启前需评审。

## 4. env 门控

| 变量 | 默认 | 含义 |
|---|---|---|
| `PA_ENFORCE_SIZING` | 关 | 用 Kelly×regime `sized_fraction` 作仓位基准 |
| `PA_ENFORCE_WEIGHTS` | 关 | 用学习 rule weight 乘子缩放仓位 |
| `PA_ENFORCE_LEARNING` | 关 | 便捷开关：等价同时开上面两个 |
| `PA_SIZING_FLOOR` | 0.005 | 探针仓位地板（不归零） |
| `PA_ENFORCE_MAX_SIZE` | 0.10 | 最终仓位绝对硬上限 |
| `PA_ENFORCE_ALLOW_SCALE_UP` | 关 | 允许放大到原始仓位之上（默认只降险） |

## 5. 接线点

- `orchestrator._consolidate_signals()`：`fresh_signals` 汇总后（含协整桥）、`datastore.put_signals` 前，
  `enforcement.any_enabled()` 为真才调用 `enforce_signals()`；best-effort，异常按原始信号继续（非致命）。
- `runtime/datastore.py::write_enforcement_audit` 单写者门面（原子 JSON + best-effort 影子 upsert）。
- `GET /enforcement-audit`（仅门控开启时有数据）。

## 6. 数据流（一周期滞后，符合预期）

learning 产物在**周期末**重算（postmortem 之后），本层在**下一周期**汇总信号时读取——
即「上一轮的学习结论」作用于「这一轮的下单仓位」，学习滞后一周期，正确且可解释。

## 7. 验证

- `tests/test_enforcement.py` 17 单测：门控关=恒等、sizing 三种 join、floor 不归零、max 硬上限、
  默认只降险 / 允许放大、weight 降权 / family 回退 / keep 不放大、sizing+weight 组合、
  gates env 解析、`enforce_signals` 落审计、冷启动空产物。
- 全量回归 **237 passed**（220 旧 + 17 新），零回归。
- dry-run 端到端：合成信号 + 产物 → sizing 0.05→0.02（turbulent）/ weight 0.08→0.04（down_weight）/
  无命中 0.05 不变；schema 迁移到 `0.3.12-phase5-enforce`，`enforcement_audit` 影子表正确落 2 行。

## 8. 校准验证（`scripts/enforcement_calibration_sim.py`，2026-06-05 跑 3 轮）

离线隔离沙箱（隔离 base_dir + 隔离 DB，全程 dry-run，不碰真实 data/runtime.db）三段验证：

- **A. 真实数据基线（3 轮）**：8 条真实 signals 全被 weight 命中但全 `w=1.0`（explore），
  sizing 候选为 0（协整冷启动）→ **净仓位改动 0**，多轮稳定。冷启动如实表现，非缺陷。
- **B. sizing 校准扫描（真实 `kelly_fraction`）**：**关键发现**——当 `expected_edge ≳ 0.005`（calm/normal）
  时 Kelly 即撞 `F_MAX(0.25)` 饱和。因协整 `expected_edge` 是**价格单位相对边代理、量纲偏大**，
  `κ·μ/σ²` 几乎总顶格 → sizing 退化为「一律 F_MAX×regime_scaler」（失去 Kelly 区分度）。
- **C. live 情景端到端**：sizing 命中降险到 ≤原始 / down_weight 0.25→0.025 / 负边 sizing→floor 0.005（不归零）/
  无命中不变；影子 `enforcement_audit` 表正确落 3 行（schema 0.3.12）。机制全链路正确。

## 9. 边量纲校准（已实现，2026-06-05）

针对 B 段发现，已把 sizing 的边校准为**无量纲收益率空间**（`cointegration` SCHEMA→`0.3.13-phase5-edge-calib`、
`position_sizing` SCHEMA→`0.3.13-phase5-edge-calib`）：

- **cointegration 候选新增**：`entry_price`（代表可成交腿当前价位）+ `expected_return`
  （`=(1−φ)·|z|·spread_std / entry_price`，AR(1) 每步预期回归收益率，与 `to_pipeline_signals.expected_return`
  及 `model_effectiveness.realized_return` 同量纲）。`expected_edge`（价格单位）保留作 traceability。
- **position_sizing 改收益率空间 Kelly**：μ 用 `expected_return`，价格单位 GARCH 方差 `forecast_vol²`
  经入场价归一为 `(vol/price)²`，使 `μ/σ²` 量纲一致。旧候选无 `entry_price` 时安全退化（向后兼容）。
- **效果（校准扫描，z×vol 网格）**：饱和格 **OLD 9/9 → NEW 4/9**——高 vol（turbulent/低流动）格脱离 F_MAX，
  Kelly 恢复对 vol/φ/z 的区分度；低 vol+强边格仍撞 F_MAX（stat-arb 单步 Sharpe 本就高，分数 Kelly κ=0.25 + F_MAX 封顶
  按设计兜底，非 bug）。
- 单测 +3（`_dimensionless_edge`、收益率空间 suggest、向后兼容）；全量 **240 passed**。

## 10. 主机开闸（2026-06-05，协整候选已出货后）

闭环已能产出 6–7 条 sizing 候选 + 14 条协整 probe 信号后，Phase 5 进入**受控 dry-run 开闸**：

- `scripts/run_host_loop.sh` 默认 `PA_ENFORCE_LEARNING=1`（可 `PA_ENFORCE_LEARNING=0` 关）。
- orchestrator 汇总时施加强制并写 `enforcement_audit`；每周期末打印 `[enforce]` 摘要。
- `scripts/verify_enforcement_live.py`：开闸前只读演练，报告 `applied_count` vs `net_position_changes`。

**预期（冷启动诚实表现）**：
- 协整信号 sizing **命中率高**（`pair_id`→`sizing.signal_uid` join 已通）。
- **净仓位改动可能仍为 0**：Kelly `sized_fraction` 常大于 probe 原始仓位（0.02–0.05），
  且默认「只降险」不放大；weight 侧多数仍为 `w=1.0`(explore)。
- 随 `turbulent` regime 降 scaler、`down_weight` 规则积累、probe 平仓进 postmortem，净改动会逐渐出现——
  这是设计预期，不是 enforcement 失效。

## 11. 后续（需评审 / 授权）

- 🟡 **weight 强制安全但当前近乎惰性**：唯一 down_weight 是 `unknown`（postmortem 无规则兜底标签），
  与 live signals 的 `learned_rule_match`(mid_range_*) 不对齐 → 实际 0 改动。需积累更多带规则归因的
  paper 反馈，learning 才会产出与 live 信号对齐的 down_weight。
- **进一步去饱和（可选，需真实候选评估）**：更小 κ 或持有期一致的 σ²（按 half_life 累积方差）。
- **Phase 4 live probe**：真实小额下单 / live 风控 / 自动止损——需真金 + 显式授权，未做。
- **scale-up 默认化**：当前默认只降险；待 paper 反馈充分后再评估。
