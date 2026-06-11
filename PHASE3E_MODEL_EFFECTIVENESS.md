# Phase 3e — 模型/规则有效性聚合器（Learning Runtime 第一块）

> 目标（对应新 PRD 第十三节「learning agent 新职责」）：让系统能确定性地回答
> **「哪个模型/规则有效、哪个已失效（decayed）」**。本阶段交付其中的
> **模型有效性聚合底座**，是 Learning Runtime 闭环（发现→hypothesis→paper_probe→结果→复盘→**学习模型有效性**）的「学习」环节第一块。

---

## 1. 为什么先做这个（背景核实）

落地前核实了现状，确认直接做「学习器」会架空：

- 信号**没有** PRD §8 的结构化 `models_used`/`source_markets`/`evidence` 字段；
  量化模型（协整/HMM/GARCH/Markowitz/Kelly/Copula）**代码里基本未实现**，
  当前信号来自 `agent_b` 的规则匹配（`learned_rule_match`，如 `mid_range_GTA_VI`）。
- 因此当前真实可用的「模型/策略标签」= 信号上的 `learned_rule_match` + `source`(agent)。
- postmortems 不带这些标签，但带 `signal_uid`，可 join 回 signals 影子表取标签。

结论：本阶段用**当前真实可用的归因**（learned_rule_match/source）搭好聚合骨架。
未来接入真正的 `models_used` 后，只需把标签来源从 learned_rule_match 换/并成 models_used，
**聚合骨架不变**。

---

## 2. 交付物

| 文件 | 改动 |
|---|---|
| `runtime/model_effectiveness.py` | **新增**。确定性聚合器：postmortems × 模型标签 → 有效性快照。 |
| `runtime/schema.sql` | **新增表** `model_effectiveness`；schema_version → `0.3.4-phase3e`。 |
| `runtime/_shadow.py` | 加 `upsert_model_effectiveness`（快照语义：整表重建）+ `query_model_effectiveness`。 |
| `runtime/datastore.py` | 加门面 `write_model_effectiveness`（json 事实源 + 影子 best-effort）。 |
| `orchestrator.py` | 周期末复盘之后加 best-effort 钩子（`PA_SHADOW_DB=1` 时），重算有效性。 |
| `runtime/api.py` | 加 `GET /model-effectiveness?scope=rule|family|agent`。 |
| `tests/test_model_effectiveness.py` | **新增** 8 个单测（纯聚合逻辑，不触 DB/网络）。 |

---

## 3. 聚合设计

### 输入
- 优先：影子库 `postmortems LEFT JOIN signals ON signal_uid` → 取 `learned_rule_match`/`source`。
- 回退：`PA_SHADOW_DB` 未开时读 `data/postmortems.jsonl`（降级，无 rule，标签退化为 hypothesis_source + 市场名解析）。

### 三个聚合尺度
- `by_rule` —— 完整 `learned_rule_match`（最细，「这条规则有效吗」）。
- `by_family` —— 规则族，去掉尾部大写市场类型 token（`mid_range_GTA_VI` → `mid_range`，「这类策略有效吗」）。
- `by_agent` —— 产生信号的 agent（「哪个研究 agent 的信号有效」）。

### 每个标签产出
胜率、总/均实现盈亏、均预期边、edge 兑现率（均实现盈亏/均预期边）、置信均值、
流动性/时机/模型问题率、`hypothesis_verdict` 分布、decay 信号、有效性裁定。

### 有效性裁定（确定性硬规则，可解释）
```
n < 3                                 -> insufficient   （样本不足，不下结论）
有样本但全 flat（无胜负）              -> inconclusive
近窗胜率较早窗下滑 ≥ 0.20（n≥6）       -> decayed        （边可能已失效）
胜率 ≥ 0.55 且 总盈亏 > 0             -> effective
胜率 ≤ 0.35 或 总盈亏 < 0             -> ineffective
其余                                  -> marginal
```
decay 检测：按 `closed_at` 排序已决出胜负的交易，比较近半窗 vs 早半窗胜率。

---

## 4. 纪律对齐

- **纯确定性**：无 LLM、无随机，沙箱可复现（同 postmortem/hypothesis）。
- **加法产物**：不改审批/执行/学习任何行为；只新增分析产物。
- **不污染学习样本**：只读 postmortems（来自真实已平仓 paper 持仓复盘），天然不碰 `dry_run` 执行结果。
- **单写者**：写经 datastore 门面；影子写 best-effort，失败只记日志不抛。
- **快照语义**：`upsert_model_effectiveness` 整表 DELETE+INSERT，避免标签修正前的 stale key 残留。
- **JSON 仍是事实源**：`data/model_effectiveness.json`；影子表纯旁路，可删 `runtime.db` 重建。

---

## 5. 验证记录（2026-06-05，Linux 沙箱 = 主机同一挂载）

- 单测：`pytest tests/test_model_effectiveness.py` → **8 passed**（标签派生/有效性裁定/decay/family聚合/jsonl降级落盘）。
- 回归：`pytest tests/test_smoke.py` → **71 passed**（与基线一致）；合计 **79 passed**。
- 真实数据 standalone（`PA_SHADOW_DB=1 python3 -m runtime.model_effectiveness`）：
  - 读到 12 笔真实 postmortems，`attribution_source=shadow_join_signals`。
  - 落盘 `data/model_effectiveness.json` + 影子表 8 行（rule/family/agent 三尺度）。
  - schema_version 自迁移到 `0.3.4-phase3e`，新表自动建立，旧表未动。
- **修复的一个真实 bug**：signals 影子表里 `learned_rule_match` 经 `_j()` 存成 JSON 文本
  （`"mid_range_GTA_VI"` 带引号），聚合读回需 `_unwrap()` 去引号，否则 family 切成 `"mid_range`。已修 + 覆盖。

### 当前数据观察（非缺陷，记录备查）
现有 12 笔 postmortems 多为 `flat`(entry=exit) 或 `-1.0` 小额（含 `Test Market` 等调试/合成痕迹），
且多数 `signal_uid` 在 signals 影子表无对应行 → 标签降级为 `unknown`。
聚合如实给出 `insufficient`/`ineffective`，**符合预期**——本阶段交付的是机制；
待 paper_probe 放量产生真实复盘后，标签与裁定才有统计意义。

---

## 5b. Phase 3e-2 — 规则权重建议（淘汰失效模型雏形，2026-06-05 续）

把有效性快照转成**可执行的处置建议**，但**刻意只建议、不强制**（对齐当前 PRD「大量低风险试错」方向）。

| 文件 | 改动 |
|---|---|
| `runtime/rule_weights.py` | **新增**。读 `model_effectiveness.json` → 每条规则/族给 weight 乘子 + 处置标签 + 理由。 |
| `runtime/schema.sql` | **新增表** `rule_weights`；schema_version → `0.3.5-phase3e-weights`。 |
| `runtime/_shadow.py` | `upsert_rule_weights`（快照语义整表重建）+ `query_rule_weights`。 |
| `runtime/datastore.py` | 门面 `write_rule_weights`（写 `data/rule_effectiveness.json` 建议产物 + 影子）。 |
| `orchestrator.py` | 周期末 model_effectiveness **之后**调 `rule_weights.compute()`（best-effort）。 |
| `runtime/api.py` | `GET /rule-weights?scope=rule|family`。 |
| `tests/test_rule_weights.py` | **新增 4 单测**。 |

### 确定性策略（保守，可解释）
```
effectiveness   weight   recommendation      语义
effective       1.10     keep                略加权，鼓励复用
marginal        1.00     keep
inconclusive    1.00     keep                全 flat 无信息
insufficient    1.00     explore             样本<阈值，继续试错，绝不淘汰
ineffective     0.50     down_weight         降权但不归零
decayed         0.25     retire_candidate    提示人工/Phase5 复核，仍不自动归零
```

### 关键纪律
- **`enforced=false`**：本产物**未接入 live 交易链路**，agent_b 信号生成/过滤行为零变化。
- 真正 enforcement（按 weight 压仓/跳过）= 后续 **env 门控的独立步骤**，需单独评审。
- 保守探索：`insufficient` 永不淘汰、`decayed` 也只到 0.25 不归零，避免过早收紧扼杀反馈采集。

### 验证（2026-06-05 沙箱）
- 单测：`pytest tests/test_rule_weights.py` → **4 passed**；合计 **83 passed**（71 smoke + 8 + 4）。
- 真实数据 standalone：`PA_SHADOW_DB=1 python3 -m runtime.rule_weights` → `data/rule_effectiveness.json` + 影子 `rule_weights` 6 行；`ineffective`→down_weight 0.5、`insufficient`→explore 1.0，`enforced=false`，schema→0.3.5。

---

## 6. 下一步候选

- **weight enforcement（Phase 5）**：env 门控（如 `PA_RULE_WEIGHTS=1`，默认关）让 agent_b 按 `rule_effectiveness.json` 的 weight 压仓/跳过 `retire_candidate`。需单独评审 + 受控验证，**不在本阶段**。
- **接真正的 models_used**：实现 PRD 第一优先级模型（协整/spread 或 Kelly）写入信号生成链路，
  让标签来源升级为真实模型；聚合骨架已就绪，无需重写。
- **关联强度学习**（PRD §13 第二/三项）：market correlation / regime 有效性，复用本表模式另起 `correlation_effectiveness`。
- **dashboard**：`/research` 加「模型有效性 + 规则权重建议」卡片（读 `GET /model-effectiveness`、`GET /rule-weights`）。

> ✅ 已完成（本轮）：learning 侧消费 model_effectiveness → 规则权重**建议**产物（3e-2，advisory-only）。
