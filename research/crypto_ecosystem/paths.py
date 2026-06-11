"""Crypto Ecosystem Lead-Lag Research — audit paths (research-only)."""

from __future__ import annotations

from pathlib import Path

PM_ROOT = Path(__file__).resolve().parent.parent.parent

SHARED_ROOT = Path("/Users/libo/shared_intelligence")
HISTORY_MARKETS = SHARED_ROOT / "history" / "markets"
PM_HISTORICAL = PM_ROOT / "data" / "historical"

# research outputs — never wired to trading
RESEARCH_ROOT = SHARED_ROOT / "research" / "crypto_ecosystem_v0"
REPORTS_DIR = RESEARCH_ROOT / "reports"
BETA_REPORTS_DIR = RESEARCH_ROOT / "beta_attribution"
AUDIT_JSON = RESEARCH_ROOT / "audit_results.json"
LEAD_LAG_JSON = RESEARCH_ROOT / "lead_lag_offline.json"
BETA_JSON = RESEARCH_ROOT / "beta_attribution_results.json"

# overlap window for beta (CP00048 earliest reliable daily)
BETA_OVERLAP_START = "2022-06-15"

LONGBRIDGE_ENV = Path("/Users/libo/us-lev-etf-cta/.env")
LONGBRIDGE_VENV = Path("/Users/libo/us-lev-etf-cta/backend/.venv/bin/python")

MIN_DAILY_SAMPLES = 200
MIN_LEAD_LAG_SAMPLES = 30
