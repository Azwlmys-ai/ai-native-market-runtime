# Phase 0 接口契约 + Schema 草案

> 日期：2026-06-02
> 拍板决策：(a) DataStore 用**模块函数**；(b) advanced/realtime orchestrator **仅标 deprecated 不移动**；(c) 影子库**先建 live 链路 6 表**（signals/reviews/paper_orders/paper_positions/paper_trades/runtime_events），暂不建 hypotheses/postmortems。
>
> 本轮交付的是**草案**：可直接 review、可端到端跑通，但**尚未接入任何 agent/executor**。接入是 Phase 0 的下一步动作。

---

## 1. 新增文件

```
runtime/
├── __init__.py
├── schema.sql        # 6 表 DDL 草案（WAL，含 raw_json 存档 + *_uid 幂等键）
├── datastore.py      # 唯一写入门面（模块函数）；json 实写 + shadow guarded
└── _shadow.py        # SQLite 影子写实现；默认关闭，PA_SHADOW_DB=1 才生效
```

设计不变量（三条铁律，已在代码里落实）：

1. **json 先写、写成功即算成功**；shadow 写在其后。
2. **shadow 失败只记日志、绝不向上抛**（`_shadow_call` 统一 best-effort 包装）。
3. **没有读路径依赖 DB**；shadow 默认关闭，开/关行为对 json 与 dry-run 完全无影响。

---

## 2. 文件 → 门面函数 → 表 映射

| live 文件 | owner 函数（datastore） | 影子表 | 备注 |
|---|---|---|---|
| `signals.json` | `put_signals(cycle_id, signals)` | signals | 整体替换 |
| `review_results.json` + `approved_signals.json` | `put_review(cycle_id, review_result)` | reviews | 聚合对象落 json，逐条决策落表 |
| `execution_results.json` | `record_executions(cycle_id, results, side="BUY")` | paper_orders | |
| `sell_execution_results.json` | `record_executions(cycle_id, results, side="SELL")` | paper_orders | |
| `sell_signals.json` | `put_sell_signals(cycle_id, sell_signals)` | paper_orders(SELL) | 产出归 agent_p 单写 |
| （卖出已处理标记） | `mark_orders_processed(order_uids)` | paper_orders.processed=1 | **替代旧的回写清空 sell_signals** |
| `positions.json` | `set_positions(positions)` | paper_positions(open) | |
| `positions_closed_registry.json` | `upsert_closed_positions(records)` | paper_positions(closed) | |
| `paper_portfolio.json` | `save_portfolio(positions)` | paper_positions | |
| `paper_trades.jsonl` | `append_paper_trade(trade)` | paper_trades | append-only |
| `orchestrator_status.json` | `write_status(payload)` | —（无表） | |
| `runtime_events.jsonl` | `emit_event(...)` | runtime_events | 委托现有 event_logger，append 不变 |

---

## 3. Schema 要点（详见 `runtime/schema.sql`）

- **每表 `raw_json` 存档**：原始记录整体留底，schema 漂移也不丢字段。
- **`*_uid` 幂等键 + UPSERT**：同一周期重跑不产生重复行（已验证 `put_signals` 调两次 rows=1）。
- **`paper_positions` 是状态归一表**：把分裂的 `paper_portfolio.json`(open) + `positions_closed_registry.json`(closed) 合成一张表的单一 `status` 列，**根治 `status=None` 漂移**。
- **生命周期护栏**（验证时发现并已修）：`paper_positions` 的 UPSERT 用 `CASE`/`COALESCE` 保证 **closed 不会被后续 open 刷新覆盖回去**、平仓字段（exit_price/realized_pnl/close_reason）不被清空——对齐 5/29 那次 registry 修复的教训。
- **`reviews.lane`**：承接现有 `approved_paper/approved_real/...` 的 paper/real 分流，并为 PRD 未来 risk grading（`PAPER_PROBE`）预留 `decision` 取值。
- **status 沿用 6 桶**：`success/dry_run/simulated/failed/timeout/error`，dry_run 永不与 success 混算。
- **schema 版本**：`schema_meta.schema_version = 0.1.0-phase0`；本轮不引入 Alembic，手工迁移 + 元表足够。

---

## 4. 验证结论（已跑通）

用临时 base dir（不污染真实 `data/`）验证：

- **shadow OFF**：只写 `signals.json`，**不生成 `runtime.db`** → 零行为变化，可作为纯重构安全采用。
- **shadow ON**：6 表正确落库；`put_signals` 幂等（两次 → 1 行）；`emit_event` 落 runtime_events。
- **生命周期护栏**：`open → closed → open刷新` 序列后，持仓仍为 `closed` 且 `realized_pnl=-4.2` 保留。✅

---

## 5. orchestrator deprecated 注释样板（决策 b：仅标注不移动）

在 `orchestrator_advanced.py` 与 `orchestrator_realtime.py` 文件**头部**加（不动逻辑、不动 import 路径，避免断 cron/dashboard 引用）：

```python
# ============================================================================
# ⚠️ DEPRECATED（2026-06-02）— 非唯一调度入口，请勿用于新接入
# ----------------------------------------------------------------------------
# 唯一活跃调度入口：launchd → scripts/scheduled_orchestrator_dryrun.sh
#                  → main.py --mode once → orchestrator.py:Orchestrator().run_once()
# 本文件保留仅为历史/手动调试用途。Phase 0 写入收敛后，新的写入一律走
# runtime.datastore 门面；本文件不接入 DataStore，也不应被排程拉起。
# 详见 PHASE0_WRITE_CONVERGENCE.md / PHASE0_CONTRACTS.md
# ============================================================================
```

> 不加 `warnings.warn` / `sys.exit`，纯注释，确保零运行时副作用。

---

## 6. 采用步骤（Phase 0 下一步，按风险从低到高）

1. **先把唯一入口 `orchestrator.py` + `signal_executor.py` + `agent_m.py` + `agent_p.py` + `paper_pnl.py` 的 live 写入逐个改调 `datastore.*`**（shadow 保持 OFF）→ 跑 `pytest tests/test_smoke.py` + 一轮 `EXECUTOR_DRY_RUN=1` 单周期，确认 json 产物逐字节/逐行不变。这一步是纯重构。
2. 给两个 deprecated orchestrator 加头注释（§5）。
3. **再打开 `PA_SHADOW_DB=1`**，跑单周期，写对账脚本比对 `signals.json` ↔ `signals` 表、`paper_trades.jsonl` ↔ `paper_trades` 表逐条一致。
4. 故意让 `_shadow` 抛异常，验证周期照常 18/18、json 照常落盘（best-effort 不阻断）。

---

## 7. 待你拍板 / 确认

- §6 步骤 1 的**收敛顺序**是否认可（先核心 5 文件，after 再扩 sell_executor/agent_g 等）？
- `reviews` 是否这轮就拆逐条决策入库（当前草案已拆），还是先整体存 raw_json、Phase 3 再拆？
- 影子库文件名 `data/runtime.db` 是否 OK（与 json 同目录，受同一备份/路径治理）？
