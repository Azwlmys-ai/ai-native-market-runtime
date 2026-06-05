"""
market_identity — canonical market identity 解析（Phase 2a）
============================================================================
问题：各 live 文件用不同标识符指向同一市场：
  signals.json            : market_id + market_slug + market_name（全）
  paper_portfolio.json    : market_id 多数有、slug 仅 ~44%
  positions.json          : 只有 market_slug + market_question（无 market_id）
  positions_closed_registry: 只有 market_slug（无 market_id）

方案：以 Polymarket 数字 id 为 **canonical key**。维护一张持久 `markets` 维表
累积 id↔slug↔question，一旦见过即记住，解决历史 slug 无 id 的解析。

解析顺序（resolve）：
  1. 记录自带 market_id（非空）→ 直接用，并把 slug/question 回填进 markets
  2. 否则 slug → markets 查 id
  3. 否则 question → markets 查 id
  4. 都不中 → 临时键 `slug:<slug>`（可被后续 upgrade 合并）；连 slug 都没有则 `q:<hash>`

所有函数接收 sqlite3 连接（复用 _shadow 的连接），不自管库。
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from typing import Any, Optional


def _norm(v: Any) -> str:
    return "" if v is None else str(v).strip()


def seed_market(c: sqlite3.Connection, market_id: str, slug: str = "",
                question: str = "", raw: Any = None) -> None:
    """把一条权威 id↔slug↔question 映射 upsert 进 markets（last_seen 刷新，缺字段用 COALESCE 保留已有）。"""
    mid = _norm(market_id)
    if not mid:
        return
    c.execute(
        """INSERT INTO markets (market_id, slug, question, raw_json)
           VALUES (?,?,?,?)
           ON CONFLICT(market_id) DO UPDATE SET
             slug=COALESCE(NULLIF(excluded.slug,''), markets.slug),
             question=COALESCE(NULLIF(excluded.question,''), markets.question),
             last_seen=strftime('%Y-%m-%dT%H:%M:%fZ','now'),
             raw_json=COALESCE(excluded.raw_json, markets.raw_json)""",
        (mid, _norm(slug), _norm(question),
         json.dumps(raw, ensure_ascii=False) if raw is not None else None),
    )


def seed_from_latest_data(c: sqlite3.Connection, latest_data: dict) -> int:
    """从 latest_data.polymarket_markets 批量播种（权威来源，每周期可刷新）。"""
    n = 0
    for m in (latest_data or {}).get("polymarket_markets", []) or []:
        if isinstance(m, dict) and m.get("id"):
            seed_market(c, m.get("id"), m.get("slug", ""), m.get("question", ""), raw=m)
            n += 1
    return n


def harvest(c: sqlite3.Connection, record: dict) -> None:
    """从任何同时含 id 与 slug/question 的业务记录里收集映射。"""
    if not isinstance(record, dict):
        return
    mid = _norm(record.get("market_id"))
    if not mid:
        return
    slug = _norm(record.get("market_slug") or record.get("slug"))
    q = _norm(record.get("market_question") or record.get("question") or record.get("market_name"))
    if slug or q:
        seed_market(c, mid, slug, q)


def resolve(c: sqlite3.Connection, record: dict) -> str:
    """返回 canonical_market_id。能拿到权威数字 id 就用 id；否则退化为 slug:<slug> 临时键。"""
    mid = _norm(record.get("market_id"))
    if mid:
        harvest(c, record)          # 顺带把映射记住
        return mid

    slug = _norm(record.get("market_slug") or record.get("slug"))
    if slug:
        row = c.execute(
            "SELECT market_id FROM markets WHERE slug=? ORDER BY last_seen DESC LIMIT 1", (slug,)
        ).fetchone()
        if row and row[0]:
            return str(row[0])

    q = _norm(record.get("market_question") or record.get("question") or record.get("market_name"))
    if q:
        row = c.execute(
            "SELECT market_id FROM markets WHERE question=? ORDER BY last_seen DESC LIMIT 1", (q,)
        ).fetchone()
        if row and row[0]:
            return str(row[0])

    # 临时键：保证有稳定主键不丢，待映射出现后可 upgrade 合并
    if slug:
        return f"slug:{slug}"
    if q:
        return "q:" + hashlib.sha1(q.encode("utf-8")).hexdigest()[:12]
    return "unknown"
