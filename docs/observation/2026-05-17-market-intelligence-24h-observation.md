# Market Intelligence Layer — 24h Observation Report

> **Template — Phase 1 Shadow Mode**
> 报告模板。所有数据字段在 24h 窗口结束后由人工/脚本填入实测值。
> **禁止预填假数据**。模板留空字段写 `<TBD>` 或 `_pending_`。

---

## 0. 元信息

| 字段 | 值 |
|---|---|
| Report ID | `<TBD>` (e.g. `obs-2026-05-18`) |
| 模板版本 | `phase1.0` |
| Orchestrator commit | `<TBD>` (e.g. `42f2cfc`) |
| `market_intelligence.py` commit | `<TBD>` |
| Phase | `1 — shadow` |
| 报告生成人 | `<TBD>` |
| 报告生成时间 | `<TBD ISO8601 +08:00>` |

---

## 1. 观察窗口

| 字段 | 值 | 说明 |
|---|---|---|
| 起始时间 | `<TBD ISO8601 +08:00>` | 第一次 step 2.5 实跑时间 |
| 结束时间 | `<TBD ISO8601 +08:00>` | 起始 + 24h |
| 总时长 | `<TBD>` 小时 | 实际跨度（应 ≥ 24h） |
| 预期扫描次数 | `<TBD>` | = 总时长 × 60 / scan_interval_min |
| 实际扫描次数 | `<TBD>` | 计算自 orchestrator 日志中 `开始新的扫描周期` 出现次数 |
| 缺失轮次 | `<TBD>` | 预期 − 实际，应 ≤ 5% |
| 中断事件 | `<TBD>` | 是否有崩溃/重启/手动停止 |

**采集命令**：

```bash
# 实际扫描轮数
grep -c "开始新的扫描周期" /var/log/polymarket/orchestrator.log

# 第一次和最后一次时间戳
grep "开始新的扫描周期" /var/log/polymarket/orchestrator.log | head -1
grep "开始新的扫描周期" /var/log/polymarket/orchestrator.log | tail -1
```

---

## 2. `market_intelligence.json` 产出状态

| 字段 | 值 | 说明 |
|---|---|---|
| 文件是否存在 | `<TBD yes/no>` | `data/market_intelligence.json` |
| 最后一次写入 | `<TBD>` | 文件内部 `generated_at` 字段 |
| 文件 schema_version | `<TBD>` | 应固定为 `phase1.0` |
| 文件 phase 字段 | `<TBD>` | 应固定为 `shadow` |
| 24h 内重写次数 | `<TBD>` | 估算自 step 2.5 success 计数 |
| 平均写入间隔（分钟） | `<TBD>` | = 1440 / 重写次数 |
| 最大写入间隔（分钟） | `<TBD>` | 应 ≤ scan_interval × 3 |

**采集命令**：

```bash
ls -la data/market_intelligence.json
python3 -c "import json; d=json.load(open('data/market_intelligence.json')); print({k: d.get(k) for k in ('generated_at','markets_total','phase','schema_version','tier_distribution')})"
```

---

## 3. `markets_processed`

| 字段 | 值 | 说明 |
|---|---|---|
| 最近一次扫描 markets_total | `<TBD>` | 文件内 `markets_total` |
| 24h 平均 markets_processed | `<TBD>` | 平均每轮成功处理的市场数 |
| 24h 最小值 | `<TBD>` | 应 ≥ markets_total × 0.8 |
| 24h 最大值 | `<TBD>` | |
| 异常轮次（< 50%）次数 | `<TBD>` | 应 = 0 |

**采集命令**：

```bash
# 若每轮日志记录了 markets_processed, 抓取所有数值
grep "市场情报层" /var/log/polymarket/orchestrator.log | grep -oE "[0-9]+ markets"
```

---

## 4. Tier 分布

记录最终一次 `tier_distribution` + 24h 内的均值/极值。

| Tier | 当前值 | 24h 均值 | 24h 最小 | 24h 最大 | 占比 |
|---|---|---|---|---|---|
| S | `<TBD>` | `<TBD>` | `<TBD>` | `<TBD>` | `<TBD>%` |
| A | `<TBD>` | `<TBD>` | `<TBD>` | `<TBD>` | `<TBD>%` |
| B | `<TBD>` | `<TBD>` | `<TBD>` | `<TBD>` | `<TBD>%` |
| C | `<TBD>` | `<TBD>` | `<TBD>` | `<TBD>` | `<TBD>%` |
| D | `<TBD>` | `<TBD>` | `<TBD>` | `<TBD>` | `<TBD>%` |

**判定标准**：
- 若 **S+A 长期 = 0**：阈值或 priors 过严 → Phase 2 前需校准
- 若 **C+D > 95%**：评分体系无区分度 → Phase 2 前需校准
- 若 **D 占比 > 30%**：上游数据质量异常或 universe 选错
- 健康分布粗参考：S 1-5% / A 5-15% / B 20-40% / C 30-50% / D ≤ 20%

**采集命令**：

```bash
python3 -c "
import json
d=json.load(open('data/market_intelligence.json'))
td=d['tier_distribution']; tot=sum(td.values())
for t,n in td.items(): print(f'{t}: {n} ({n/tot*100:.1f}%)' if tot else f'{t}: 0')
"
```

---

## 5. Category 分布

记录 `profiles[*].category` 在最终一次产出中的频数。

| Category | 频数 | 占比 |
|---|---|---|
| sports | `<TBD>` | `<TBD>%` |
| crypto | `<TBD>` | `<TBD>%` |
| politics | `<TBD>` | `<TBD>%` |
| weather | `<TBD>` | `<TBD>%` |
| finance | `<TBD>` | `<TBD>%` |
| entertainment | `<TBD>` | `<TBD>%` |
| other | `<TBD>` | `<TBD>%` |

**判定标准**：
- 若某个 category **占比 > 60%**：universe 偏科，Phase 2 资金分配前需平衡
- 若 `other` **占比 > 40%**：`classify_category()` 关键词覆盖不足

**采集命令**：

```bash
python3 -c "
import json, collections
d=json.load(open('data/market_intelligence.json'))
c=collections.Counter(p.get('category','?') for p in d['profiles'])
tot=sum(c.values())
for k,v in c.most_common(): print(f'{k}: {v} ({v/tot*100:.1f}%)')
"
```

---

## 6. Score 分布

记录 `profiles[*].tradability_score` 的统计量（0-100）。

| 统计量 | 值 |
|---|---|
| min | `<TBD>` |
| p25 | `<TBD>` |
| median (p50) | `<TBD>` |
| p75 | `<TBD>` |
| p95 | `<TBD>` |
| max | `<TBD>` |
| mean | `<TBD>` |
| stdev | `<TBD>` |

**判定标准**：
- 若 **mean 长期 < 25**：评分过保守 → 提高 priors / 放宽 clip
- 若 **mean 长期 > 75**：评分过乐观 → 收紧权重
- 若 **stdev < 5**：评分无区分度 → 检查 axes 是否退化为常数
- 健康参考：mean 35-55，stdev 10-25

**采集命令**：

```bash
python3 -c "
import json, statistics
d=json.load(open('data/market_intelligence.json'))
xs=[p.get('tradability_score',0) for p in d['profiles']]
xs.sort()
print('n=', len(xs))
print('min=', xs[0], 'max=', xs[-1])
print('mean=', round(statistics.mean(xs),2), 'stdev=', round(statistics.stdev(xs),2))
print('p25=', xs[len(xs)//4], 'p50=', xs[len(xs)//2], 'p75=', xs[3*len(xs)//4])
"
```

---

## 7. Missing Data 比例

衡量 `enrich_market()` 在 24h 内多少比例的市场走了 missing/fallback 分支。

| 字段 | 值 | 阈值 |
|---|---|---|
| 总市场样本 | `<TBD>` | |
| missing token_id | `<TBD>` (`<TBD>%`) | ≤ 5% |
| missing orderbook | `<TBD>` (`<TBD>%`) | ≤ 20% |
| missing news | `<TBD>` (`<TBD>%`) | ≤ 30% |
| missing volume/volatility | `<TBD>` (`<TBD>%`) | ≤ 10% |
| 全字段缺失 | `<TBD>` (`<TBD>%`) | = 0 |

**判定标准**：
- 任一比例 **> 阈值 × 2**：上游数据源或 CLOB 抓取不可靠 → Phase 2 前需修
- `missing orderbook > 50%`：CLOB 请求层不可用 → 阻断 Phase 2

**采集命令**：见 §8（CLOB 统计）+ profile 内的 `missing_fields` 标记字段（待 enrich_market 实际产出后定义）。

---

## 8. CLOB 请求成功 / 失败

| 字段 | 值 | 阈值 |
|---|---|---|
| 24h 总 CLOB 请求数 | `<TBD>` | |
| 成功 (HTTP 200 + valid book) | `<TBD>` (`<TBD>%`) | ≥ 80% |
| 失败 — 超时 | `<TBD>` | |
| 失败 — HTTP 4xx | `<TBD>` | |
| 失败 — HTTP 5xx | `<TBD>` | |
| 失败 — JSON parse error | `<TBD>` | |
| 失败 — 空 book | `<TBD>` | |
| 平均延迟（ms） | `<TBD>` | ≤ 500 |
| p95 延迟（ms） | `<TBD>` | ≤ 2000 |

**判定标准**：
- 成功率 **< 80%**：CLOB 抓取不可靠 → 阻断 Phase 2
- p95 延迟 **> HTTP_TIMEOUT (4000ms)**：超时配置不足或网络降级

**采集命令**：

```bash
# 需要在 fetch_orderbook 中增加结构化日志（Phase 1 暂未启用）
# 或运行专用观测脚本
grep "fetch_orderbook" /var/log/polymarket/market_intel.log | python3 -c "<聚合脚本待写>"
```

> **注**：Phase 1 当前未对 CLOB 请求做结构化埋点；本节填值可能来自手工抽样或临时加日志。

---

## 9. Cache 命中情况

`OrderbookCache` (TTL 120s, 落盘 `data/orderbook_cache.json`)。

| 字段 | 值 | 阈值 |
|---|---|---|
| 24h 总查询次数 | `<TBD>` | |
| Cache hit | `<TBD>` (`<TBD>%`) | ≥ 30% |
| Cache miss → fetch | `<TBD>` (`<TBD>%`) | |
| TTL 失效淘汰 | `<TBD>` | |
| 文件最终大小 (KB) | `<TBD>` | ≤ 5000 |
| 文件最终条目数 | `<TBD>` | |

**判定标准**：
- hit rate **< 10%**：cache 失效或 TTL 太短 → Phase 2 前调参
- 文件大小 **> 5MB**：需要加 LRU 上限

**采集命令**：

```bash
ls -la data/orderbook_cache.json
python3 -c "import json; d=json.load(open('data/orderbook_cache.json')); print('entries=', len(d))"
```

---

## 10. `safe_run` 成功 / 失败次数

| 字段 | 值 | 阈值 |
|---|---|---|
| 24h 总调用 | `<TBD>` | = 扫描轮数 |
| success=True | `<TBD>` (`<TBD>%`) | ≥ 90% |
| success=False (caught) | `<TBD>` (`<TBD>%`) | ≤ 10% |
| 主流程 except 兜底（safe_run 都没回） | `<TBD>` | = 0（这是契约红线） |

**主要失败原因 Top-N**（聚合自 `safe_run` 返回的 `error` 字段）：

| 错误 | 次数 |
|---|---|
| `<TBD>` | `<TBD>` |

**采集命令**：

```bash
# safe_run 自身失败（被 safe_run 内部 try/except 兜住，返回 success=False）
grep "市场情报层 (shadow) —" /var/log/polymarket/orchestrator.log

# safe_run 本身抛出（被 orchestrator 外层 try/except 兜住）— 红线
grep "市场情报层 (shadow) FAILED but ignored" /var/log/polymarket/orchestrator.log
```

---

## 11. step 2.5 是否阻断主流程

| 字段 | 值 | 期望 |
|---|---|---|
| 24h 内 step 2.5 出现次数 | `<TBD>` | = 扫描轮数 |
| step 2.5 之后 step 3 出现次数 | `<TBD>` | = step 2.5 次数 |
| 主流程因 step 2.5 中断 | `<TBD>` | = 0 |
| 整轮完成数（"扫描周期完成"） | `<TBD>` | = 扫描轮数 |

**判定标准**：**任何中断 = Phase 2 一票否决**。

**采集命令**：

```bash
grep -c "步骤 2.5" /var/log/polymarket/orchestrator.log
grep -c "步骤 3/" /var/log/polymarket/orchestrator.log
grep -c "扫描周期完成" /var/log/polymarket/orchestrator.log
```

---

## 12. buy / sell dry_run / success 统计

24h 内主流程的交易执行统计（不变性验证）。

| 字段 | 值 | 期望 |
|---|---|---|
| Buy 总信号 | `<TBD>` | |
| Buy dry_run | `<TBD>` | = Buy 总 |
| Buy 真实 success | `<TBD>` | = 0 |
| Buy 真实 failed | `<TBD>` | = 0 |
| Sell 总信号 | `<TBD>` | |
| Sell dry_run | `<TBD>` | = Sell 总 |
| Sell 真实 success | `<TBD>` | = 0 |
| Sell 真实 failed | `<TBD>` | = 0 |

**判定标准**：任何 `success > 0` 或 `failed > 0` = **DRY_RUN 已被破坏，Phase 1 失败**。

**采集命令**：

```bash
./venv/bin/python scripts/local_gateway_control.py status --telegram
# 看 "买入执行 total:X dry:X ✅成功:0" 和 "卖出执行 total:X dry:X ✅成功:0 failed:0"
```

---

## 13. 是否有真实下单

| 字段 | 值 | 期望 |
|---|---|---|
| `EXECUTOR_DRY_RUN` 24h 全程 = 1 | `<TBD>` | yes |
| pm-trader 真实路径调用次数 | `<TBD>` | = 0 |
| mock pm-trader 调用次数 | `<TBD>` | 任意 ≥ 0 |
| Polymarket 账户余额 24h 变化 | `<TBD>` USDC | = 0.00 |
| Polymarket 账户持仓 24h 变化 | `<TBD>` | = 0 |

**判定标准**：**任一真实下单 = Phase 1 直接判负 + 全面回滚**。

**采集命令**：

```bash
env | grep EXECUTOR_DRY_RUN
grep "mock_pm_trader" /var/log/polymarket/orchestrator.log | wc -l
# Polymarket 余额需要查 pm-trader 账户接口
```

---

## 14. 是否有 schema 变化

24h 起始与终止时刻，对比下列文件的 top-level keys：

| 文件 | 起始 keys | 终止 keys | 变化 |
|---|---|---|---|
| latest_data.json | `<TBD>` | `<TBD>` | `<yes/no>` |
| signals.json | `<TBD>` | `<TBD>` | `<yes/no>` |
| sell_signals.json | `<TBD>` | `<TBD>` | `<yes/no>` |
| positions.json | `<TBD>` | `<TBD>` | `<yes/no>` |
| intelligence_report.json | `<TBD>` | `<TBD>` | `<yes/no>` |
| market_intelligence.json | `<TBD>` | `<TBD>` | `<yes/no>` |
| orderbook_cache.json | `<TBD>` | `<TBD>` | `<yes/no>` |

**判定标准**：除 `market_intelligence.json` 和 `orderbook_cache.json` 之外，**任何下游 schema 变化 = Phase 1 失败**（说明 shadow mode 边界被破）。

**采集命令**：

```bash
python3 - <<'PY'
import json, hashlib
from pathlib import Path
base = Path("data")
for f in ["latest_data.json","signals.json","sell_signals.json","positions.json",
          "intelligence_report.json","market_intelligence.json","orderbook_cache.json"]:
    p = base / f
    if not p.exists():
        print(f, "missing"); continue
    d = json.loads(p.read_text())
    keys = sorted(d.keys()) if isinstance(d, dict) else f"<list len={len(d)}>"
    print(f, "->", keys)
PY
```

---

## 15. Phase 2 准入判定门槛

逐项打勾。**全部满足才允许进入 Phase 2 规划**；任一项失败即停留 Phase 1。

| # | 门槛 | 阈值 | 实测 | PASS? |
|---|---|---|---|---|
| G1 | step 2.5 主流程中断次数 | = 0 | `<TBD>` | `<TBD>` |
| G2 | safe_run 成功率 | ≥ 90% | `<TBD>` | `<TBD>` |
| G3 | market_intelligence.json 平均写入间隔 | ≤ scan_interval × 3 | `<TBD>` | `<TBD>` |
| G4 | tier 分布有区分度（S+A+B ≥ 5%） | ≥ 5% | `<TBD>` | `<TBD>` |
| G5 | tier 分布不退化（C+D ≤ 95%） | ≤ 95% | `<TBD>` | `<TBD>` |
| G6 | category 分布健康（单类 ≤ 60%） | ≤ 60% | `<TBD>` | `<TBD>` |
| G7 | score mean 在 [25, 75] 区间 | 25 ≤ mean ≤ 75 | `<TBD>` | `<TBD>` |
| G8 | score stdev ≥ 5 | ≥ 5 | `<TBD>` | `<TBD>` |
| G9 | CLOB 成功率 | ≥ 80% | `<TBD>` | `<TBD>` |
| G10 | cache hit rate | ≥ 10% | `<TBD>` | `<TBD>` |
| G11 | 下游 schema 零变化 | yes | `<TBD>` | `<TBD>` |
| G12 | 真实下单次数 | = 0 | `<TBD>` | `<TBD>` |
| G13 | buy/sell success = 0 | yes | `<TBD>` | `<TBD>` |
| G14 | EXECUTOR_DRY_RUN 全程 = 1 | yes | `<TBD>` | `<TBD>` |
| G15 | Polymarket 余额变化 | = 0 USDC | `<TBD>` | `<TBD>` |

**判定**：

- **PASS（≥ 14/15 且 G1/G11/G12/G13/G14/G15 全 PASS）** → 允许进入 Phase 2 规划阶段（仍需写新计划文档 + 用户授权）
- **WARN（10-13/15）** → 修复短板再观察一个 24h 窗口
- **FAIL（< 10/15 或任一安全红线 fail）** → 阻断 Phase 2，根因分析 + 整改

**安全红线（一票否决）**：G1 / G11 / G12 / G13 / G14 / G15 任一失败 → 直接 FAIL。

---

## 16. 备注 / 异常观察

`<TBD — 24h 窗口内的人工观察、异常事件、临时假设等>`

---

## 17. 结论

- 总评：`<PASS / WARN / FAIL>`
- 是否进入 Phase 2 规划：`<yes / no>`
- 下一步动作：`<TBD>`
- 报告归档：`docs/observation/<date>-market-intelligence-24h-observation.md`

---

**模板版权**：本项目内部使用。生成自 Phase 1 计划文档 §6 验收标准。
