# Historical Replay Learning — Design (Phase 3)

> **Project:** Polymarket_arbitrage  
> **Shared layer:** `/Users/libo/shared_intelligence`  
> **Mode:** Learning Only — no changes to agents/executors/risk/strategy

---

## 1. Goal

Upgrade knowledge flow:

```
Observation → Hypothesis → Insight
```

by consuming:

- ETF historical price reactions (QQQ, SOXL, SOXS, TQQQ)
- OKX/crypto historical reactions (BTC, ETH)
- Macro + earnings event calendars (2022–2026)
- Theme mapping (AI, RATES, INFLATION, …)

**Not** single-event narratives (“AVGO earnings caused SOXL down”), but **theme-level statistics**:

> AI + Rates themes | sample 43 | SOXL avg -4.8% | QQQ -1.9% | BTC -0.7% | confidence 83%

---

## 2. Directory Layout

```
shared_intelligence/history/
├── macro/          # NFP, CPI, PPI, FOMC (2022–2026)
├── earnings/       # NVDA, AVGO, TSLA, AAPL, MSFT, META, AMZN
├── markets/        # daily bars + precomputed replay slices
├── themes/         # manifest.json
└── replay_dataset.jsonl

shared_intelligence/learning/
├── theme_patterns.json
├── hypotheses.json
├── insights.json
├── observations.json
└── learning_dashboard_summary.md
```

---

## 3. Pipeline

| Step | Script | Output |
|------|--------|--------|
| 1–2 | `research/build_history_datasets.py` | `history/macro`, `earnings`, `markets` |
| 3 | `analytics/historical_replay_joiner.py` | `replay_dataset.jsonl` |
| 4 | `analytics/theme_learning_engine.py` | `learning/theme_patterns.json` |
| 5 | `analytics/cross_market_theme_report.py` | `insights/cross_market_theme_report.md` |
| 6 | `analytics/hypothesis_generator.py` | `learning/hypotheses.json` + `hypotheses/HYP_*.md` |
| 7 | `analytics/insight_promoter.py` | `learning/insights.json` + `insights/INSIGHT_*.md` |
| 8 | `analytics/learning_dashboard.py` | dashboard mirror + summary |

**One-shot:**

```bash
cd /Users/libo/.hermes/polymarket_arbitrage
# 用项目 venv（含 certifi，修复 macOS SSL 证书问题）
PYTHONPATH=. ./venv/bin/python research/run_historical_replay_pipeline.py
```

若 ETF 仍为 0 bars，日志会打印 `[warn] Yahoo fetch failed`；可检查网络/代理，或依赖 Stooq 兜底。

---

## 4. Data Sources

| Layer | Source | Notes |
|-------|--------|-------|
| Macro dates | `build_event_calendars` rules + 2022–2023 FOMC | NFP/CPI/PPI release proxies |
| Macro actuals | Sparse curated rows in builder | Extend via FRED/BLS ingest later |
| Earnings dates | `earnings_actual_calendar.json` + 2022–23 anchors | EPS fields nullable until enriched |
| ETF/Crypto prices | Yahoo chart API + certifi SSL | macOS 需 `certifi`；ETF 失败时 Stooq 兜底；crypto 可回退本地 OKX |
| Polymarket | `PM_PROXY_*` in joiner | Synthetic until historical PM tape wired |

---

## 5. Promotion Rules

| Stage | Gate |
|-------|------|
| **Hypothesis** | Theme×asset replay sample ≥ 10 |
| **Insight** | Sample ≥ 30 AND \|mean−baseline\| significant (lightweight t-style gate) |

Trading systems are **not** allowed to read these artifacts without a future explicit promotion review.

---

## 6. Forbidden (this phase)

- Event filter / blocking / override in orchestrator
- Changes to `agents/`, `executors/`, `risk/`, `strategy/`
- Strategy optimization or position sizing from replay outputs

---

## 7. Future Enrichment

1. FRED/BLS macro actual/expected/surprise full history
2. Earnings EPS actual/expected from yfinance or IR feeds
3. Real Polymarket historical probability tape (2022–2026)
4. Formal statistical tests (Holm-Bonferroni across themes)
