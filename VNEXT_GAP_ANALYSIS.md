# VNext 落差分析 — Runtime API 化改造

> 日期：2026-06-02
> 目的：在动代码前，先把 PRD（VNext）描述的目标态 vs 仓库**实际现状**对齐，标出真实工作量、已存在的可复用资产、以及必须先决策的选型问题。
> 结论先行：**PRD 把它当成"纯文件流水线 → 从零搭 API+DB"。但仓库里 VNext 的好几块已经部分落地了**——直接照 PRD 从零搭会重复造轮子，且会和现有资产打架。

---

## 1. 一句话现状

文件流水线确实到了复杂度极限（data/ 下 ~80 个顶层 json，live / test / backtest / historical 全混在一起），但：

- **事件系统已经存在**（`event_logger.py` + `data/events/runtime_events.jsonl`，已落 9893 条结构化事件）
- **HTTP API 已经存在**（dashboard 是 Next.js，已有 9 个 `/api/*` 只读路由）
- **Web Dashboard 已经存在**（Next.js，executive 模式 / agent 拓扑 / 事件流 / 信号审查面板）
- **Paper Runtime 逻辑已经存在**（`paper_pnl.py` 有 open/close/portfolio/trades/attribution，含 close_reason、realized_pnl）

也就是说 PRD 的 Phase 4（event runtime）、Phase 5（dashboard）、Phase 2（paper 逻辑）**不是从零**。真正从零的是 **DB 层** 和 **统一的写入 API（source-of-truth）**。

---

## 2. PRD 目标 vs 现状 逐项对照

| PRD 模块 | PRD 设想 | 仓库现状 | 落差 |
|---|---|---|---|
| **Runtime API（Layer 1）** | 新建 FastAPI，REST/WebSocket | **已有 Next.js `/api/*` 9 个只读路由**，直接读 json 文件 | 已有 HTTP 层但是 **TS / 只读 / 文件后端**，非 PRD 的 Python+DB。**选型冲突点见 §4.1** |
| **Database（Layer 2）** | SQLite WAL，8 张表 | **不存在**。零 DB | 纯新建。真正的核心工作量 |
| **Event Runtime** | 新增 runtime_events，统一事件 | **已存在** `event_logger.write_event()`，已落 9893 条 | ~50% 已完成。缺的是事件类型补齐 + 落库（见 §3） |
| **Agent Runner（Layer 3）** | Agent 调 API 不写 json | 现状 agent 全部读写 json 文件 | 未动。Phase 3 工作量 |
| **Paper Runtime** | `/paper/open` `/paper/close` API 化 | `paper_pnl.py` 逻辑齐全，但是函数调用 + 文件落盘，无 API | 逻辑可复用，只需 API 包壳 |
| **Dashboard（Web）** | Runtime 状态/持仓/决策流/PnL/复盘 | **已有 Next.js dashboard**，含事件流、信号审查、KPI | 大部分已有；缺"复盘"视图（因为 postmortem 还没数据） |
| **Dashboard（Mobile）** | 仓位/假设/风险/失败原因 | 无 | 纯新建 |
| **Agent B → Research** | 提 hypothesis（方向/置信/持仓时长/失败条件） | 现状直接产 signal（18 字段，无 hypothesis 概念） | 语义改造，Phase 4 |
| **Agent M → risk grading** | approve / paper_probe / reject 三级 | **现状是二元 fail-closed**：approve/REJECT（事件里全是 `risk.rejected`） | 行为改造，需重训/改 prompt + schema |
| **Agent P → 持仓退出** | 止盈/止损/时间/波动退出 + 真实 attribution | 已有止损 + 时间退出 + 生命周期 registry（5/29 修过），attribution 已真实 | 较接近目标，缺波动退出 |
| **Agent G → Postmortem Engine** | 每笔强制复盘，结构化字段 | 现状是启发式 learning bridge，写 learning_report/KB，**非逐笔、无 hypothesis 关联** | 重写为 postmortem engine，Phase 4 |

---

## 3. 确认的真实问题（PRD 抱怨的，哪些是真的）

PRD §2.1 列的问题，逐条核实：

- ✅ **schema 漂移（真）**：典型例子——`paper_portfolio.json` 2129 条记录 `status` 字段**全是 None**；持仓的 open/closed 状态其实活在**另一个文件** `positions_closed_registry.json`（5/29 的修复）。这正是 PRD 说的"无统一状态层"。
- ✅ **历史/当前混杂（真）**：data/ 顶层 ~80 个 json，`test_*` / `backtest_*` / `historical_*` / `train_*` 与 live 的 `signals.json` / `positions.json` 平铺在一起，attribution 时很难一眼区分。
- ✅ **文件无限增长（真，PRD 没提但更紧迫）**：`runtime_events.jsonl` 7.2MB、`learning_history.json` 4.2MB、`paper_portfolio.json` 1.5MB（2129 条）、`paper_trades.jsonl` 1MB。无归档/保留策略，迟早拖慢读取。
- ⚠️ **并发写入风险（部分真）**：存在 `orchestrator.lock` 单写锁，但仓库里有 **3 个 orchestrator + 4 个 executor（MD5 各不同）**。SQLite WAL 只解决单写者下的读并发；**只要多 orchestrator 还在，换 DB 也不自动解决并发**——必须先收敛到单写者。
- ✅ **无标准 API / 手机端无法接入（真）**：现有 Next.js API 只读且耦合文件路径。
- ✅ **agent 强耦合（真）**：agent 之间靠固定文件名 + 固定 schema 约定通信。

---

## 4. 必须先决策的选型问题（动代码前要拍板）

这些是 PRD 没写死、但会决定整个改造形态的岔路口：

### 4.1 API 技术栈：FastAPI（PRD）还是扩展现有 Next.js API？【最关键】

现状已有一套 **Next.js TS API（只读、读文件）+ 消费它的 dashboard**。PRD 要的是 **Python FastAPI + DB**。三种走法：

- **A. FastAPI 作为唯一 source-of-truth API（含写），Next.js 退化为纯前端 / 反代到 FastAPI。** 最符合 PRD，但要重写现有 9 个路由的数据来源。
- **B. 保留 Next.js 做读，FastAPI 只做写 + DB。** 两套 HTTP 层并存，短期快但长期又是两套协议（与"统一状态层"目标矛盾）。
- **C. 不上 FastAPI，直接在 Next.js 里接 SQLite（better-sqlite3）做读写。** 单一栈，但放弃了 Python 侧（agent 都是 Python）直连 DB 的便利，agent 要走 HTTP 才能写。

> 倾向 A，但取决于你希望 agent 写库走"直连 DB"还是"走 HTTP API"。这点你定。

### 4.2 DB 访问层：裸 sqlite3 vs SQLModel/SQLAlchemy + Alembic 迁移

核心痛点就是 schema 漂移。**裸 sqlite3** 省事但没迁移管理；**SQLModel + Alembic** 让表结构有版本、有迁移脚本，正面解决漂移。代价是依赖和样板。鉴于"治漂移"是本次主目标，我倾向带迁移工具。

### 4.3 Phase 1 双写策略：json 与 DB 谁是 source of truth

PRD Phase 1 说"当前 json 仍保留"。但如果 json 和 DB 同时被写又互不为准，等于**制造新的漂移**。建议明确：Phase 1 让 DB 做**影子写（shadow write）只读校验**，json 仍为准；Phase 2 再把 paper 写路径切到 DB 为准。需要你确认这个推进顺序。

### 4.4 事件存储：jsonl 继续 append + 入库，还是直接切 DB

已有 9893 条 jsonl 事件。建议保留 `event_logger` 的 append（crash-safe），新增一个 ingest 把 jsonl 灌进 `runtime_events` 表，双轨一段时间。需要你认可这个迁移姿势。

### 4.5 运行位置：Docker `/opt/data` vs 主机路径

代码里大量 hardcode `/opt/data/...`（CLAUDE.md 列为 #1 待修）。**sqlite 文件落哪、FastAPI 进程在容器内还是主机、launchd dry-run loop 怎么连 DB**，必须先定，否则 API 起来连不上库。

### 4.6 并发前提：单写者收敛

换 DB 不自动解决多 orchestrator 并发。Phase 1 前/中必须把入口收敛到单写者（或给写 API 加全局锁），否则 WAL 也救不了。

---

## 5. 对 PhasePlan 的修正建议

基于"已有资产"，PRD 的 Phase 顺序可微调：

- **Phase 0（PRD 没有，建议新增）**：选型拍板（§4）+ 单写者收敛 + 路径治理。不写业务代码。
- **Phase 1**：建 DB（含迁移）+ FastAPI 壳 + `GET /signals /positions /trades /status`（先只读，数据从 DB 影子表来）+ 把 `event_logger` 的 jsonl ingest 进 `runtime_events`。json 仍为准。
- **Phase 2**：`POST /paper/open` `/paper/close`，把 `paper_pnl.py` 逻辑包成 API，paper 写路径切 DB 为准。
- **Phase 3**：Agent B/M/P/G 改为调 API（M 加 risk grading 三级是这里的硬骨头）。
- **Phase 4**：hypotheses + postmortems 表 + G 重写为 postmortem engine + 事件类型补齐（paper.opened/closed、postmortem.created、agent.timeout、review.approved）。
- **Phase 5**：复盘视图（Web 已有壳）+ Mobile。

---

## 6. 待你决策清单（给后续会话）

1. §4.1 API 栈走 A / B / C？
2. §4.2 上不上 ORM + 迁移工具？
3. §4.3 Phase 1 DB 做影子写、json 为准 —— 认可吗？
4. §4.5 sqlite 文件 + FastAPI 进程落在容器内还是主机？
5. §4.6 多 orchestrator 是否先收敛到单一入口？
6. Agent M 二元 → 三级 grading 是这轮就改，还是 Phase 3 再改？
