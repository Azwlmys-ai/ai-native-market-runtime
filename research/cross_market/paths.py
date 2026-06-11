"""Cross Market Research V0 — paths (research-only, no trading DB)."""

from __future__ import annotations

from pathlib import Path

# polymarket_arbitrage root
PM_ROOT = Path(__file__).resolve().parent.parent.parent

# shared intelligence (canonical series storage)
SHARED_ROOT = Path("/Users/libo/shared_intelligence")
HISTORY_ROOT = SHARED_ROOT / "history"
MACRO_DIR = HISTORY_ROOT / "macro"
CHINA_DIR = HISTORY_ROOT / "china"
FLOWS_DIR = HISTORY_ROOT / "flows"
MARKETS_DIR = HISTORY_ROOT / "markets"

# research outputs (never wired to trading)
RESEARCH_ROOT = SHARED_ROOT / "research" / "cross_market_v0"
RESEARCH_DB = RESEARCH_ROOT / "cross_market_v0.db"
REPORTS_DIR = RESEARCH_ROOT / "reports"
REPORTS_ARCHIVE_DIR = REPORTS_DIR / "archive"
CRON_LOG_DIR = RESEARCH_ROOT / "logs"
BRIEF_STATUS_FILE = RESEARCH_ROOT / "brief_cron_status.json"
BRIEF_INDEX_FILE = RESEARCH_ROOT / "brief_index.json"
INSIGHTS_DIR = SHARED_ROOT / "insights" / "cross_market_v0"

# trading paths — brief cron must NEVER write these (health check)
TRADING_GUARD_PATHS = [
    PM_ROOT / "data" / "signals.json",
    PM_ROOT / "data" / "execution_results.json",
    PM_ROOT / "data" / "orchestrator_status.json",
    PM_ROOT / "data" / "paper_portfolio.json",
    PM_ROOT / "data" / "approved_signals.json",
    PM_ROOT / "orchestrator.lock",
]

# external read-only sources
ASHARE_DB = Path("/Users/libo/Documents/New project/data/a_share_research.sqlite")
PM_HISTORICAL = PM_ROOT / "data" / "historical"

# history extension (V0.1)
CHINA_HISTORY_START = "2020-01-01"

# default lookback for 3yr validation
VALIDATION_START = "2023-01-01"
VALIDATION_END = "2026-06-08"

LEAD_LAG_WINDOWS = (1, 3, 5, 10, 20)

# V0.1 outputs
V0_BASELINE_VALIDATION = RESEARCH_ROOT / "validation_v0_baseline.json"
V01_DELIVERABLES = RESEARCH_ROOT / "V0_1_DELIVERABLES.md"
V01_COMPARISON = RESEARCH_ROOT / "V0_vs_V0_1_comparison.md"
