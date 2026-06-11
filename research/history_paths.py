"""Shared paths for Historical Replay Learning (Phase 3). Learning-only."""

from __future__ import annotations

from pathlib import Path

SHARED_ROOT = Path("/Users/libo/shared_intelligence")
HISTORY_ROOT = SHARED_ROOT / "history"
LEARNING_ROOT = SHARED_ROOT / "learning"
INSIGHTS_ROOT = SHARED_ROOT / "insights"
HYPOTHESES_ROOT = SHARED_ROOT / "hypotheses"
OBSERVATIONS_ROOT = SHARED_ROOT / "observations"

MACRO_DIR = HISTORY_ROOT / "macro"
EARNINGS_DIR = HISTORY_ROOT / "earnings"
MARKETS_DIR = HISTORY_ROOT / "markets"
THEMES_DIR = HISTORY_ROOT / "themes"

REPLAY_DATASET = HISTORY_ROOT / "replay_dataset.jsonl"
THEME_PATTERNS = LEARNING_ROOT / "theme_patterns.json"
HYPOTHESES_JSON = LEARNING_ROOT / "hypotheses.json"
INSIGHTS_JSON = LEARNING_ROOT / "insights.json"
OBSERVATIONS_JSON = LEARNING_ROOT / "observations.json"
DASHBOARD_SUMMARY = LEARNING_ROOT / "learning_dashboard_summary.md"
CROSS_MARKET_REPORT = INSIGHTS_ROOT / "cross_market_theme_report.md"

MARKET_SYMBOLS = ("QQQ", "SOXL", "SOXS", "TQQQ", "BTC", "ETH")
RETURN_HORIZONS = (1, 3, 5, 10)
