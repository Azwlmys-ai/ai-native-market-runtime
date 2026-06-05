# Phase 3c-2 — 失败条件复盘对照（主机外沙箱验证通过）

> 日期：2026-06-04
> 对应 VNEXT 里程碑 §6 尾巴 #6：**B 的 failure_conditions 用于复盘对照**——「当初说的失败条件是否真发生」。
> 闭合 研究→试错→复盘→进化 环的最后一段：把 Agent B 假设里的预测失败条件，与 Agent G 复盘的实际结果对照裁定。

---

## 1. 背景 / 落差

- Phase 3c-1 已让每个信号派生结构化 hypothesis，含 `failure_conditions`（B prompt 原生 or 派生）。
- 但复盘引擎（Phase 3a）只 join 信号拿 hypothesis/expected_edge，**没用到 failure_conditions**——预测的失败模式从未与实际结果对照。
- 3c-2 目标：复盘时取该信号的 hypothesis，对每条预测失败条件判定「是否发生」，给出整体裁定。

---

## 2. 做了什么

### 判定逻辑（确定性，沙箱可验）—— `runtime/postmortem.py`

- `_parse_conditions(fc)`：把 failure_conditions（JSON 数组串 / 「；」拼接串 / list / None）解析成逐条。
- `_classify_condition(cond)`：按关键词归类 liquidity / timing / model / event（event=方向性/事件触发，如「若 X 队夺冠」）。
- `_review_failure_conditions(conditions, outcome, liq, tim, mod)`：逐条判定 occurred + 整体 verdict。
  - **win** → 假设成立，预测失败均未发生（occurred=False）→ verdict `confirmed`。
  - **loss** → 至少一条兑现；逐条对照复盘问题标志：类别命中对应 issue 标志（liquidity/timing/model）→ occurred=True；event 类亏损即视为兑现；其余无法对应 → occurred=None。materialized>0 → `refuted`；否则 `loss_unexplained`（亏损但与预测失败条件不符 = 模型遗漏真实失败模式，高价值信号）。
  - **flat** → `inconclusive`。无预测条件 → `no_prediction`。
- `build_postmortem(..., hypothesis=...)`：新增 hypothesis 入参，产出 `failure_conditions_review`（predicted/items/materialized_count/verdict）+ 标量 `hypothesis_verdict` + `hypothesis_uid`/`hypothesis_source`。
- `generate()`：逐笔已平仓 → 经 `signal_uid` 取 hypothesis（`_shadow.hypothesis_for_signal`）→ 对照。

闭环连接键：`hypotheses(signal_uid) → signals(signal_uid) → postmortems`。signal_uid 三处用同一 `_ds.uid(market_id, direction, generated_at, source)` 计算，天然对齐。

### 影子库 —— `runtime/_shadow.py` / `schema.sql`

- postmortems 表加 `hypothesis_verdict TEXT`（schema.sql 新建版 + `_EXPECTED_COLUMNS["postmortems"]` 旧库 ALTER 自迁移）。
- 新增 `hypothesis_for_signal(signal_uid)` 查询。
- `upsert_postmortem` 写新列（含 ON CONFLICT 更新）。
- schema_version → `0.3.3-phase3c2`。

### 重建健壮性 —— `runtime/ingest.py`

- **关键修复**：ingest 此前不回填 hypotheses。文档建议「schema 升级后删库重建」，重建后 hypotheses 表会空 → 对照退化成全 `no_prediction`。本轮加 `hypotheses.jsonl` 回填（**不回填 postmortems**，让复盘引擎在重建后重跑，使存量已平仓持仓也带上 verdict）。

### Dashboard 露出 —— `/api/postmortems` + `/research`

- 路由 Postmortem 接口加 `hypothesis_verdict` + `failure_conditions_review`；summary 加 `verdicts` 计数。
- `/research` 复盘卡片加「失败条件对照」徽章（假设成立/证伪/亏损·预测外/无定论）+ 逐条「●发生 / ○未发生 / ◌未知」。

---

## 3. 验证（全过）

- **单元真值表**（确定性纯函数）：win→confirmed、loss+timing 命中→refuted、loss+event→refuted、loss+model 类未命中标志→loss_unexplained、flat→inconclusive、无条件→no_prediction，全部断言通过。
- **真实数据端到端**（非破坏性，`PA_BASE_DIR=$PWD` 只读真实 json + `PA_DB_PATH=/tmp` 临时库）：
  - ingest 回填 9 条 hypotheses；schema 0.3.3、新列就位。
  - `postmortem.generate` 产 14 笔，verdict 分布 `{refuted:1, inconclusive:1, no_prediction:12}`。
  - 命中样例真实可读：耶稣再临(loss)→`refuted`，事件条件「若耶稣再临超自然事件」occurred=True；比特币$1m(flat)→`inconclusive`。
  - 仅 2 笔非 no_prediction，因多数已平仓持仓仍是 slug 形态临时键（对不上数字 signal id）——属尾巴 #3「临时键 reconcile」，**非 3c-2 缺陷**；reconcile 后覆盖自动扩大。
- **旧库 ALTER 迁移**：0.3.2 旧库连接即 `_migrate`，新列补上、版本 bump、14 条旧数据无损。
- **smoke 71 passed**；`py_compile` 三模块通过；**dashboard tsc `--noEmit` 0 错误**。
- 真实 `data/runtime.db` 已自迁移到 0.3.3（安全 ALTER，22 持仓 / 14 复盘无损）。

---

## 4. 主机收尾步骤（让存量复盘带上 verdict）

3c-2 逻辑已生效；要让**存量已平仓持仓**也带上 verdict，需重建影子库（runtime.db 是可重建旁路）：

```bash
cd /Users/libo/.hermes/polymarket_arbitrage
rm -f data/runtime.db data/runtime.db-wal data/runtime.db-shm
PA_BASE_DIR="$PWD" PA_SHADOW_DB=1 venv/bin/python3 -m runtime.ingest      # 回填含 hypotheses
PA_BASE_DIR="$PWD" PA_SHADOW_DB=1 venv/bin/python3 -m runtime.postmortem  # 重生带 verdict 的复盘
# dashboard: cd dashboard && npm run dev → /research 看复盘卡片的「失败条件对照」
```

> 沙箱因 `rm` 无 unlink 权限未原地重建真库；主机有权限，一行重建即可。日常 orchestrator 周期末也会 best-effort ingest+复盘，新平仓自动带 verdict。

---

## 5. 局限 / 后续

- 占位覆盖受限于临时键 reconcile（尾巴 #3）：slug 形态老仓 join 不到数字 signal → no_prediction。reconcile 后自然扩大。
- occurred 判定是确定性启发式（类别×issue 标志）；event 类在亏损下一律视为兑现，偏粗。后续可在 `use_llm` 路径加 LLM 逐条判定「该条件是否真的发生」。
- `loss_unexplained`（亏损但预测外）是最有价值的学习信号——后续可单独喂学习模块「模型遗漏的失败模式」。
