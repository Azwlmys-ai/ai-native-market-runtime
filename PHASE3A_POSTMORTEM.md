# Phase 3a — Agent G → Postmortem Engine（沙箱验证通过）

> 日期：2026-06-02
> Phase 3（Agent B/M/P/G API化）的第一步，选 G(复盘)作起点：**纯加法、低风险**——不改审批/执行/学习行为，只新增逐笔结构化复盘产物。
> 关键依赖：2a 的 canonical 身份让【已平仓持仓】能 join 回【原始信号】，从而对照 hypothesis vs 实际结果。

---

## 1. 做了什么

逐笔已平仓持仓 → 结构化复盘，落 `data/postmortems.jsonl`（事实源）+ 影子 `postmortems` 表。

PRD 复盘字段全部落地：

| 字段 | 来源（确定性） |
|---|---|
| hypothesis | 原始信号 reason + logic_chain + 方向/置信 |
| expected_edge | signal.expected_value |
| confidence | signal.confidence |
| actual_result | realized_pnl + outcome(win/loss/flat) |
| failure_reason | 规则叙述（亏损/盈利了结 + close_reason）；LLM 路径增强 |
| liquidity_issue | risk_notes 含 liquidity 或 price_source∈(missing,entry_price_fallback) |
| timing_issue | close_reason 含 时间/超时/timeout |
| model_issue | 置信≥70 却亏损 → 模型高估 |

两条路径：
- **确定性 fallback**（默认，沙箱可验）：纯规则算全部字段，不依赖 LLM。
- **LLM 增强**（use_llm，主机）：仅对 failure_reason 叙述增强，其余不变。

---

## 2. 新增/改动

| 文件 | 改动 |
|---|---|
| `runtime/postmortem.py` | 新增：`build_postmortem()` 确定性构建 + `generate()` 逐笔（幂等，只对未复盘的已平仓） |
| `runtime/schema.sql` | 加 `postmortems` 表；schema 版本 → `0.3.0-phase3a` |
| `runtime/_shadow.py` | `upsert_postmortem` / `query_postmortems` / `closed_positions_without_postmortem` / `latest_signal_for`（join 原始信号） |
| `runtime/datastore.py` | `append_postmortem`（jsonl 事实源 + shadow） |
| `runtime/api.py` | `GET /postmortems`（可按 outcome 过滤）+ `POST /admin/generate-postmortems` |
| `orchestrator.py` | 周期末 shadow 钩子内加一行：确定性逐笔复盘（best-effort，`PA_SHADOW_DB=1` 时；不改交易行为） |

**未改 agent_g 核心、未改审批/执行**。复盘是 DB 派生 + jsonl 加法产物。

---

## 3. 验证

沙箱（TestClient + 构造数据）：
- 确定性归因正确：高置信(85)亏损 → `model_issue=1`；risk_notes 含 liquidity → `liquidity_issue=1`；hypothesis/expected_edge(71.7)/confidence(85) 从信号 join。
- 双写 jsonl + DB；幂等（再 generate=0）；`GET /postmortems` + outcome 过滤 + `POST /admin/generate-postmortems` 正常。

真实数据：14 个已平仓 → 14 笔复盘（6 flat / 7 loss / 1 win），liquidity_issue=3、model_issue=1；schema 自迁移到 0.3.0-phase3a。

**附带发现（数据质量）**：有一笔 realized_pnl=+274 的盈利，close_reason 却是「止损 -100%」——源数据自相矛盾。引擎按 pnl 正确判 win，确定性 failure_reason 照抄了矛盾文案（LLM 路径会调和）。这正是复盘引擎该暴露的问题，非引擎 bug；后续可作为一个数据清洗线索。

---

## 4. 主机验证步骤（待跑）

```bash
cd /Users/libo/.hermes/polymarket_arbitrage
venv/bin/python3 -m pytest tests/test_smoke.py -q     # 期望仍 71（未改 live 写者/审批/执行）
rm -f data/runtime.db data/runtime.db-wal data/runtime.db-shm   # 升级 schema，干净重建
PA_BASE_DIR="$PWD" venv/bin/python3 -m runtime.ingest

# 受控单周期：应看到「🧾 新增 N 笔复盘」
EXECUTOR_DRY_RUN=1 PA_SHADOW_DB=1 PM_TRADER_PATH=/tmp/mock_pm_trader.sh \
  venv/bin/python3 -c "from orchestrator import Orchestrator; Orchestrator().run_once()"

# 看复盘（API 或 jsonl）
PA_SHADOW_DB=1 PA_BASE_DIR="$PWD" venv/bin/python3 -m uvicorn runtime.api:app --port 8848 &
curl -s 'localhost:8848/postmortems?limit=3' | python3 -m json.tool | head -40
# 可选 LLM 增强：curl -s -X POST 'localhost:8848/admin/generate-postmortems?use_llm=true'
```

预期：smoke 71；周期日志出现复盘行；`data/postmortems.jsonl` 生成；GET /postmortems 返回结构化复盘。

---

## 5. 局限 / 后续

- 默认自动路径是**确定性**（无 LLM），保证稳定；LLM 叙述增强需显式触发（API `use_llm=true` 或 `PA_POSTMORTEM_LLM=1`），主机验证。
- `hypotheses` 表仍缓延（属 Agent B → Research，Phase 3b）；当前 hypothesis 以文本存在 postmortem 内。
- Phase 3 后续：Agent B(hypothesis)、Agent M(risk grading 三级)、Agent P(波动退出)。M 改动会动审批/交易行为，风险最高，建议放后面并重点主机验证。
