# Phase 0 方案设计 — 写入权收敛 + SQLite 影子库接入

> 日期：2026-06-02
> 路线（已定）：保留 Next.js 只读 Dashboard API + Python 单写者 Runtime；渐进式收敛，不全量重写。
> 本文档**只设计、不动代码**。核心原则：**一个系统只能有一个写入口。**
>
> Phase 0 → Phase 1（SQLite 影子库）→ Phase 2（paper_pnl API 化）→ Phase 3（Agent B/M/P/G 逐步 API 化）

---

## 0. 一句话结论（先看这个）

**真相和直觉相反**：调度层其实**已经是单写者**——launchd 只拉起一个入口 `main.py --mode once → orchestrator.run_once()`，并且有 `fcntl` 文件锁 `orchestrator.lock` 串行化。

真正的"写入口太多"问题不在**进程并发**，而在两个层面：

1. **物理写入分散**：~13 个 live 文件由 ~8 个模块各自 `open(w)/json.dump` 直接落盘，**没有统一的数据访问层**。这才是 schema 漂移、且"以后想切 DB 无从下手"的根因。
2. **潜在入口多但未调度**：`orchestrator_advanced.py` / `orchestrator_realtime.py` / gateway `run-once` / 一堆手动脚本都能各自拉起一个写周期，目前只靠锁兜底、且只有 dry-run 心跳在排程。

所以 Phase 0 的收敛 = **① 确认并冻结唯一调度入口 + ② 建一个唯一"写入门面"(DataStore)让所有 live 写入收口**。SQLite 影子库就挂在这个门面后面，不碰 agent、不碰 dry-run。

---

## 1. 问题①：现在到底有哪些文件在写 `data/*.json`

按"活跃 live runtime 文件"列（已排除 test_/backtest_/generate_/historical_ 等离线产物）。写者经过逐个核实，**已剔除两类误报**：(a) 启发式把 `_read_json` 误判为写的 `local_gateway_control.py`；(b) `AGENT_PIPELINE.md` 标注 inactive 的 `agent_b_enhanced/optimized`、`agent_n`。

| Live 文件 | 真实写者（活跃） | 写入口数 |
|---|---|---|
| `signals.json` | `orchestrator.py`（步骤 12.5 汇总） | 1 |
| `intelligence_report.json` | `agents/agent_b.py` | 1 |
| `review_results.json` | `agents/agent_m.py` | 1 |
| `approved_signals.json` | `agents/agent_m.py` | 1 |
| `execution_results.json` | `signal_executor.py`（真实结果）+ `orchestrator.py`（仅 skipped 占位） | 2＊ |
| `sell_signals.json` | `agents/agent_p.py`（产出）+ `executors/sell_executor.py`（处理后写回/清空，L225） | 2＊ |
| `sell_execution_results.json` | `executors/sell_executor.py` | 1 |
| `positions.json` | `agents/agent_p.py` + `orchestrator.py` | 2＊ |
| `positions_closed_registry.json` | `agents/agent_p.py`（变量路径写，L214/235） | 1 |
| `paper_portfolio.json` | `paper_pnl.py`（`self.portfolio_file`，L157） | 1 |
| `paper_trades.jsonl` | `paper_pnl.py`（L167 append）+ `executors/signal_executor.py`（L47 append） | 2＊ |
| `paper_pnl_history.jsonl` | `paper_pnl.py` | 1 |
| `risk_snapshot.json` | `risk/risk_engine.py` | 1 |
| `runtime_events.jsonl` | `event_logger.py`（所有 agent 经 `write_event()` append） | 多 append（crash-safe） |
| `latest_data.json` | `collectors/okx_collector.py` / `agents/agent_a.py` | 1~2 |
| `learning_report.json` | `agents/agent_g.py` | 1 |
| `learning_knowledge_base.json` | `learning_knowledge_base.py` | 1 |
| `orchestrator_status.json` | `orchestrator.py`（`_write_status_from_log`） | 1 |
| `health_report.json` | `agents/agent_i.py` | 1 |

`＊` = 同一文件多个写者。注意：这些都在**同一个串行化周期内**先后写，不是跨进程并发，但属于"职责未归一"，是 Phase 0 要消除的。

> 数据访问方式说明：写入分两种——**字面量路径**（`open("data/x.json","w")`）和**变量路径**（`self.portfolio_file`、`get_events_file()`）。后者在静态扫描里容易被漏掉，本文已逐个核实补全。这本身就说明"没有统一访问层"。

---

## 2. 问题②：谁是写者，谁是读者

把 live 文件按"生产 → 消费"链路画出来（W=写，R=读）：

```
collectors/okx_collector, agent_a   ──W──>  latest_data.json
        └──R── agent_b, agent_e, risk_engine, orchestrator

agent_b            ──W──>  intelligence_report.json ──R──> orchestrator
orchestrator(12.5) ──W──>  signals.json             ──R──> agent_m
risk_engine        ──W──>  risk_snapshot.json       ──R──> agent_m
agent_m            ──W──>  review_results.json / approved_signals.json
        └──R── orchestrator, (realtime)
signal_executor    ──W──>  execution_results.json / paper_trades.jsonl
paper_pnl          ──W──>  paper_portfolio.json / paper_trades.jsonl / paper_pnl_history.jsonl
agent_p            ──W──>  sell_signals.json / positions.json / positions_closed_registry.json
        └──R── risk_engine(positions), sell_executor(sell_signals)
sell_executor      ──W──>  sell_execution_results.json / sell_signals.json(回写)
agent_g            ──W──>  learning_report.json
learning_kb        ──W──>  learning_knowledge_base.json
agent_i            ──W──>  health_report.json
orchestrator       ──W──>  orchestrator_status.json
所有 agent         ──W(append)──> runtime_events.jsonl   ──R──> Next.js dashboard
```

**纯读者（永不写 live 状态，可放心保持只读）**：
- `scripts/local_gateway_control.py`（Hermes/Telegram 网关，全部 `_read_json` 展示；唯一写的是 mock pm-trader 和它自己的 run-state 文件）
- 整个 `dashboard/`（Next.js 9 个 `/api/*` 路由，`readFile` 只读）
- `risk/risk_engine.py` 对 `positions.json`/`latest_data.json` 是只读，仅写自己的 `risk_snapshot.json`

---

## 3. 问题③：哪些必须收敛到单写者

判定标准：**一个文件 = 一个写入权拥有者（owner module）**。下面是必须收敛的清单及处理方式。

| 文件 | 现状 | 收敛动作 |
|---|---|---|
| `sell_signals.json` | agent_p 产出 + sell_executor 回写清空 | **拆语义**：产出归 agent_p；"已处理"状态不要回写同一文件，改为状态字段/独立 processed 标记（影子库阶段直接进 DB 的 `paper_orders.processed`）。这是最该先治的双写。 |
| `positions.json` | agent_p + orchestrator 都写 | 收敛到 **agent_p 单一拥有**；orchestrator 不再直接写持仓，只触发。 |
| `paper_trades.jsonl` | paper_pnl + signal_executor 都 append | 收敛到 **paper_pnl 单一拥有**；signal_executor 不再自己 append，改为调用 paper_pnl 接口。 |
| `execution_results.json` | signal_executor + orchestrator(skipped) | 收敛到 **signal_executor 单一拥有**；orchestrator 的 skipped 占位也通过同一写入函数产出，状态用 `status=skipped`，不要另起一套写法。 |
| 调度入口 | orchestrator.py / advanced / realtime / gateway run-once 都能拉起写周期 | **冻结为唯一入口** `main.py --mode once → orchestrator.run_once()`。advanced/realtime 标记 deprecated 或移出根目录；gateway `run-once` 必须复用同一 `run_once()` + 同一锁，不得另开写路径。 |

**收敛的统一手段（关键设计）**：引入一个 **`DataStore` 写入门面**（单一 Python 模块），把上述所有 live 写入改为经它落盘：

```
旧:  各模块  open("data/x.json","w"); json.dump(...)
新:  各模块  datastore.put_signals(...) / datastore.append_trade(...) / datastore.set_positions(...)
```

`DataStore` 内部仍写同样的 json 文件（Phase 0 不改行为），但**写入收口到一个模块**。这一步本身不引入 DB，只是把分散的 `open(w)` 收编。**有了这个门面，Phase 1 的 SQLite 影子写只需在门面内部加一行，零散落到各 agent。**

---

## 4. 问题④：哪些可以继续只读

明确**不需要收敛、保持只读**，避免过度改造：

- **Next.js dashboard 全部 `/api/*`**：只读 json/jsonl，保留。这是已定路线"Next.js 只读展示"的落点。
- **`scripts/local_gateway_control.py`**：状态/health/metrics 展示，纯读。保留。
- **`risk/risk_engine.py` 对 positions/latest_data**：只读输入，保留。
- **`runtime_events.jsonl`**：虽然多 append，但 append-only + crash-safe，**不算"多写者冲突"**，无需收敛；Phase 1 仅追加一个 ingest 把它灌进 DB 的 `runtime_events` 表，原 append 不动。
- **离线/历史文件**（`backtest_*`、`historical_*`、`train_*`、`test_*`、`distillation_*` 等 ~50 个）：与 live runtime 无关，**Phase 0 不碰**，后续单独归档/隔离（已有 `data/quarantine`、`data/historical` 目录可用）。

---

## 5. 问题⑤：SQLite 影子库怎么接，不破坏现有 dry-run

设计目标：**DB 只做影子（shadow），json 仍是唯一事实源（source of truth）。dry-run 行为零变化。**

### 5.1 接入点：只在 `DataStore` 门面里挂钩，别处不改

```
DataStore.put_signals(signals):
    _write_json("data/signals.json", signals)     # ① 原行为，仍为准
    try:
        shadow_db.upsert_signals(signals)          # ② 影子写，best-effort
    except Exception as e:
        log("[shadow] 非致命: %s" % e)              # ③ 绝不向上抛
```

三条铁律：
1. **json 先写、且写成功即算成功**；DB 写在其后。
2. **DB 写失败只记日志，绝不影响周期**（照搬 `event_logger` 已验证的 best-effort 模式）。
3. **没有任何读路径依赖 DB**（dashboard 仍读 json）。这样即使影子库整个崩了，系统行为和今天一模一样。

### 5.2 dry-run 不受影响的保证

- 影子库**不参与任何执行/审批判断**，纯旁路记录，因此 `EXECUTOR_DRY_RUN=1` 的护栏链路完全不经过 DB。
- 写入 DB 的记录**继承现有 6 桶 status**（`success/dry_run/simulated/failed/timeout/error`），`dry_run` 照样隔离；下游学习只读 json（Phase 0/1 不变）。**绝不让 dry_run 记录在 DB 里被误算成 success。**
- `paper_portfolio` 的 open/closed 状态当前分裂在 `positions_closed_registry.json`——影子库正好用一张 `paper_positions` 表把它**归一**（一个 `status` 列），这是"状态归一"的第一个实证收益，但 Phase 0 仅旁路验证，不切读。

### 5.3 落库位置与并发（呼应路径问题）

- SQLite 文件落 `data/runtime.db`（与 json 同目录，受同一备份/路径治理）。**WAL 模式**开读并发。
- 因为写入已收敛到 `DataStore` + 单一 `run_once()` 串行周期，**SQLite 单写者前提天然满足**——这正是"先收敛写入权、再上 DB"顺序的意义：反过来先上 DB 解决不了并发。
- Next.js 若要读 DB（Phase 1 之后可选），用 `better-sqlite3` 只读连接；Phase 0 阶段 dashboard 继续读 json，DB 仅供离线核对（`SELECT` 比对 json 一致性）。

### 5.4 Phase 0 的验收（不破坏的证据）

- 跑 `EXECUTOR_DRY_RUN=1` 单周期，`pytest tests/test_smoke.py` 全过（与改造前一致）。
- 同一周期产出的 `signals.json` / `paper_trades.jsonl` 与 DB 影子表**逐行可对账**（写校验脚本，不进主流程）。
- 故意让 `shadow_db` 抛异常，验证周期照常 18/18 完成、json 照常落盘。

---

## 6. Phase 0 交付物清单（不含业务代码改写）

1. 本设计文档（写者/读者矩阵 + 收敛清单 + 影子库接法）。
2. `DataStore` 门面的**接口设计**（函数签名草案：`put_signals / put_review / set_positions / append_trade / set_status …`），先定契约不实现。
3. SQLite 影子库 **schema 草案**（`signals / reviews / paper_orders / paper_positions / paper_trades / runtime_events`，与 PRD §4 表对齐）。
4. 调度入口冻结决定（确认只留 `main.py --mode once`，其余 orchestrator 标 deprecated）。
5. 影子写 best-effort + dry-run 不受影响的验收脚本设计。

> 下一步需你拍板的点：
> (a) `DataStore` 门面用"模块函数"还是"单例类"？
> (b) advanced/realtime 两个 orchestrator 直接标 deprecated，还是先移到 `legacy/` 目录留存？
> (c) 影子库 schema 是否这轮就按 PRD 8 表全建，还是先建 live 链路用到的 6 张？
