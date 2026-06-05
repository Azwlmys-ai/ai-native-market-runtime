# Phase 5（Web）— 研究闭环 Dashboard 视图（typecheck 通过）

> 日期：2026-06-03
> PRD 剩余：Phase 5 Dashboard。本轮做 **Web 端「研究闭环」视图**，把 3a/3c/3d 产出的复盘/假设/风险评级首次接进 dashboard。
> 路线一致：**Next.js 只读、Python 侧写**；新增只读 `/api` 路由读 JSON 事实源，不调 Python FastAPI、不碰现有复杂 `page.tsx`。

---

## 1. 做了什么

新增一个**自包含页面 `/research`** + 3 个只读 API 路由，体现 PRD「研究→试错→复盘→进化」闭环，对应 PRD dashboard 目标「当前风险等级 / 当前 hypothesis / 最近失败原因」。

| 新增文件 | 作用 |
|---|---|
| `dashboard/app/api/risk-grading/route.ts` | 读 `review_results.json` → Agent M 三级（approve/paper_probe/reject）+ 每条市场/失败概率/仓位 |
| `dashboard/app/api/hypotheses/route.ts` | 读 `hypotheses.jsonl` → Agent B 假设（方向/置信/预期边/持仓时长/失败条件/source） |
| `dashboard/app/api/postmortems/route.ts` | 读 `postmortems.jsonl` → Agent G 复盘（outcome/realized_pnl/failure_reason/liquidity\|timing\|model_issue） |
| `dashboard/app/research/page.tsx` | 自包含页面：三级评级表 + 假设卡片（含失败条件、agent_b/derived 标记）+ 复盘卡片（含 issue 标签、盈亏色） |

- 全部沿用现有路由范式（`readFile` from `DATA_DIR`，`safeParse`，fallback 空结构防 UI 崩）。
- `/research` 30s 轮询，不依赖主 dashboard 的复杂 hooks，零侵入。

---

## 2. 验证

- **`tsc --noEmit` 全量 0 错误**（含新增 4 文件），未引入任何类型回归。
- 数据形态已与主机真实文件核对：postmortems.jsonl 70 行、hypotheses.jsonl 9 行、review_results.json `paper_probe=5 / rejected=3`。

> Next dev server 渲染需主机起（沙箱不便跑）；typecheck 是沙箱验证上限。

---

## 3. 主机预览步骤

```bash
cd /Users/libo/.hermes/polymarket_arbitrage/dashboard
npm run dev            # 或 next dev
# 浏览器打开 http://localhost:3000/research
```

预期：
- **Agent M 三级评级**：summary（approve/paper_probe/reject 计数）+ 明细表，paper_probe 行有琥珀色标、仓位显示被压小（×0.25）。
- **Agent B 假设**：卡片列出方向/置信/预期边/持仓天数；`source=agent_b` 蓝标、`derived` 灰标；有失败条件则列出。
- **Agent G 复盘**：win/loss/flat 计数 + 卡片（失败原因 + 流动性/时机/模型 issue 标签 + 盈亏色）。
- 数据为空时各区显示占位文案（等一轮 Agent M/G 跑出数据），不报错。

---

## 3b. Mobile = Telegram bot（已做，2026-06-03）

主机无固定 IP，Web 不便外访 → **PRD Mobile 端用现有 Telegram bot 实现**（`scripts/local_gateway_control.py`，只读、dry-run 安全）。

- **修复回归**：3d 三级 grading 让 `review_results.approved=0`（批准转为 paper_probe），bot 的 status/metrics/live-readiness 还按二元读 approved/rejected，显示矛盾的「审查通过:0 待执行:5」。已三处加 `paper_probe`（试错），数字自洽：`审查通过:0 试错:5 拒绝:3 待执行:5`；live-readiness 准确标注 probe 是 dry_run paper 不下真实单。
- **新增两命令**（PRD Mobile：当前 hypothesis + 最近失败原因）：
  - `hypotheses`：Agent B 研究假设（方向/置信/边/持仓 + 逐市场失败条件，source=agent_b/derived）。
  - `postmortems`：Agent G 复盘（win/loss/flat 汇总 + 最近 N 笔失败原因 + 流动性/时机/模型 issue 标签）。
- 注册进 COMMANDS、更新 HELP 与 `docs/hermes_bot_control_skill.md`（意图映射 + 命令表 + 三级解读）。
- **验证**：全部 9 个只读命令在真实 data/ 上冒烟通过、无异常；hypotheses 正确显示 3c-2 原生逐市场失败条件。
- PRD Mobile 目标对照：仓位(status)✓ · 当前 hypothesis(hypotheses)✓ · 当前风险等级(status 三级)✓ · 最近失败原因(postmortems)✓。

## 3c. PRD Mobile 原生视图 = bot 发送自包含 HTML（2026-06-04 定稿）

主机无固定 IP，不起在线 Mobile 服务 → **PRD Mobile「原生视图」正式由 Telegram bot 的 `report` 命令承担**：`scripts/mobile_report.py` 生成自包含离线 HTML（`data/reports/research_*.html`），bot 作为文档发送，手机浏览器直接打开。

本轮把它补成**完整 Mobile 视图**，覆盖 PRD Mobile 四目标：
- **仓位**：新增「💼 Paper 持仓」段——读 **canonical**（`runtime.db` 去重，缺库回退裸 portfolio）的持有中列表（市场/方向/入场/名义）+ 已平仓数 + 已实现盈亏。**修掉**此前读裸 `paper_portfolio.json`（2213 条）导致的持仓 KPI 膨胀。
- **当前风险等级**：Agent M 三级评级表（通过/试错/拒绝）。
- **当前 hypothesis**：Agent B 假设卡（方向/置信/边/持仓 + 失败条件 + 原生/派生）。
- **最近失败原因**：Agent G 复盘卡 + **3c-2 失败条件对照徽章**（假设证伪/成立/亏损·预测外/无定论），postmortems 按 `postmortem_uid` 去重还原 canonical 笔数。

零依赖（仅 stdlib + sqlite3 只读）、离线、只读、模拟盘安全。

## 4. 局限 / 后续

- Web `/research` 已做但主机无固定 IP 暂不外访；Mobile 由 Telegram bot 发送 HTML 承担（见 §3b/§3c）。
- `/research` 是独立页面，未嵌入主 dashboard 布局（刻意，避免动复杂 `page.tsx`）；后续可加导航入口或并入。
- 仍读 JSON 事实源（与 dashboard 现状一致）；如需 canonical 去重持仓视图，可再加 `/api` 路由读 `runtime.db`（better-sqlite3）或调 FastAPI。
- 事件实时推送（PRD Phase 4 的 WebSocket）未做；当前 30s 轮询。
