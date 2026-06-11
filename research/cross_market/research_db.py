"""Research-only SQLite — never touches trading DB."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

from .lead_lag import LeadLagResult
from .paths import RESEARCH_DB, RESEARCH_ROOT


def _schema_path() -> Path:
    return Path(__file__).parent / "schema.sql"


def get_connection() -> sqlite3.Connection:
    RESEARCH_ROOT.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(RESEARCH_DB)
    conn.row_factory = sqlite3.Row
    conn.executescript(_schema_path().read_text(encoding="utf-8"))
    return conn


def upsert_returns(conn: sqlite3.Connection, series_key: str, category: str, rets: dict[str, float], source: str) -> None:
    if not rets:
        return
    dates = sorted(rets.keys())
    conn.execute(
        """INSERT OR REPLACE INTO series_meta (series_key, category, source, start_date, end_date, row_count, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (series_key, category, source, dates[0], dates[-1], len(rets), datetime.now().isoformat()),
    )
    conn.executemany(
        "INSERT OR REPLACE INTO daily_returns (series_key, trade_date, daily_return) VALUES (?, ?, ?)",
        [(series_key, d, rets[d]) for d in dates],
    )


def upsert_factor_returns(conn: sqlite3.Connection, factor_id: str, rets: dict[str, float]) -> None:
    if not rets:
        return
    conn.executemany(
        "INSERT OR REPLACE INTO factor_returns (factor_id, trade_date, daily_return) VALUES (?, ?, ?)",
        [(factor_id, d, rets[d]) for d in rets],
    )


def save_lead_lag_results(conn: sqlite3.Connection, results: list[LeadLagResult]) -> None:
    now = datetime.now().isoformat()
    conn.execute("DELETE FROM lead_lag_results")
    conn.executemany(
        """INSERT INTO lead_lag_results
           (driver, target, lag_days, window_days, sample_count, hit_rate, avg_return,
            avg_drawdown, correlation, direction, computed_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        [
            (r.driver, r.target, r.lag_days, r.window_days, r.sample_count,
             r.hit_rate, r.avg_return, r.avg_drawdown, r.correlation, r.direction, now)
            for r in results
        ],
    )


def save_question_verdict(conn: sqlite3.Connection, qid: str, question: str, driver: str, target: str,
                        verdict: str, evidence: dict[str, Any]) -> None:
    conn.execute(
        """INSERT OR REPLACE INTO research_questions
           (question_id, question, driver, target, verdict, evidence_json, computed_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (qid, question, driver, target, verdict, json.dumps(evidence, ensure_ascii=False), datetime.now().isoformat()),
    )
