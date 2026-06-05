# Phase 2a 尾巴 — 临时键 reconcile 自动化（沙箱验证通过）

> 日期：2026-06-04
> 对应 VNEXT 里程碑 §6 尾巴 #3：**临时键 reconcile 自动化**（`upgrade_provisional_positions` 已有，接入周期或定时）。
> 与 3c-2 强相关：reconcile 把临时键/裸 slug 持仓合并到权威数字 canonical，减少重复、并为失败条件对照扩大可 join 的覆盖面。

---

## 1. 背景 / 落差

Phase 2a 引入 canonical 市场身份后，`paper_positions` 的 `canonical_market_id` 仍有三类非权威形态：
- `slug:<x>` 临时键（resolve 拿不到数字 id 时的兜底）。
- **裸 slug**（如 `will-jesus-christ-return-before-gta-vi-665`）——因为 `market_identity.resolve` 对非空 `market_id` 字段**原样信任**，老仓的 market_id 本就是 slug 时直接落为裸 slug。
- `q:<hash>` / `unknown`。

问题：
1. 既有 `upgrade_provisional_positions` **只抓 `slug:%`**，catch 不到裸 slug → 大量可合并持仓没合并（实测 22 行里 10 数字 / 1 `slug:` / 11 裸 slug）。
2. reconcile **从未被自动调用**：`ingest.reconcile()` 只是诊断打印，不调 upgrade；orchestrator 周期末也没接。只有 FastAPI `/admin/reconcile-provisional` 手动触发。

---

## 2. 做了什么

### A. 拓宽 `upgrade_provisional_positions`（`runtime/_shadow.py`）

- 选取范围从 `canonical_market_id LIKE 'slug:%'` 拓宽到 **`NOT GLOB '[0-9]*'`**（所有非纯数字 canonical：slug:、裸 slug、q:、unknown）。
- 新增 `_numeric_market_id_for(slugs, question)`：按 `market_slug` / 去 `slug:` 前缀的 canonical / canonical 本身（精确 slug）→ 退回 `market_name`（精确 question）在 markets 找 **纯数字** id（`market_id GLOB '[0-9]*'` + Python `isdigit()` 双重守护）。**真·slug-only 市场**（markets.market_id=slug 本身，如 anaheim ducks）解析为 None，**不会被误升级**。
- **防污染合并**（关键修正）：注入数字 id 后，先看权威数字行是否已存在：
  - **已存在且已平仓** → provisional 是重复，**直接删**，不 upsert 它（避免 incoming 的 `0/空` 经 `_upsert_position` 的 `COALESCE(excluded, existing)` 覆盖权威平仓 pnl/exit —— 该 COALESCE 偏向 incoming，实测会把真实亏损 `-1.0` 冲成 `0` → 复盘 verdict 被错判）。
  - **不存在 或 仍 open** → re-key 合并（让 provisional 的平仓数据正常上位），删旧行。
- 幂等：没有可升级的（含已是数字 canonical）返回 0。

### B. 接入自动化（`runtime/ingest.py`）

- 在 `ingest.backfill()` **末尾**调 `upgrade_provisional_positions()`（此时 markets 维表 + positions 都已就位），记 `stats["positions_reconciled"]`。best-effort，失败不影响回填。
- **一处接入覆盖三条路径**：orchestrator 周期末（调 `backfill()` → reconcile 在 `postmortem.generate()` **之前**，故复盘能 join 到升级后的数字 canonical）、standalone `python -m runtime.ingest` 重建、FastAPI `/admin/reconcile-provisional` 手动端点（本就直调）。

---

## 3. 验证（隔离临时库，非破坏性；全过）

`PA_BASE_DIR=$PWD`（只读真实 json）+ `PA_DB_PATH=/tmp`（临时库），真实 `data/runtime.db` 不动：

| 项 | 结果 |
|---|---|
| reconcile 前持仓形态 | 总 22（数字 10 / `slug:` 1 / 裸 slug 11） |
| 升级行数 | **4**（2 合并进已有权威行 → 总数降；2 re-key 成新数字行） |
| reconcile 后 | 总 **20**（数字 12 / `slug:` 1 / 裸 slug 7）—— 去重见效 |
| 幂等（再跑） | **0** ✅ |
| **防污染** | jesus 540819 `pnl=-1.0 closed` **保住**（修正前会被裸 slug 的 0.0 冲掉）；复盘 verdict `refuted` 保住、**无回归** ✅ |
| 真·slug-only 市场 | 7 裸 slug + 1 `slug:` 是 markets 无数字 id 的（anaheim 等 / bitcoin slug 不匹配），**正确不动** |
| smoke | **71 passed**；`py_compile` 通过 |

> 剩余未升级的临时键，是 markets 维表确实没有其数字映射（slug-only 市场或 slug/question 都对不上）——非缺陷，待 latest_data 出现该市场数字 id 后下一轮自动升级。

---

## 4. 主机收尾（让真库应用 reconcile + 3c-2 verdict）

reconcile 与 3c-2 都在 `ingest.backfill()`/复盘引擎里自动跑；要让**存量**真库即时应用（沙箱 `rm` 无权限未原地重建）：

```bash
cd /Users/libo/.hermes/polymarket_arbitrage
rm -f data/runtime.db data/runtime.db-wal data/runtime.db-shm
# 可选：清掉旧复盘事实源避免 jsonl 累积无 verdict 的旧行
#   cp data/postmortems.jsonl data/postmortems.jsonl.bak && : > data/postmortems.jsonl
PA_BASE_DIR="$PWD" PA_SHADOW_DB=1 venv/bin/python3 -m runtime.ingest      # 回填 + 自动 reconcile
PA_BASE_DIR="$PWD" PA_SHADOW_DB=1 venv/bin/python3 -m runtime.postmortem  # 重生带 verdict 的复盘
```

预期：`paper_positions` 22→20（去重）；dashboard `/positions` 显示去重后 canonical；`/research` 复盘卡片对照覆盖随数字 canonical 增多而扩大。日常 orchestrator 周期末自动跑，无需手动。

---

## 5. 局限 / 后续

- 升级依赖 markets 维表有该市场的 **精确 slug 或精确 question → 数字 id** 映射；slug 带后缀差异（如 `...-872` vs `...-872-424`）且 question 也不一致时不升级。后续可加模糊/规范化 slug 匹配，但需防误并。
- 本轮 reconcile 在该数据集主要体现为**去重**（22→20）；3c-2 覆盖扩大是数据相关的副产物（可升级的多是已被覆盖的数字行的重复）。新市场数字 canonical 增多后覆盖自然扩大。
