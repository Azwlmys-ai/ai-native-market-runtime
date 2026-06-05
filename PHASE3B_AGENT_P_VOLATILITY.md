# Phase 3b — Agent P 波动退出 + 价格历史（沙箱验证通过）

> 日期：2026-06-03
> Phase 3 第二步。选定方案：**自建每市场价格历史**（而非复用 risk_snapshot 的参考资产波动）。

---

## 1. 背景发现

调研确认：live 路径**没有每市场价格时间序列**——`latest_data.json` 是单快照（每周期覆盖），持仓是点时刻，无最高水位。agent_p 代码自己注明 trailing 是「假设当前价格就是最高点」的假实现。

`risk_snapshot.json` 虽有波动率，但按**底层参考资产**（okx:BTC-USDT / us:TSLA / commodities:gold…）算，多数预测市场（NHL/Rihanna/GTA）无映射。

→ 决定自建每市场价格历史，作为正确基础。

---

## 2. 做了什么

**价格历史持久化**（每周期一个点，滚动累积）：
- `orchestrator` 新增**步骤 1.5**（agent_a 之后）：把 `latest_data.polymarket_markets` 的 yes/no 价格 + 流动性记入历史。**无条件写**（agent_p 读的是事实源，不能被 PA_SHADOW_DB 门控）；best-effort。
- 事实源 `data/market_price_history.json`：`{market_id: [{ts, yes_price, no_price, liquidity}, …]}`，每市场滚动保留最近 60 点（体积有界）。
- 影子 `market_prices` 表：全序列（market_id+ts 去重），供分析/API。

**波动率/最高水位 helper**（`runtime/price_history.py`，纯函数）：
- `realized_volatility(series)` = 相邻价格变动的样本标准差（预测市场价在 [0,1]，用绝对变动非对数收益）。
- `should_volatility_exit(series, threshold)`：波动 ≥ 阈值返回该值，否则 None。**样本 < MIN_SAMPLES(5) 一律 None** —— 数据没攒够前绝不误触发。
- `high_water/low_water`：为后续真实 trailing 准备。

**Agent P 波动退出分支**（`analyze_positions`）：
- 在止盈/止损/获利回撤/保护利润都不触发时，查该市场近窗口波动；超阈值（默认 0.08，可被 `strategy_config.volatility_exit.threshold` 覆盖）→ 生成 `波动退出` 卖出信号（priority=medium）。
- market_slug→id 映射从 `latest_data` 取，按 id 查历史；**读 json 事实源，不依赖旁路 DB**。

---

## 3. 新增/改动

| 文件 | 改动 |
|---|---|
| `runtime/price_history.py` | 新增：load/series/realized_volatility/should_volatility_exit/high_water |
| `runtime/schema.sql` | 加 `market_prices` 表；版本 → `0.3.1-phase3b` |
| `runtime/_shadow.py` | `insert_market_prices`（去重 append） |
| `runtime/datastore.py` | `record_market_prices`（滚动 json 事实源 + 影子表） |
| `orchestrator.py` | 步骤 1.5 `_record_market_prices()`（无条件、best-effort） |
| `agents/agent_p.py` | analyze_positions 加波动退出分支（min 样本守护） |

---

## 4. 验证（沙箱，全过）

- helper：低波动市场不触发；高波动（0.19~0.24）触发；样本 <5 不触发。
- 门面：json 事实源 + 影子表双写；market_id+ts 去重；每市场滚动 cap=60。
- orchestrator 步骤：`_record_market_prices` 从合成 latest_data 写 2 市场快照（日志「💹 记录 2 个市场价格快照」）+ 影子表；多周期累积后波动 helper 正确触发。
- 真实数据 ingest：schema 自迁移 0.3.1，market_prices 表可查（ingest 不回填=0 行），无回归（signals 8 / paper_positions 22 / markets 107）。
- 全部 py_compile 通过。

> agent_p 本体含 LLM 依赖、沙箱不可导入；波动决策已抽成 `price_history` 纯函数独立验证，agent_p 分支仅薄包装 + py_compile。完整 agent_p 行为需主机验证。

---

## 5. 主机验证步骤（待跑）

```bash
cd /Users/libo/.hermes/polymarket_arbitrage
venv/bin/python3 -m pytest tests/test_smoke.py -q     # 期望仍 71（波动分支有 min 样本守护、无历史时不触发）
rm -f data/runtime.db data/runtime.db-wal data/runtime.db-shm
PA_BASE_DIR="$PWD" venv/bin/python3 -m runtime.ingest # schema → 0.3.1

# 单周期：应见「💹 记录 N 个市场价格快照」；data/market_price_history.json 生成
EXECUTOR_DRY_RUN=1 PA_SHADOW_DB=1 PM_TRADER_PATH=/tmp/mock_pm_trader.sh \
  venv/bin/python3 -c "from orchestrator import Orchestrator; Orchestrator().run_once()"
ls -la data/market_price_history.json
```

预期：smoke 71；周期出现价格快照日志；`market_price_history.json` 生成。**波动退出要累积 ≥5 周期历史才可能触发**，单轮不会出现波动退出信号（符合 min 样本守护设计）。多跑几轮后，whippy 市场可能出现 `波动退出` 卖出信号。

### 5+ 轮观察 runbook

单轮验证只证明价格快照管道已通；波动退出需要每市场至少 5 个历史点。连续观察时重点看点数递增、触发时机、去重和 dry-run 护栏。

```bash
cd /Users/libo/.hermes/polymarket_arbitrage
for i in 1 2 3 4 5 6; do
  echo "===== CYCLE $i  $(date '+%H:%M:%S') ====="
  EXECUTOR_DRY_RUN=1 PA_SHADOW_DB=1 PM_TRADER_PATH=/tmp/mock_pm_trader.sh \
    venv/bin/python3 -c "from orchestrator import Orchestrator; Orchestrator().run_once()" \
    2>&1 | grep -E "扫描周期完成|记录.*价格快照|波动退出|新增.*复盘" || true
  echo "--- 周期 $i 价格历史/信号统计 ---"
  venv/bin/python3 - <<'PY'
import json, sqlite3
h = json.load(open("data/market_price_history.json"))
pts = [len(v) for v in h.values()]
print("  覆盖市场:", len(h), " 每市场点数 min/max:", min(pts), "/", max(pts))
try:
    ss = json.load(open("data/sell_signals.json"))
    vol = [s for s in ss if "波动退出" in str(s.get("reason", ""))]
    print("  本轮 sell_signals:", len(ss), " 其中波动退出:", len(vol))
except Exception:
    print("  sell_signals: 空")
c = sqlite3.connect("data/runtime.db")
print("  影子 market_prices 行:", c.execute("SELECT COUNT(*) FROM market_prices").fetchone()[0])
c.close()
PY
done
```

判断标准：
- 每市场点数随轮次递增；滚动 cap=60，长期不会无限增长。
- 第 5 轮前不应出现波动退出；第 5 轮后才可能触发。
- 出现 `波动退出` 后应被 closed_registry 去重，不应重复膨胀。
- `market_prices` 每轮 append 约当前市场数；dry-run 护栏继续保持 `success=0`。
- 无 traceback/sqlite 错误。

现实预期：分钟级连续 dry-run 里 Polymarket 价格可能很平，波动达不到默认阈值 0.08，因此 5+ 轮也可能不触发。那表示数据平静，不等同于逻辑失败。

### 5+ 轮主机观察结果（2026-06-03）

连续 6 轮受控 dry-run 已跑完：

| 轮次 | 历史点数/市场 | market_prices 行 | sell_signals | 波动退出 | execution |
|---|---:|---:|---:|---:|---|
| 1 | 2 | 200 | 0 | 0 | success=0/dry_run=2/failed=0 |
| 2 | 3 | 300 | 0 | 0 | success=0/dry_run=0/failed=0 |
| 3 | 4 | 400 | 0 | 0 | success=0/dry_run=2/failed=0 |
| 4 | 5 | 500 | 0 | 0 | success=0/dry_run=2/failed=0 |
| 5 | 6 | 600 | 0 | 0 | success=0/dry_run=4/failed=0 |
| 6 | 7 | 700 | 0 | 0 | success=0/dry_run=2/failed=0 |

判读：
- 价格历史按轮次稳定递增，最终 100 个市场全部 7 点。
- 第 1-4 轮无波动退出符合样本守护；第 5-6 轮仍无波动退出，说明自然市场价格未达到默认阈值 0.08。
- `market_prices` 线性 append，无重复/缺口；`paper_positions` 恒定 22；`postmortems` 恒定 14。
- dry-run 护栏守住；无 traceback/sqlite/no such column/OperationalError/Exception；无残留项目进程。

结论：3b 自然多轮观察通过。触发路径未在自然数据下出现，原因是价格平静/阈值未达；不是管道或样本守护失败。

---

## 6. 局限 / 后续

- **波动退出需累积历史才生效**：前几轮 market_price_history 不足 5 点 → 不触发。这是安全设计，非缺陷。
- ~~**trailing 真实最高水位未做**~~ → 见 §7（已完成）。
- Phase 3 剩余：Agent B(hypothesis 表)、Agent M(risk grading 三级，风险最高)。

---

## 7. 真实最高水位 trailing（2026-06-04 完成，VNext 最后一条尾巴）

把原「假设当前=最高点」的简化 trailing 改成**真实回撤跟踪**：

- **新增 `agent_p._peak_pnl_from_history(pos, market_slug, ph, price_hist, slug2id)`**：按持有方向取该侧价格序列（`normalize_outcome` → YES 用 `yes_price` / NO 用 `no_price`），用 `price_history.high_water` 取真实峰值价，与入场价算出**峰值浮盈%**。数据不足（<3 点）/无 slug→id 映射/入场价非法 → 返回 None。
- **trailing 分支改判**（`agents/agent_p.py`）：
  - `peak_pnl is None`（无足够历史）→ **回退旧保守行为**（达 trigger 即止盈），不因缺数据漏退出。
  - `(峰值浮盈 − 当前浮盈) ≥ trailing_percent` → **卖出锁利**，reason 带「峰值 X%→现 Y%, 回撤 Z%」。
  - 否则（仍在峰值附近）→ **持有，让利润奔跑**（不再像旧逻辑一到 trigger 就僵硬下车）。

效果：趋势行情里多吃利润、见顶回落时及时锁利，移动止盈名副其实。

**验证**：单测真值表全过——YES 峰值 60%、NO 方向用 no_price 序列（66.7%）、回撤 2% 持有 / 8% 卖出 / 创新高持有、无数据与样本<3 回退；`tests/test_agent_p_*`（28 passed）+ smoke（71 passed）无回归。纯模拟盘加法、可回滚。
