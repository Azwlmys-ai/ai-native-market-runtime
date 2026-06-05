# SESSION_STATE — 2026-05-29

> 接续：SESSION_STATE_20260524.md（Agent P stop_loss dict bug 修复，21 周期 dry-run 验证）。
> 本次三段链路修复全部自然验证通过。

---

## 本次会话完成的事项

### 1. Agent P price fallback 修复 ✅

**问题**：`agents/agent_p.py` 在 `live_price=0.0` 时将 0 作为有效价格返回，导致 `sell_signals.json` 中 `price=null`（`price_source=current_price`），`missing_exit_price` 标记频出。

**修复**：`resolve_exit_price()` 中改用 `valid_price()` 过滤 `≤0` 的值，并按顺序 fallback 至 `last_known_price → avg_entry_price → entry_price_fallback`。

**验收**：
- `sell_signals.json` 连续多周期 4/4 有效数字 price
- `missing_exit_price = 0`
- `price_source` 分布：`market_price×1, entry_price_fallback×3`

---

### 2. paper_pnl / sell_executor close/writeback 修复 ✅

**问题**：`paper_pnl.py` 的 `_position_matches_sell()` 无法匹配 sell signal 与 paper_portfolio open position——sell signal 只有 slug（`market_id=null`），paper_portfolio 只有 numeric `market_id`（`market_slug=""`），三条匹配路全部失配，每周期生成 4 个 `sell_executor_unmatched` 幽灵 closed 条目。

**根因细节**：
- Open positions（source=agent_b）：`market_id="540844"`, `market_slug=""`, `slug=""`, `market=""`
- Sell signals（source=Agent P）：`market_id=null`, `market_slug="will-bitcoin-hit-1m-before-gta-vi-872"`
- `positions.json` 有 `market_slug ↔ market_question` 映射；paper_portfolio 有 `market_name`（等于 `market_question`）→ 可作为 bridge

**修复内容**（`paper_pnl.py`）：
1. `PaperPosition` 新增 `close_reason: str = ""` 字段（含 `from_dict` 更新）
2. `_position_matches_sell()` 新增 Try 3：`sell_slug → positions.json market_question → pos.market_name`
3. 新增 `_slug_to_market_question()` 辅助方法
4. 未在 paper_portfolio 中开仓的市场（Anaheim Ducks / Buffalo Sabres）新增 `_synthesise_position_from_snapshot()` fallback：从 positions.json 合成 PaperPosition 并立即关闭
5. `close_position()` 写入 `pos.close_reason = sell_signal.get("reason")`
6. `paper_trades.jsonl` close 记录新增 `market_name` 和 `close_reason` 字段

**验收**：
- `test_sell_close_dryrun.py` 4/4 matched，exit_price / close_reason / realized_pnl 全部非 null
- 自然落盘（2026-05-29 起）：paper_trades.jsonl 连续出现 CLOSE×4；`UNMATCHED SELL = 0`；`Paper P&L realized = $+3372.04`（修复前始终 $0.00）
- `source=sell_executor_unmatched` 新增条目 = 0

---

### 3. Agent P positions lifecycle registry 修复 ✅

**问题**：`get_portfolio()` 每周期从 pm-trader 完全覆写 `positions.json`，导致任何已处理标记被清除。4 个 pnl=-100% / live_price=0.0 的死亡市场每周期重新生成 4 条 urgent 止损信号 → sell_executor 每周期重复 CLOSE → `paper_portfolio.json` 持续积累重复 closed 条目。

**修复内容**（`agents/agent_p.py`）：
1. 新增 `load_closed_registry()` — 读 `data/positions_closed_registry.json`，返回 `{(market_slug, outcome): record}` dict
2. 新增 `update_closed_registry(sell_signals)` — 将 `priority=urgent` 的止损信号写入 registry（幂等）；写入字段：`market_slug / outcome / closed_at / exit_price / close_reason / close_source=agent_p_stop_loss / pnl`
3. `save_positions()` — 写入前合并 registry status：registry 中的持仓加 `status=closed + closed_at + exit_price + close_reason + close_source`，其余加 `status=open`
4. `analyze_positions()` — 开头过滤：跳过 `status=closed` 或 `(market_slug, outcome)` 在 registry 中的持仓，日志输出跳过数量
5. `run()` — 生成信号后调用 `update_closed_registry(sell_signals)`
6. 修正 `tests/test_smoke.py::test_agent_p_uses_pm_trader_env`（适配新 `status` 字段）
7. 新增 `tests/test_agent_p_lifecycle.py`（8 个测试用例）

**pytest 结果**：
- `tests/test_agent_p_lifecycle.py` → **8/8 passed**
- `tests/test_agent_p_stop_loss.py` → **20/20 passed**
- `tests/test_smoke.py::test_agent_p_uses_pm_trader_env` → **PASSED**
- 其余 smoke 失败项均为沙箱 `ModuleNotFoundError: openai`（预存在，与本次无关）

**自然验证（2026-05-29 11:16 — 22:01）**：
- `positions_closed_registry.json` 于 11:16:51 首次自然生成，含 4 条目标市场 + 1 条新增（jesus-christ）
- 此后连续 4 轮（20:50 / 21:13 / 21:36 / 22:01）均输出：`⏭️ 跳过 5 个已关闭持仓 → 生成 0 个卖出信号`
- `sell_signals.json` 当前为空（`total=0`）
- `sell_execution_results.json`：`total=0, dry_run=0`
- `paper_portfolio.json`：registry 写入后新增 closed = **0**，完全停止

---

## 当前系统状态（22:01:27）

### 运行状态
- launchd dry-run 每 ~15 分钟一次（`com.libo.polymarket-orchestrator-dryrun`）
- 最新完成周期：2026-05-29 22:01:27，步骤 18/18 ✅
- 无 traceback / exception / crash

### 关键指标
| 指标 | 值 |
|---|---|
| sell_signals 总数 | **0** |
| UNMATCHED SELL | **0** |
| positions_closed_registry 记录数 | **5** |
| 重复止损 | **已停止** |
| paper_portfolio open | 640 |
| paper_portfolio closed | **910（稳定）** |
| Paper P&L realized | $+3372.04 |
| ERROR / Exception / Traceback | 0 |
| Timeout（agent_b/e/f） | 常规，graceful 跳过 |

### 无 P0 / P1 功能性缺口
所有已知功能性缺口均已修复并自然验证通过。当前无阻塞项。

### 已知未修复项（非阻塞）
| 项 | 说明 |
|---|---|
| FIX_PLAN #2 key 治理 | 用户确认本轮不轮换 |
| agent_b / agent_e / agent_f 超时 | 常规 graceful 跳过，不影响周期完成 |

---

## 修改文件清单

| 文件 | 变更 |
|---|---|
| `paper_pnl.py` | close_reason 字段；Try-3 slug→market_name 匹配；合成仓位 fallback |
| `agents/agent_p.py` | closed_registry 读写；save_positions status 注解；analyze_positions 过滤 |
| `tests/test_agent_p_lifecycle.py` | 新增，8 个测试用例 |
| `tests/test_sell_close_dryrun.py` | 新增，dry-run 匹配验收脚本 |
| `tests/test_smoke.py` | 修正 test_agent_p_uses_pm_trader_env 断言 |

---

## 给下次会话的入门指引

1. 读本文件（SESSION_STATE_20260529.md）
2. 读 FIX_PLAN.md 进度跟踪表（所有 P0/P1/P2/P3 项均 ✅）
3. 系统当前无需立即处理的修复项；如需继续，可关注：
   - `positions_closed_registry.json` 是否需要定期归档/清理（P3 级别）
   - `agent_b/e/f` 超时根因深查（P2 级别，已 graceful 处理）
4. 禁止真实交易——执行层始终保持 `EXECUTOR_DRY_RUN=1`
