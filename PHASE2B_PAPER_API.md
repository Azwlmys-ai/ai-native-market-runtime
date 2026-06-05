# Phase 2b — Paper Runtime API（FastAPI，沙箱验证通过）

> 日期：2026-06-02
> 路线：保留 Next.js 只读 Dashboard + Python 单写者 Runtime。
> 选型（已拍板）：含 open/close **写**端；GET 读 **影子 DB（canonical）**；FastAPI 跑 **主机 venv**。

---

## 1. 核心设计：写并发如何不破单写者

Phase 0 花大力气把 live 写入收敛成单写者（orchestrator 周期串行，`data/orchestrator.lock` fcntl 锁）。Phase 2b 引入 API 写端后，**API 写与周期写必须互斥**，否则又是多写者。

方案：**API 的 POST 写端复用同一把 `orchestrator.lock`**（`runtime/locking.py`）。
- POST /paper/open|close 进来先**非阻塞抢** orchestrator.lock。
- 抢不到（周期正在跑 / 另一次 API 写）→ **409 写者忙**，让调用方稍后重试。
- 抢到 → 经 `paper_pnl` → `runtime.datastore` 门面写（**JSON 仍是事实源**，shadow 同步）→ 释放锁。

→ 同一时刻只有一个写者，无论它是扫描周期还是 API 写。Phase 0 不变量守住。

并发读：API 进程与 orchestrator 进程并发开同一 `runtime.db`，已加 `PRAGMA busy_timeout=5000`，WAL 下并发写等待而非 "database is locked"。

---

## 2. 端点

| 方法 | 路径 | 说明 | 数据源 |
|---|---|---|---|
| GET | `/runtime/status` | 周期状态 | json 事实源（最新） |
| GET | `/paper/positions?status=open\|closed` | canonical 持仓 + summary | 影子 DB（去重） |
| GET | `/paper/trades?limit=` | 成交流水 | 影子 DB |
| GET | `/signals` `/reviews` `/markets` | 信号/审查/市场维表 | 影子 DB |
| POST | `/paper/open` （body: signal） | 开 paper 仓 | 写 json+DB，**带锁** |
| POST | `/paper/close` （body: sell_signal） | 平 paper 仓（无匹配 404） | 写 json+DB，**带锁** |
| POST | `/admin/reconcile-provisional` | 升级历史临时键 slug:&lt;x&gt; → 权威 id | DB |
| GET | `/healthz` | 健康检查 | — |

`/paper/positions` 的 positions 是 **canonical 去重视图**（按 `canonical_market_id`，如 22 而非膨胀的 2143）——这正是 2a 建的价值。

---

## 3. 新增文件（全在 runtime/）

| 文件 | 作用 |
|---|---|
| `runtime/api.py` | FastAPI app（GET 只读 + POST 带锁写 + 运维端点） |
| `runtime/locking.py` | `single_writer_lock()` 复用 orchestrator.lock；`WriterBusy` → 409 |
| `runtime/_shadow.py`（追加） | 只读查询 `query_*` / `positions_summary` + `upgrade_provisional_positions()`（2a 尾巴）+ busy_timeout |

**未改任何 live 写者**；本轮纯新增 + _shadow 追加只读/运维函数。

---

## 4. 验证（沙箱 TestClient，全过）

- GET：`/healthz`、`/runtime/status`(state=completed)、`/paper/positions`(summary 正确)、`/markets` 正常。
- POST `/paper/open`：200，写出 `paper_portfolio.json`（事实源）+ DB `paper_positions` 同步 +1。
- **锁 409**：手动占住 `orchestrator.lock` 再 POST → **409 写者忙**；释放后 POST → 200。与周期互斥确认。
- **reconcile**：构造 `slug:will-z` 临时键持仓 + 后到的 slug→id 映射 → `/admin/reconcile-provisional` 升级 1 行，临时键计数 1→0，will-z canonical 变 541000。Phase 2a 尾巴闭环。
- `busy_timeout=5000` 生效；全部 py_compile 通过。

---

## 5. 主机验证步骤（待跑）

```bash
cd /Users/libo/.hermes/polymarket_arbitrage
venv/bin/python3 -m pip install fastapi uvicorn            # 依赖（一次性）
venv/bin/python3 -m pytest tests/test_smoke.py -q          # 期望仍 71 passed（本轮未改 live 写者）

# 起 API（只读优先验证）
PA_SHADOW_DB=1 PA_BASE_DIR="$PWD" \
  venv/bin/python3 -m uvicorn runtime.api:app --host 127.0.0.1 --port 8848 &
curl -s localhost:8848/healthz
curl -s localhost:8848/paper/positions | python3 -m json.tool | head
curl -s localhost:8848/runtime/status

# 写端 + 锁验证
curl -s -X POST localhost:8848/paper/open -H 'content-type: application/json' \
  -d '{"market_id":"540817","market_slug":"...","direction":"NO","price":0.4,"position_size":0.1,"source":"api_manual"}'
# 在一次 run_once() 进行中并发 POST，应得 409
```

预期：smoke 71；GET 返回 canonical 数据；POST 写出 json + DB；周期进行中 POST 得 409。

---

## 6. 局限 / 后续

- POST 写端目前直接收 signal/sell_signal dict（未做严格 schema 校验）；后续可加 Pydantic 模型。
- Next.js dashboard 暂仍读 json；如要切到 `/paper/*` canonical 视图是独立小改。
- 仍是 dry-run-first：API 写的是 paper（虚拟），不触发真实下单。
- 进程托管（launchd/常驻）未做；本轮只验证可手起。
