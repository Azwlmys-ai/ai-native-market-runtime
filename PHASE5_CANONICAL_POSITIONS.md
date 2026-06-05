# Phase 5（Web）— Canonical 持仓视图（tsc 通过）

> 日期：2026-06-04
> 对应 VNEXT 里程碑 §6 尾巴 #4：**dashboard 切 canonical 视图**——读去重后的 canonical 持仓，而非膨胀裸 JSON。
> 选型（用户已拍板）：**better-sqlite3 直读 runtime.db** + **独立 `/positions` 页**。

---

## 1. 背景 / 落差

- dashboard 此前**根本没有持仓视图**（已有 signals/reviews/execution/hypotheses/postmortems/risk-grading，无 positions）。
- 持仓真相分两处：裸 `paper_portfolio.json` 已膨胀到 **2213 条**（历史累积、含重复）；而 Phase 2a 的 canonical 影子表 `runtime.db/paper_positions` 是**按 canonical_market_id 去重后的 22 行**（8 open / 14 closed）。
- 目标：dashboard 展示 canonical 的 22 行，不碰 2213 条裸 JSON。

---

## 2. 做了什么

| 文件 | 作用 |
|---|---|
| `dashboard/app/api/positions/route.ts` | 新增只读路由：better-sqlite3 以 `readonly` 直读 `data/runtime.db` 的 `paper_positions`（canonical），返回 summary + 持仓列表；模块/库/表任一缺失一律优雅 fallback（`source:'fallback'` + note），UI 不崩 |
| `dashboard/app/positions/page.tsx` | 新增**独立 `/positions` 页**（自包含，30s 轮询，零侵入主 `page.tsx`）：6 个 summary 卡片（总持仓/open/closed/open 名义敞口/已实现 PnL/dry_run 笔数）+ canonical 持仓表（市场+canonical id、方向、状态、入场/出场价、名义、已实现 PnL、开仓时间、平仓原因），空态占位 |
| `dashboard/app/types/better-sqlite3.d.ts` | ambient `declare module 'better-sqlite3'`：让 tsc 在**未装原生模块**的环境（沙箱）通过；主机装了 better-sqlite3（无 @types）也靠它避免 TS7016 |
| `dashboard/package.json` | 依赖新增 `better-sqlite3 ^11.8.1`（由主机 `npm install` 编译本机原生二进制） |

设计要点：
- **去重逻辑不在前端**：直接吃影子表已去重的行（canonical_market_id 为主键语义）。
- **DB 是可重建旁路**：故路由对一切缺失都 fallback，不把 dashboard 可用性绑死在 DB 上。
- **排序**：open 优先，再按 `opened_at` 倒序。
- **summary 基于全量**，不受 `?status=` 过滤影响（单独查一次）。

---

## 3. 验证

- **tsc `--noEmit` 全量 0 错误**（含新增 3 个 TS 文件）。
- **canonical 查询正确性**（用 Python sqlite3 复刻路由的完全相同 SQL + summary 逻辑，对真实 `data/runtime.db` 实跑，SQLite 引擎与驱动无关）：
  - `total=22 open=8 closed=14`（= Phase 2a 去重目标）。
  - `openNotional=$8000 · realizedPnl=+$179.60 · dryRun=22`（全 dry_run，护栏一致）。
  - 排序验证：open 行排在最前。`?status=open` 过滤返回 8 行。
- **未污染共享 node_modules**：沙箱网络受限无法编译 better-sqlite3 原生模块（node headers 403），故**没有**把任何 Linux 原生二进制写进共享 `dashboard/node_modules`；驱动由主机自行 `npm install` 编译。
- Next dev server 渲染需主机起（沙箱不便跑），tsc + 真实 DB 查询是沙箱验证上限。

---

## 4. 主机预览步骤

```bash
cd /Users/libo/.hermes/polymarket_arbitrage/dashboard
npm install            # 关键：编译本机 macOS 版 better-sqlite3 原生二进制
npm run dev            # 或 next dev
# 浏览器打开 http://localhost:3000/positions
```

前置：`data/runtime.db` 需存在（影子库）。若没有：
```bash
cd /Users/libo/.hermes/polymarket_arbitrage
PA_BASE_DIR="$PWD" venv/bin/python3 -m runtime.ingest   # 回填重建影子库
```

预期：summary 显示 `总持仓 22 / open 8 / closed 14 / open 名义敞口 $8,000 / 已实现 PnL +$180 / dry_run 22`；表格列出 22 行 canonical 持仓（open 在前）。DB 缺失则整页 fallback 占位、不报错。

---

## 5. 局限 / 后续

- `/positions` 是独立页，未嵌入主 dashboard 导航（刻意，沿用 `/research` 零侵入范式）；后续可在主导航加 `/positions`、`/research` 入口。
- 仅读 `paper_positions`；trades/复盘已分别由 `/api/positions` 之外的路由或 `/research` 承载。
- 实时性靠 30s 轮询（非 WebSocket，与 dashboard 现状一致）。
- 若未来想彻底摆脱原生依赖，可改回「Python 导出 canonical JSON 快照 + Next.js 只读」——本轮按用户选型用 better-sqlite3 直读。
