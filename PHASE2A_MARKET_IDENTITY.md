# Phase 2a — Canonical Market Identity（沙箱验证通过）

> 日期：2026-06-02
> 目标：给持仓/信号一个稳定统一的市场主键，根治"同一市场被不同标识符引用"导致的状态分裂。
> 定位：**纯影子库侧改动**——本轮未改任何 live json 写入，只改 `runtime/` 影子层。dry-run / live 流水线零影响。
> 这是 Phase 2b（paper_pnl API化）的前置：API 的 open/close/positions 都按市场身份做键。

---

## 1. 问题（实测覆盖率）

各 live 文件用不同标识符指向同一市场：

| 文件 | market_id | market_slug | question | 说明 |
|---|---|---|---|---|
| `signals.json` | 8/8 | 8/8 | name 8/8 | 全 |
| `paper_portfolio.json` | 2129/2143 | 941/2143 | 951/2143 | id 多、slug 仅 ~44% |
| `positions.json` | 0 | 有 | market_question | **无 market_id** |
| `positions_closed_registry.json` | 0/7 | 7/7 | 0 | **只有 slug** |
| `latest_data.polymarket_markets` | 100/100 | 100/100 | 100/100 | **权威交叉源** |

后果：position_uid 用 `slug or id` 拼，registry（纯 slug）与 portfolio（纯 id）即使是同一市场也算两个持仓 → 状态分裂、重复行。

---

## 2. 方案

**canonical key = Polymarket 数字 `id`（market_id）。**

持久维表 `markets(market_id PK, slug, question, first_seen, last_seen, raw_json)` 累积 id↔slug↔question 映射，**一旦见过即记住**，解决历史 slug 无 id。

播种来源（按权威性）：
1. 每周期 `latest_data.polymarket_markets`（权威，当前 100 市场）
2. 任何同时含 id 与 slug/question 的业务记录（signals / portfolio）—— 次级，扩展到历史市场

**解析顺序** `market_identity.resolve(conn, record)`：
1. 记录自带 `market_id` → 直接用（并 harvest 映射）
2. 否则 `slug` → markets 查 id（`ORDER BY last_seen DESC`，权威 latest_data 最后播种故胜出）
3. 否则 `question` → markets 查 id
4. 都不中 → 临时键 `slug:<slug>`（保证主键不丢，待映射出现可 upgrade 合并）；无 slug 则 `q:<hash>`；都无则 `unknown`

`position_uid = uid(canonical_market_id, direction)`，paper_positions 新增 `canonical_market_id` 列。

脏数据处理：实测存在**同一 slug 被不同 market_id 引用**，故 `markets.slug` 用非唯一索引 + resolve 取 `last_seen` 最新（权威源胜）。

---

## 3. 新增/改动（全在 runtime/）

| 文件 | 改动 |
|---|---|
| `runtime/market_identity.py` | 新增：seed_market / seed_from_latest_data / harvest / resolve |
| `runtime/schema.sql` | 加 `markets` 表 + `paper_positions.canonical_market_id` 列；schema 版本 → `0.2.0-phase2a` |
| `runtime/_shadow.py` | 连接初始化从 latest_data 播种 markets；`_upsert_position` 用 canonical 算 uid 并落列 |
| `runtime/ingest.py` | backfill 先 harvest 业务记录、后播种权威 latest_data；对账加 markets/canonical 分布 |

---

## 4. 验证结果（真实数据）

- **持仓 29 → 22**：canonical 身份把纯 slug 的 registry 行与 id-keyed 的 portfolio 行合并。
- **canonical 解析分布**：权威 id = 20，临时键(slug:/q:) = 1（历史市场 `will-bitcoin-...-872`，未在交叉表，待再次出现即 upgrade），无标识 = 1。
- **markets 维表**：107 行（latest_data 100 + harvest 扩展）。
- **幂等**：复跑 paper_positions 仍 22、markets 仍 107。
- **合并定向验证**：构造 slug-only 记录 + id 记录（交叉表已知 slug→id），落**同一持仓行**（canonical=540817），closed 生命周期护栏保住。
- 全部 `py_compile` 通过。

---

## 5. 局限 / 后续

- 临时键 `slug:<X>` 的 upgrade 合并目前是"下次见到映射时新写入会用 id"，**已存在的临时键行不会自动迁移**——需要一个 reconcile 作业把 `slug:X` 行重keyed 到 id（Phase 2b 或单独小任务）。影子库可重建，影响可控。
- markets 维表尚未接入 live 写路径（仅影子/ingest）；Phase 2b API 化时 `/markets` 可直接读它。

---

## 6. 下一步：Phase 2b — paper_pnl API 化

身份已稳。Phase 2b 起 FastAPI：`POST /paper/open`、`POST /paper/close`、`GET /paper/positions`、`GET /paper/trades`，读写经 datastore/DB，positions 按 `canonical_market_id` 返回。attribution（exit_price/realized_pnl/close_reason）已在 paper_positions 齐备。
