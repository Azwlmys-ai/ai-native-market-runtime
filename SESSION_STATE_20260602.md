# SESSION_STATE — 2026-06-02

> 主题：VNext Runtime API 化改造启动 —— 路线定调 + Phase 0 写入收敛设计 + Phase 1 影子库落地。
> 接续：SESSION_STATE_20260529.md（系统功能性缺口已清零，dry-run 稳定）。
>
> ✅ **Phase 1 Shadow DB：主机验证通过（2026-06-02）** —— ingest 可刷新、shadow dry-run 周期钩子生效、`pytest tests/test_smoke.py` **71 passed**、JSON 仍为事实源。launchd 仍停止（未恢复）。

---

## 本次定调（用户已拍板）

路线从 PRD 的「全量 API 重构」改为 **渐进式 Runtime 收敛**：

- 保留 **Next.js 只读 Dashboard API**（已存在 9 个 `/api/*`，不废）
- Python 负责 **单写者 Runtime**：Agent / paper / DB 写入
- Next.js 只读展示，避免前端与 Agent 同时写库
- 顺序：**Phase 0 收敛写入权 → Phase 1 SQLite 影子库 → Phase 2 paper_pnl API 化 → Phase 3 Agent B/M/P/G 逐步 API 化**
- 选型：DataStore=**模块函数**；advanced/realtime orchestrator **仅标 deprecated 不移动**；影子库**先建 6 表**（signals/reviews/paper_orders/paper_positions/paper_trades/runtime_events），hypotheses/postmortems 留 Phase 3。

---

## 关键审查结论（落差分析）

PRD 把项目当成「纯文件流水线 → 从零搭 API+DB」，但实测 **VNext 多块已部分落地**：

- 事件系统已存在：`event_logger.py` + `data/events/runtime_events.jsonl`（9893 条结构化事件）
- HTTP API 已存在：Next.js dashboard 9 个 `/api/*` 只读路由
- Web Dashboard 已存在；Paper 逻辑（`paper_pnl.py` open/close/attribution）已齐

**真正从零的只有 DB 层 + 统一写入门面。** 详见 `VNEXT_GAP_ANALYSIS.md`。

写者/读者实测要点（详见 `PHASE0_WRITE_CONVERGENCE.md`）：
- 调度层其实**已是单写者**：launchd 只拉 `main.py --mode once → orchestrator.run_once()`，有 `fcntl` 锁串行化
- 真问题是**物理写入分散**（~13 个 live 文件 ~8 个模块各自 `open(w)`）+ **潜在入口多但未排程**（advanced/realtime/gateway run-once）
- 4 个必须收敛的双写文件：`sell_signals.json` / `positions.json` / `paper_trades.jsonl` / `execution_results.json`
- 纠正了两个静态扫描误报：`local_gateway_control.py` 实为只读；`agent_b_enhanced/optimized`、`agent_n` 是 inactive 变体

---

## 本次落地的代码（新增 runtime/ 包）

| 文件 | 作用 | 状态 |
|---|---|---|
| `runtime/schema.sql` | 6 表 DDL（WAL，raw_json 存档 + *_uid 幂等键） | ✅ 已验证 |
| `runtime/datastore.py` | 唯一写入门面（模块函数）；json 实写 + shadow guarded | ✅ 编译/单测通过 |
| `runtime/_shadow.py` | SQLite 影子写实现；默认关，`PA_SHADOW_DB=1` 才生效 | ✅ 已验证 |
| `runtime/ingest.py` | 从真实 json 回填影子库 + 对账；**只读 live json** | ✅ 真实数据跑通 |
| `data/runtime.db` | 回填成品（12MB 快照，主机可原生打开） | ✅ 已生成 |

改动（非新增）：
- `orchestrator_advanced.py` / `orchestrator_realtime.py`：加 **DEPRECATED 头注释**（纯注释，零运行时副作用）
- `orchestrator.py`：周期末尾加 **影子库刷新钩子**——`PA_SHADOW_DB=1` 时只读本周期 json 回填 runtime.db，best-effort，**不改任何 json 写入路径**

---

## 验证结果（沙箱内可验证部分，全过）

- **shadow OFF**：只写 json，不生成 runtime.db → 零行为变化（可作纯重构安全采用）
- **shadow ON**：6 表正确落库；`put_signals` 幂等
- **生命周期护栏**（验证时发现并修复）：`paper_positions` UPSERT 用 `CASE`/`COALESCE`，**closed 不被 open 刷新覆盖回去**、平仓字段不被清空（对齐 5/29 registry 教训）
- **真实数据回填**：signals 8 / reviews 8 / paper_trades 3399 / runtime_events 9893
- **状态归一实锤**：`paper_portfolio.json` **2129 行 → 29 个唯一持仓**（16 open / 13 closed），印证历史「重复 closed 条目」膨胀
- **幂等性**：连跑两次 ingest 行数完全一致（周期钩子每轮安全）
- **全部 py_compile 通过**

发现的防漂移点（已处理）：三个「持仓类」文件字段名不同（portfolio=`direction/entry_price`，positions=`outcome/avg_entry_price/shares`，registry=`outcome/pnl`），ingest 已各自归一；`_txt()` 把 list/dict 字段（如 `risk_notes`）安全转 json，防 SQLite 绑定报错。

---

## ⚠️ 待主机验证（沙箱跑不了）

本沙箱（Linux）**缺 venv/openai/pm-trader**，且挂载不支持 SQLite WAL（已用 `PA_DB_PATH` 落 `/tmp` 绕过），所以**无法跑完整 18 步 dry-run 周期**。以下必须在 macOS 主机验证：

1. 主机重建影子库（不依赖沙箱快照）：
   ```bash
   cd /Users/libo/.hermes/polymarket_arbitrage
   PA_BASE_DIR="$PWD" python3 -m runtime.ingest      # 主机原生 WAL，db 落 data/runtime.db
   ```
2. 开影子库跑一轮受控 dry-run，验证周期钩子：
   ```bash
   EXECUTOR_DRY_RUN=1 PA_SHADOW_DB=1 PM_TRADER_PATH=/tmp/mock_pm_trader.sh \
     python3 -c "from orchestrator import Orchestrator; Orchestrator().run_once()"
   ```
   预期：周期 18/18 完成、日志出现「🗃️ 影子库已刷新」、`pytest tests/test_smoke.py` 全过。
3. 故障注入：临时让 `runtime/_shadow.py` 抛错，确认周期仍 18/18、json 照常落盘（best-effort 不阻断）。

---

## 下一步（Phase 0 收尾 + Phase 2 入口）

- **未做**：把 5 个核心写者（orchestrator/signal_executor/agent_m/agent_p/paper_pnl）的 `json.dump` 写入逐个改调 `datastore.*`（纯重构）。**本次刻意未做**——该改动触及 live 执行器，项目纪律要求 smoke 全过才可信，需在主机带 dry-run 做。`datastore.py` 门面与契约已就绪，照 `PHASE0_CONTRACTS.md §6` 采用顺序即可。
- 注意双执行器：`signal_executor.py` 根目录 + `executors/` 两份都要改。
- 识别出的深层问题：持仓缺 **canonical 市场身份**（portfolio 多数 `market_slug=""`、positions 无 `market_id`），状态归一要更稳需先统一市场主键 —— 建议列入 Phase 2。

---

## 本次新增/修改文件清单

| 文件 | 变更 |
|---|---|
| `runtime/__init__.py` `schema.sql` `datastore.py` `_shadow.py` `ingest.py` | 新增 |
| `data/runtime.db` | 新增（回填快照） |
| `orchestrator.py` | 周期末尾加 shadow 刷新钩子（guarded、additive） |
| `orchestrator_advanced.py` `orchestrator_realtime.py` | 加 DEPRECATED 头注释 |
| `VNEXT_GAP_ANALYSIS.md` `PHASE0_WRITE_CONVERGENCE.md` `PHASE0_CONTRACTS.md` | 新增设计文档 |

---

## 主机验证回收（用户已跑）

- `python3 -m runtime.ingest`：通过，runtime.db 可刷新
- `PA_SHADOW_DB=1 EXECUTOR_DRY_RUN=1 venv/bin/python3 main.py --mode once`：exit=0，日志见「🗃️ 影子库已刷新」；dry-run 安全（execution_results `total=4, success=0, dry_run=4`）；无 shadow/SQLite 错误
- dry-run 后 DB：signals=16 / reviews=16 / paper_trades=3411 / runtime_events=9920；JSON 仍为事实源（DB 未反向驱动业务写入）
- 既有问题：agent_e / agent_f 仍 120s 超时（与本次无关）
- 运行环境：必须用 `venv/bin/python3`（裸 python3 缺 openai/aiohttp/pytest）

### smoke 失败项已查证并修复
`tests/test_smoke.py::test_load_config` 断言 `agent_codex==deepseek-v4-flash` 失败。

**查证结论：应改测试，非改配置。** 证据：`config/llm_config.json`（路由事实源，gitignore 不入库）相对 `backup_20260524_201007`，**全部 21 个 agent 由 deepseek-v4-flash 统一升级为 deepseek-v4-pro**，是蓄意全局升级；test_load_config 恰好只对 agent_codex 做精确值断言，故唯一炸点。已将断言更新为 `deepseek-v4-pro`（加注说明）。

**待办**：主机重跑 `venv/bin/python3 -m pytest tests/test_smoke.py -q` 应为 **71 passed**；全过后即可把 Phase 1 标记为「主机验证通过」。调度仍停止（未恢复 launchd）。

---

## Phase 0 写入收敛 —— ✅ 主机验证通过（2026-06-02）

主机结果：`pytest tests/test_smoke.py` **71 passed**；`EXECUTOR_DRY_RUN=1 PA_SHADOW_DB=1` 单周期完成、`orchestrator_status.state=completed`、日志「🗃️ 影子库已刷新」；execution_results `total=4, success=0, dry_run=4`；DB 对账 signals=24/reviews=24/paper_orders=4/paper_trades=3427/runtime_events=9948；无 runtime/sqlite/shadow 错误；launchd 仍停。残留 `agent_e` 120s 超时为既有 LLM 问题，与本阶段无关。

> 注：本轮 `paper_orders=4` 首次非零 —— 收敛后 `record_executions` 的 per-call shadow 已在 live 周期内直接落 orders（此前靠 ingest 兜底为 0）。



把 5 个核心写者的 live 写入全部收敛到 `runtime.datastore` 门面（json 输出逐字节不变；shadow 默认关）：

| 文件 | 收敛的写入 | 门面函数 |
|---|---|---|
| `paper_pnl.py` | portfolio / trades | `save_portfolio` / `append_paper_trade` |
| `agents/agent_p.py` | positions / closed_registry / sell_signals | `set_positions` / `upsert_closed_positions` / `put_sell_signals` |
| `agents/agent_m.py` | review_results / approved_signals（标准模式，批次模式保留直写） | `put_review` |
| `executors/signal_executor.py` | execution_results / paper_trades | `record_executions` / `append_paper_trade` |
| `orchestrator.py` | signals / skipped review / skipped exec / status | `put_signals` / `put_review` / `record_executions` / `write_status` |

要点：
- 根目录 `signal_executor.py` 本就是 deprecated thin wrapper（re-export `executors/`），无需改 —— “两份执行器”天然只剩一份。
- 门面函数加了 `base_dir` 可选参，保留测试的 `tmp_path` 隔离（否则会写到真实 `data/`、破坏 smoke）。
- `agent_m` 批次模式（`output_file` 自定义）保留直写，不进 live review_results。
- bootstrap 的空文件 `[]` 脚手架属初始化、非业务写入，未改。
- 周期末 ingest 钩子**保留**：覆盖未收敛文件（latest_data/risk_snapshot/learning_*/health）+ runtime_events 全量；与 per-call shadow 幂等不冲突。全部写者收敛后可再撤。

收敛中发现并修复的正确性问题：
- **跨 schema 持仓归一**：三套字段名（portfolio=`direction/entry_price`、positions=`outcome/avg_entry_price/shares`、registry=`outcome/pnl`）会让 live 路径与 ingest 路径算出不同 `position_uid` → 重复行。已在 `_shadow._canon_pos()` 集中归一，uid 从归一后字段计算；ingest 改为直传原始 dict（raw_json 保留真原始）。验证：positions.json 与 paper_portfolio 两套字段映射到**同一持仓行**。
- `_txt()` 把 list/dict 字段（如 `risk_notes`）安全转 json，防 SQLite 绑定报错。

沙箱验证（全过）：全部改动 py_compile 通过；核心代码无残留直写 live 文件；真实数据 ingest x2 幂等；门面全表面 json+shadow 双写一致；paper_pnl 开仓格式/隔离正确。

**待主机验证**（沙箱跑不了完整 dry-run）：
```bash
venv/bin/python3 -m pytest tests/test_smoke.py -q          # 期望仍 71 passed（收敛为纯重构）
EXECUTOR_DRY_RUN=1 PA_SHADOW_DB=1 PM_TRADER_PATH=/tmp/mock_pm_trader.sh \
  venv/bin/python3 -c "from orchestrator import Orchestrator; Orchestrator().run_once()"
# 期望：周期 18/18；signals/review/exec/positions/sell_signals/status 经门面落盘且内容与收敛前一致
```
全过后 Phase 0 即可标记主机验证通过；之后才是 Phase 2（paper_pnl API化）。

---

## Phase 2a —— Canonical Market Identity ✅ 主机验证通过（2026-06-02）

主机结果：smoke **71 passed**；删旧库重建后 `runtime.ingest` 对账 markets(seed)=100 / markets 行=107 / `paper_positions=22`（从 29 下降）/ canonical 权威 id=20、临时键=1；`git status` 无 `data/*.json` 污染，仅刷新 `data/runtime.db*`。

**纯影子层改动，未动任何 live json 写入**（dry-run/live 零影响）。详见 `PHASE2A_MARKET_IDENTITY.md`。

- canonical key = Polymarket 数字 id；持久 `markets` 维表累积 id↔slug↔question（latest_data 权威 + 业务记录 harvest）。
- `runtime/market_identity.py` 新增 resolve（id→slug→question→临时键 `slug:<x>`）；`paper_positions` 加 `canonical_market_id` 列、position_uid 改用 canonical。
- 脏数据：同一 slug 被多 id 引用 → slug 非唯一索引 + resolve 取 last_seen 最新（权威胜）。
- **验证**：持仓 **29→22**（slug-only registry 行与 id portfolio 行合并）；解析 20 权威 id / 1 临时键 / 1 无标识；markets 107 行；幂等；定向合并测试（slug-only+id 落同一行、closed 护栏保住）通过；全部 py_compile 通过。
- 局限：已存在的临时键 `slug:<x>` 行不会自动迁移到 id（需一个 reconcile 小作业，留 Phase 2b）。

**待主机轻验**：本轮无 live 写改动，`pytest tests/test_smoke.py` 应仍 **71 passed**；`python3 -m runtime.ingest` 重建库后 `paper_positions` 应较 29 下降（主机数据为准）、`markets` 非空。

### 2a 主机轻验发现的 schema 迁移缺口（已修）

主机首验：smoke 71 passed，但 `runtime.ingest` 报 `no such column: canonical_market_id`。

**根因**：旧 `data/runtime.db`（Phase 0/1 快照）已有 `paper_positions` 表，`CREATE TABLE IF NOT EXISTS` 对旧表是 no-op、不会加列；且 schema.sql 里 `idx_pos_canon` 索引引用新列，executescript 跑到该行即报错中止，连 `markets` 表都没建成。**不是 smoke/import/JSON 问题。**

**修复**（`runtime/_shadow.py` + `schema.sql`）：
- 加轻量自迁移 `_migrate()`（无 Alembic）：建缺失表 → 用 `ALTER TABLE ADD COLUMN` 给旧表补 `_EXPECTED_COLUMNS`（含 canonical_market_id）→ 补列后再建 `idx_pos_canon`。幂等，全新库与旧库都到目标 schema。
- 把 `idx_pos_canon` 从 schema.sql 移出（改由 `_migrate` 在补列后创建）。
- 验证：模拟旧 Phase0/1 库 → 自迁移补列/建表/建索引、数据不丢、迁移后 upsert 正常。

**注意（旧 uid 孤儿行）**：迁移只补列，旧库里按旧 uid 存的持仓行 canonical 为 NULL、不会被新 canonical-keyed upsert 更新 → 与新行并存致计数虚高。因影子库是可重建纯旁路，**2a 主机验证请删库重建**（见下）。沙箱已把仓库内 `data/runtime.db` 替换为干净 2a 快照（schema_version=0.2.0-phase2a、markets=107、paper_positions=22）。

### 2a 主机轻验（修订命令）
```bash
cd /Users/libo/.hermes/polymarket_arbitrage
venv/bin/python3 -m pytest tests/test_smoke.py -q          # 期望仍 71 passed
rm -f data/runtime.db data/runtime.db-wal data/runtime.db-shm   # 删旧库，干净重建
PA_BASE_DIR="$PWD" venv/bin/python3 -m runtime.ingest      # 期望：markets 非空；paper_positions < 29；canonical 多数为权威 id
```

### 三轮受控 dry-run 稳定性观察 ✅ 通过（2026-06-02，未恢复 launchd）

| 指标 | C1 | C2 | C3 | 判读 |
|---|---|---|---|---|
| signals | 16 | 24 | 32 | +8/轮，agent_b 产出经门面正常 |
| reviews | 16 | 24 | 32 | +8/轮，与 signals 同步 |
| paper_orders | 5 | 10 | 12 | +5/+5/+2，精确对上 exec dry_run 数 |
| **paper_positions** | 22 | 22 | 22 | **三轮锁死，canonical 去重+护栏稳住，无膨胀** |
| paper_trades | 3445 | 3455 | 3459 | 有序递增 |
| runtime_events | 9977 | 10000 | 10020 | 有序递增 |
| markets | 107 | 107 | 107 | 幂等播种稳定 |
| exec success | 0 | 0 | 0 | dry-run 护栏守住，真实下单 0 |

每轮 `state=completed` + 「🗃️ 影子库已刷新」；无 traceback/sqlite/shadow 错误；`git status` 无 json 污染。唯一噪声 `agent_e` 120s 超时（既有 LLM 问题）。

**结论**：Phase 0 + 1 + 2a 在连续 live dry-run 下稳定。`paper_positions` 恒定 22 实测证明历史"重复 closed 行膨胀"病根（2129 行）已根治。

下一步：见下 Phase 2b。

---

## Phase 2b —— Paper Runtime API（FastAPI）✅ 主机验证通过（2026-06-02）

主机结果：依赖 fastapi 0.128.8 / uvicorn 0.39.0；smoke **71 passed**；uvicorn 起在 127.0.0.1:8848；GET `/healthz`=ok、`/runtime/status`=completed、`/paper/positions` summary `total=22,open=8,closed=14`、`/markets` 正常；**写并发锁**：占住 orchestrator.lock 后 POST `/paper/open` 得 **409 写者忙**。临时进程已停、无遗留、无 json 污染。
- **主机兼容修复**：主机 venv 是 **Python 3.9**，FastAPI 运行时 introspect 签名 → `runtime/api.py` 的 `status: str | None` 在 3.9 下解析失败，已最小改为 `Optional[str]`（行为不变）。已记入 CLAUDE.md 纪律：API 端点注解禁用 PEP 604 `X | None`。

---

## Phase 3a —— Agent G → Postmortem Engine ✅ 主机验证通过（2026-06-03）

主机结果：smoke **71 passed**；删库重建后 ingest 正常(paper_positions=22/markets=107/postmortems 表正常)；受控单周期完成、日志见 `🗃️ 影子库已刷新` + `🧾 新增 14 笔复盘`、`data/postmortems.jsonl`(~8.9K) 生成；`GET /postmortems` 200，结构化字段齐全(hypothesis/expected_edge/outcome/failure_reason/三 issue/source=deterministic)；无 sqlite/traceback；`git status` 仅 `?? runtime/`，无 data/*.json 污染。运行噪声 agent_b/agent_f 超时→signals stale→M/买入安全跳过（既有 LLM 问题）。

Phase 3 第一步，选 G(复盘)：**纯加法、低风险**，不改审批/执行/学习行为。靠 2a canonical 身份把【已平仓持仓】join 回【原始信号】。详见 `PHASE3A_POSTMORTEM.md`。

- **逐笔结构化复盘** → `data/postmortems.jsonl`(事实源) + 影子 `postmortems` 表。PRD 字段全落地：hypothesis/expected_edge/actual_result/failure_reason/liquidity_issue/timing_issue/model_issue。
- 两路径：**确定性 fallback**(默认，沙箱可验) + **LLM 增强**(use_llm，主机，仅 failure_reason 叙述)。
- **新增**：`runtime/postmortem.py`；`_shadow` 加 query/upsert/join 助手；`datastore.append_postmortem`；`api` 加 `GET /postmortems` + `POST /admin/generate-postmortems`；schema 加 `postmortems` 表(→0.3.0-phase3a)。
- **改动 orchestrator**：周期末 shadow 钩子内加一行确定性复盘(best-effort，PA_SHADOW_DB=1 时)。**未改 agent_g 核心/审批/执行**。
- **验证**：沙箱确定性归因正确(高置信亏损→model_issue、liquidity→liquidity_issue)、双写、幂等、API 全过；真实数据 14 已平仓→14 复盘(6flat/7loss/1win)。
- **附带发现**：一笔 pnl=+274 盈利却 close_reason="止损-100%"，源数据自相矛盾——引擎按 pnl 正确判 win 并暴露之（数据清洗线索）。

**待主机验证**：smoke 仍 71；删库重建 ingest；受控单周期见「🧾 新增 N 笔复盘」；`GET /postmortems` 返回结构化复盘。命令见 PHASE3A_POSTMORTEM.md §4。

**三轮连续 dry-run 幂等观察（2026-06-03）**：postmortems 三轮稳定 14（outcome 6flat/7loss/1win、issue liquidity=3/model=1 不变），无「新增」行（无新平仓）、无重复膨胀、无报错；paper_positions 仍 22。**复盘引擎连续周期幂等性通过。**

---

## Phase 3b —— Agent P 波动退出 + 价格历史（沙箱验证通过，待主机验证）

方案选定：**自建每市场价格历史**（risk_snapshot 的波动是底层参考资产、多数预测市场无映射）。详见 `PHASE3B_AGENT_P_VOLATILITY.md`。

- **价格历史持久化**：orchestrator 新增步骤 1.5，每周期把 latest_data 价格记入 `data/market_price_history.json`(事实源，每市场滚动 60 点) + 影子 `market_prices` 表。**无条件写**（agent_p 读事实源，不受 PA_SHADOW_DB 门控）。
- **波动 helper**（`runtime/price_history.py` 纯函数）：realized_volatility / should_volatility_exit（**样本<5 不触发**）/ high_water。
- **agent_p 波动退出分支**：止盈/止损/回撤都不触发时，市场近窗口波动超阈值(默认0.08)→ `波动退出` 卖出信号(medium)；slug→id 从 latest_data 取，读 json 事实源不依赖 DB。
- schema → `0.3.1-phase3b`（加 market_prices 表）。
- **验证**：helper（高波动触发/样本守护）、门面双写+去重+滚动、orchestrator 步骤（💹 价格快照）+ 累积波动触发、真实 ingest 无回归（22/107）全过；agent_p 决策抽成纯函数独立验证（本体含 LLM 沙箱不可导入，仅 py_compile）。
- **刻意不做**：trailing 真实最高水位（high_water 已就位，但改既有 trailing 会动行为/测试，留低风险后续）。

**单轮主机验证 ✅ 通过（2026-06-03）**：smoke **71 passed**；schema 0.3.1；ingest market_prices=0(不回填)/paper_positions=22/markets=107；单周期 18/18 completed、日志「💹 记录 100 个市场价格快照」、`market_price_history.json` 生成(100 市场×1 点)、影子 market_prices=100；execution success=0/dry_run=2；无 sqlite/traceback。波动退出尚不可判（每市场仅 1 点 < 样本守护 5）。**下一步：5+ 轮 dry-run 观察波动退出触发与幂等。**（agent_e/f 120s 超时为既有噪声；postmortems 重生成 14 是删库重建所致，非回归。）

**5+ 轮观察 runbook 已补入 `PHASE3B_AGENT_P_VOLATILITY.md`**：观察点为每市场历史点数递增、第 5 轮后才可能出现 `波动退出`、closed_registry 去重不膨胀、`market_prices` append 正常、dry-run `success=0` 护栏守住。若 5+ 轮仍不触发，优先判定为市场价格平静/阈值 0.08 未达，不直接判 bug。

**5+ 轮自然 dry-run 观察 ✅ 通过（2026-06-03）**：连续 6 轮受控 dry-run 完成，价格历史从单轮后的 1 点累积到 7 点/市场；覆盖市场恒定 100，点数分布最终 `{7: 100}`；影子 `market_prices` 从 100 线性增至 700；`paper_positions` 恒定 22；`postmortems` 恒定 14（无重复膨胀）；每轮 `扫描周期完成`，最终状态 `completed`。前 4 轮无 `波动退出` 符合样本守护；第 5/6 轮样本足够后仍无 `波动退出`，判定为自然价格波动未达默认阈值 0.08，不是逻辑失败。dry-run 护栏守住（最终 execution `success=0/dry_run=2/failed=0`）；无 traceback/sqlite/no such column/OperationalError/Exception；无残留项目进程。

---

## Phase 3c —— Agent B → Research/Hypothesis（3c-1/3c-2 主机验证通过）

两步走：**3c-1 加法派生**（零 live 风险）+ **3c-2 扩 B prompt**（live agent LLM 输出 schema 加法）。详见 `PHASE3C_AGENT_B_HYPOTHESIS.md`。

**3c-1（已完成）**：每个信号确定性派生结构化研究假设 → `data/hypotheses.jsonl`(事实源) + 影子 `hypotheses` 表。**不改 agent_b/prompt/交易决策。**
- 字段：direction/confidence/expected_edge（信号现成）+ holding_horizon_days（从 risk_notes end_date 派生）+ thesis + risk_summary + failure_conditions（从 risk_notes 风险项派生，偏样板）。
- **前向兼容 3c-2**：原生 holding_horizon_days/failure_conditions 优先，B 一旦输出即自动采用（source derived→agent_b）。
- 新增 `runtime/hypothesis.py`；`_shadow` upsert/query；`datastore.append_hypothesis`；`api` GET /hypotheses；schema → `0.3.2-phase3c`；orchestrator 步骤 12.5b 无条件派生(best-effort)。
- **闭环**：hypothesis.signal_uid == postmortem.signal_uid（假设→结果→复盘可 join）。
- **验证**：派生/原生优先、幂等、闭环 join、API 全过；真实 signals 8→6 假设(去重)、持仓时长/失败条件 6/6；ingest 无回归(22)。

**3c-2 主机验证 ✅ 通过（2026-06-03）**：扩 agent_b prompt 输出 holding_horizon_days + failure_conditions（逐市场真推理）。
- 改 `agents/agent_b.py` prompt（要求 #8 + 输出示例）+ `orchestrator.py` consolidation 白名单。
- **抓到并修了一个会让 3c-2 静默失效的 bug**：consolidation 用固定字段白名单归一信号，原白名单不含新字段 → 会被丢掉到不了 signals.json。已加入白名单透传。
- **M 容忍性确认**：M 全程 `.get(默认)` + `json.dumps(signal)` 整体 dump，无严格校验/无 required-keys 拒绝 → 新字段安全（还能进 M 的 prompt 上下文）。
- **沙箱验证**：模拟 B 原生输出 → consolidation 透传 → signals.json 保留 → 提取器 source=agent_b 用真值；M 访问模式不炸。py_compile 通过。
- **主机验证**：smoke **71 passed**；删库重建 schema `0.3.2-phase3c`，`hypotheses=0`/`paper_positions=22`/`markets=107`；真实周期完成，Agent B 汇总 8 个新信号，日志「🔬 派生 8 条研究假设」；Agent M `✅ agent_m 执行成功`、无解析报错；`signals.json` 8/8 带新字段；DB `hypotheses=8`、source 分布 `{'agent_b': 8}`；假设↔复盘 join=2；execution `success=0/failed=0`（本轮无待执行买入）；最终 `completed`；无 traceback/sqlite/no such column/OperationalError/Exception；无残留项目进程。

**3c-1 主机验证 ✅ 通过（2026-06-03）**：smoke **71 passed**；删库重建 schema `0.3.2-phase3c`，`hypotheses=0`(ingest 不生成)/`paper_positions=22`/`markets=107`；受控单周期完成，日志「🔬 派生 1 条研究假设 (hypotheses)」+「✅ 扫描周期完成」+「🗃️ 影子库已刷新」；`data/hypotheses.jsonl` 生成；DB `hypotheses=1`、`source=derived`、字段齐全（NHL market, NO, confidence=85, edge=19.5, hold=27）；假设↔复盘 join=0（本轮信号暂无 postmortem，正常）；execution `success=0/dry_run=1/failed=0`；无 traceback/sqlite/no such column/OperationalError/Exception；无残留项目进程。

---

## Phase 3d —— Agent M 三级 Risk Grading（主机补充验证通过）

Phase 3 压轴，唯一直接改审批→执行行为的一步。详见 `PHASE3D_AGENT_M_GRADING_DESIGN.md`。

- **实现**：`agents/agent_m.py` 加 PAPER_PROBE prompt 说明 + 确定性 `_grade()` 后处理；band `[35%,60%)` 且信号健全 → `PAPER_PROBE`；probe 仓位压到正常 ×0.25；`approved_signals.json` 包含 approve + probe；`runtime/_shadow.py` 支持 reviews 表写 `PAPER_PROBE`。
- **沙箱验证**：`_grade()` 真值表、probe 压仓、reviews 三级落库、py_compile 全过。
- **主机 smoke**：**71 passed**；删库重建正常，schema `0.3.2-phase3c`，`reviews=8`/`signals=8`/`paper_positions=22`/`markets=107`。
- **自然 orchestrator 周期 caveat**：周期完成，但 Agent M 被 stale guard 跳过（`signals stale: age=16937s exceeds max_age=7200s`），买入执行也跳过；该自然周期没有验证到 M 三级分流，护栏仍 `success=0`。
- **补充最小验证**：直接运行 Agent M 审查当前 8 个 signals，缓存命中 8/8；日志 `[grade] approve 0, paper_probe 5, reject 3`；`review_results.json` = approved=0 / paper_probe=5 / rejected=3 / total=8；`approved_signals.json` 5 条全部 `grade=paper_probe`，仓位全部 `0.025`；reviews 表出现 `PAPER_PROBE`。
- **执行护栏/学习隔离**：用 `EXECUTOR_DRY_RUN=1` + mock pm-trader 单独跑 signal_executor，5 条 probe 全部 `status=dry_run`，execution `success=0/dry_run=5/failed=0`，execution grade 分布 `paper_probe=5`。无 traceback/sqlite/no such column/OperationalError/Exception；无残留项目进程。

判读：3d 核心高风险项（三级分流、probe 压仓、执行护栏、学习隔离）主机补充验证通过；若要求严格“orchestrator 全周期内 M 审查执行”，需等/生成 fresh signals 后再跑一轮。

Phase 3 剩余：严格全周期 fresh-signal 复验 Agent M（可选收口项）；其他 B/P/G/M 改造主体验证均已完成。



选型拍板：含 open/close 写；GET 读影子 DB(canonical)；FastAPI 跑主机 venv。详见 `PHASE2B_PAPER_API.md`。

- **写并发不破单写者**：POST /paper/open|close 复用同一把 `orchestrator.lock`（`runtime/locking.py`）——周期跑时 POST 返回 **409**，绝不与周期并发写 paper。写仍经 paper_pnl→datastore 门面（JSON 事实源 + shadow 同步）。
- **新增**：`runtime/api.py`（GET positions/trades/signals/reviews/markets/status + POST open/close + /admin/reconcile-provisional）、`runtime/locking.py`；`_shadow` 追加只读 `query_*`/`positions_summary` + `upgrade_provisional_positions()`（2a 临时键尾巴）+ `busy_timeout=5000`（API 与 orchestrator 并发开同库）。
- **未改任何 live 写者**（纯新增 + _shadow 追加只读/运维）。
- **沙箱验证（TestClient，全过）**：GET canonical 正常；POST open 双写 json+DB；**锁 409**（占 orchestrator.lock→409，释放→200）；reconcile 把 `slug:will-z` 临时键升级到权威 id 541000（临时键 1→0）。

**待主机验证**：
```bash
venv/bin/python3 -m pip install fastapi uvicorn
venv/bin/python3 -m pytest tests/test_smoke.py -q   # 期望仍 71（未改 live 写者）
PA_SHADOW_DB=1 PA_BASE_DIR="$PWD" venv/bin/python3 -m uvicorn runtime.api:app --host 127.0.0.1 --port 8848 &
curl -s localhost:8848/paper/positions | head   # canonical 视图
# 周期进行中并发 POST /paper/open 应得 409
```
