"""
Verified mega-cap earnings dates (2024–2026).

Sources documented in event_calendar_audit.md:
  - finance.yahoo.com/calendar/earnings (AMZN, AVGO, META, TSLA)
  - historicalearnings.com (MSFT)
  - wallstreethorizon.com / investor.nvidia.com (NVDA, AAPL)
  - Company IR press releases where cited

Times are US market after-close (≈ 21:00 UTC EST / 20:00 UTC EDT).
We store canonical event_time in UTC; see build script for conversion.
"""

from __future__ import annotations

# (ticker, YYYY-MM-DD, source_note)
EARNINGS_ACTUAL: list[tuple[str, str, str]] = [
    # ── 2024 ──────────────────────────────────────────────────────────────
    ("AAPL", "2024-02-01", "yahoo_finance"),
    ("AAPL", "2024-05-02", "wallstreethorizon"),
    ("AAPL", "2024-08-01", "wallstreethorizon"),
    ("AAPL", "2024-10-31", "wallstreethorizon"),
    ("AMZN", "2024-02-01", "yahoo_finance"),
    ("AMZN", "2024-04-30", "yahoo_finance"),
    ("AMZN", "2024-08-01", "yahoo_finance"),
    ("AMZN", "2024-10-31", "yahoo_finance"),
    ("AVGO", "2024-03-07", "yahoo_finance"),
    ("AVGO", "2024-06-12", "yahoo_finance"),
    ("AVGO", "2024-09-05", "yahoo_finance"),
    ("AVGO", "2024-12-12", "yahoo_finance"),
    ("META", "2024-02-01", "yahoo_finance"),
    ("META", "2024-04-24", "yahoo_finance"),
    ("META", "2024-07-31", "yahoo_finance"),
    ("META", "2024-10-30", "yahoo_finance"),
    ("MSFT", "2024-01-30", "historicalearnings"),
    ("MSFT", "2024-04-25", "historicalearnings"),
    ("MSFT", "2024-07-30", "historicalearnings"),
    ("MSFT", "2024-10-30", "historicalearnings"),
    ("NVDA", "2024-02-21", "nvidia_ir"),
    ("NVDA", "2024-05-22", "nvidia_ir"),
    ("NVDA", "2024-08-28", "nvidia_ir"),
    ("NVDA", "2024-11-20", "nvidia_ir"),
    ("TSLA", "2024-01-24", "yahoo_finance"),
    ("TSLA", "2024-04-23", "yahoo_finance"),
    ("TSLA", "2024-07-23", "yahoo_finance"),
    ("TSLA", "2024-10-23", "yahoo_finance"),
    # ── 2025 ──────────────────────────────────────────────────────────────
    ("AAPL", "2025-01-30", "wallstreethorizon"),
    ("AAPL", "2025-05-01", "wallstreethorizon"),
    ("AAPL", "2025-07-31", "wallstreethorizon"),
    ("AAPL", "2025-10-30", "wallstreethorizon"),
    ("AMZN", "2025-02-06", "yahoo_finance"),
    ("AMZN", "2025-05-01", "yahoo_finance"),
    ("AMZN", "2025-07-31", "yahoo_finance"),
    ("AMZN", "2025-10-30", "yahoo_finance"),
    ("AVGO", "2025-03-06", "yahoo_finance"),
    ("AVGO", "2025-06-05", "yahoo_finance"),
    ("AVGO", "2025-09-04", "yahoo_finance"),
    ("AVGO", "2025-12-11", "yahoo_finance"),
    ("META", "2025-01-29", "yahoo_finance"),
    ("META", "2025-04-30", "yahoo_finance"),
    ("META", "2025-07-30", "yahoo_finance"),
    ("META", "2025-10-29", "yahoo_finance"),
    ("MSFT", "2025-01-29", "historicalearnings"),
    ("MSFT", "2025-04-30", "historicalearnings"),
    ("MSFT", "2025-07-30", "microsoft_ir"),
    ("MSFT", "2025-10-29", "historicalearnings"),
    ("NVDA", "2025-02-26", "nvidia_newsroom"),
    ("NVDA", "2025-05-28", "wallstreethorizon"),
    ("NVDA", "2025-08-27", "wallstreethorizon"),
    ("NVDA", "2025-11-19", "wallstreethorizon"),
    ("TSLA", "2025-01-29", "yahoo_finance"),
    ("TSLA", "2025-04-22", "yahoo_finance"),
    ("TSLA", "2025-07-23", "yahoo_finance"),
    ("TSLA", "2025-10-22", "yahoo_finance"),
    # ── 2026 (reported or confirmed only) ─────────────────────────────────
    ("AAPL", "2026-01-29", "wallstreethorizon"),
    ("AAPL", "2026-04-30", "wallstreethorizon"),
    ("AMZN", "2026-02-05", "yahoo_finance"),
    ("AMZN", "2026-04-29", "yahoo_finance"),
    ("AVGO", "2026-03-04", "yahoo_finance"),
    ("AVGO", "2026-06-03", "yahoo_finance"),
    ("META", "2026-01-28", "yahoo_finance"),
    ("META", "2026-04-29", "yahoo_finance"),
    ("MSFT", "2026-01-28", "historicalearnings"),
    ("MSFT", "2026-04-29", "historicalearnings"),
    ("NVDA", "2026-02-25", "nvidia_ir"),
    ("NVDA", "2026-05-20", "nvidia_ir"),
    ("TSLA", "2026-01-28", "yahoo_finance"),
    ("TSLA", "2026-04-22", "yahoo_finance"),
]
