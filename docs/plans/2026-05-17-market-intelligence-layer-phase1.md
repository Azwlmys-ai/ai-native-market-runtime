# Market Intelligence Layer — Phase 1 (Shadow Mode) Implementation Plan

> **For Hermes:** Use `subagent-driven-development` skill to implement task-by-task.
> **MUST stay DRY_RUN.** No executor / capital / stoploss main-flow changes in this phase.

---

## 1. Goal

Add a new shadow-mode module `market_intelligence.py` that:

- Reads `data/latest_data.json` (no new external API calls required for Phase 1 except the optional Polymarket CLOB/trades enrichment, see Task 6).
- Produces `data/market_intelligence.json` with per-market: `category`, `tier`, 6-axis scores, `tradability_score`, **shadow** `capital_weight`, **shadow** `max_position_size`, **shadow** `stoploss_profile`.
- Maintains `data/orderbook_cache.json` (TTL 120s) for optional CLOB enrichment.
- **Nothing consumes these fields in Phase 1.** Capital adapter, signal executor, Agent M, Agent P, sell executor are NOT modified.

Hook into orchestrator as a single new step `2.5/19` wrapped by the existing try/except, with full failure tolerance.

---

## 2. Non-goals

- ❌ Modify `capital_adapter.py` / `capital_allocation.json` schema
- ❌ Modify `signal_executor.py` (both copies)
- ❌ Modify `agent_m.py` / `review_results.json` schema
- ❌ Modify `agent_p_stop_loss.py` / stoploss thresholds
- ❌ Modify `_consolidate_signals_for_review` (no signal enrichment)
- ❌ Touch real trading / disable DRY_RUN
- ❌ Touch `opc`, `look`, `polymarket_okx`
- ❌ Final tier weights / thresholds (current values are conservative observation defaults)

---

## 3. Files Added

| Path | Purpose |
|---|---|
| `market_intelligence.py` | Main module (single file, runnable standalone) |
| `tests/test_market_intelligence.py` | Pytest unit + integration tests |
| `data/market_intelligence.json` | Runtime output (gitignored if not already) |
| `data/orderbook_cache.json` | Runtime cache (gitignored if not already) |
| `docs/plans/2026-05-17-market-intelligence-layer-phase1.md` | This plan |

## 4. Files Modified

| Path | Change | LOC delta |
|---|---|---|
| `orchestrator.py` | Insert single step `2.5/19` calling `_run_module("market_intelligence")` wrapped in try/except; rename step counts `2/16→2/19`, etc. **Only step-count strings + 4 new lines.** | +6, −0 |

No other files touched.

---

## 5. Data Schemas

### 5.1 `data/market_intelligence.json`

```json
{
  "generated_at": "2026-05-17T20:30:00.123456",
  "schema_version": "phase1.0",
  "source_timestamp": "<latest_data.json.timestamp>",
  "market_count": 100,
  "tier_distribution": {"S": 0, "A": 0, "B": 0, "C": 0, "D": 0},
  "category_distribution": {"crypto": 0, "politics_macro": 0, "...": 0},
  "markets": {
    "<slug>": {
      "market_id": "540817",
      "slug": "new-rhianna-album-before-gta-vi-926",
      "question": "New Rihanna Album before GTA VI?",
      "category": "entertainment",
      "tier": "D",
      "scores": {
        "liquidity_score": 30,
        "spread_score": 30,
        "activity_score": 30,
        "volatility_score": 30,
        "news_heat_score": 0,
        "time_score": 50
      },
      "tradability_score": 28.5,
      "shadow": {
        "capital_weight": 0.20,
        "max_position_size": 0.02,
        "stoploss_profile": "explore"
      },
      "data_quality": {
        "has_orderbook": false,
        "has_trades": false,
        "fallback_fields": ["spread_score", "activity_score", "volatility_score"]
      }
    }
  },
  "run_stats": {
    "duration_ms": 0,
    "cache_hits": 0,
    "cache_misses": 0,
    "api_errors": 0
  }
}
```

### 5.2 `data/orderbook_cache.json`

```json
{
  "<slug>": {
    "fetched_at": "2026-05-17T20:30:00.123456",
    "ttl_seconds": 120,
    "spread": 0.02,
    "depth_1pct_usd": 1500.0,
    "depth_5pct_usd": 7800.0,
    "last_trade_ts": "2026-05-17T20:28:11Z",
    "trade_count_1h": 12
  }
}
```

### 5.3 Constants (frozen Phase 1 defaults)

```python
TIER_PRIORS = {
    "crypto":         ({"S","A","B","C"}, "A"),
    "politics_macro": ({"A","B","C"},     "A"),
    "politics_other": ({"B","C","D"},     "C"),
    "breaking_news":  ({"B","C"},         "B"),
    "ai_tech":        ({"B","C"},         "B"),
    "weather":        ({"B","C"},         "C"),
    "sports":         ({"C","D"},         "C"),
    "entertainment":  ({"C","D"},         "D"),
    "other":          ({"C","D"},         "D"),
}
TIER_S_CRYPTO_SLUG_TOKENS = ("btc","bitcoin","eth","ethereum","sol","solana","xrp","ripple")

TIER_DEFAULTS = {
    "S": {"capital_weight": 1.50, "max_position_size": 0.15, "stoploss_profile": "strict"},
    "A": {"capital_weight": 1.20, "max_position_size": 0.12, "stoploss_profile": "standard"},
    "B": {"capital_weight": 1.00, "max_position_size": 0.10, "stoploss_profile": "standard"},
    "C": {"capital_weight": 0.50, "max_position_size": 0.05, "stoploss_profile": "loose"},
    "D": {"capital_weight": 0.20, "max_position_size": 0.02, "stoploss_profile": "explore"},
}

WEIGHTS = {"liquidity":0.30,"spread":0.20,"activity":0.20,
           "volatility":0.15,"news_heat":0.10,"time":0.05}

CACHE_TTL_SECONDS = 120
```

---

## 6. Task Breakdown

Each task ≤ 5 min, single goal, single file (except final orchestrator hook), independently committable & revertible.

### Task 1 — Skeleton + `_paths` wiring (no logic)
**File:** `market_intelligence.py`
**Action:** Create file with module docstring, imports, `class MarketIntelligence` with `__init__(base_dir=None)` using `_paths.get_base_dir()`, `data_dir`, `logs_dir`. Add `log()` helper mirroring other agents.
**Verify:** `./venv/bin/python -c "from market_intelligence import MarketIntelligence; MarketIntelligence()"` exits 0.
**Commit:** `feat(intel): scaffold market_intelligence module`

### Task 2 — Category detection (pure function + test)
**Files:** `market_intelligence.py`, `tests/test_market_intelligence.py`
**Action:**
1. Add `CATEGORY_PATTERNS` list and `classify_category(question: str) -> str`.
2. Write failing test `test_classify_category_known_examples` with 8 fixtures (crypto/politics/news/sports/entertainment/weather/ai/other).
3. Implement to make tests pass.
**Verify:** `./venv/bin/python -m pytest tests/test_market_intelligence.py::test_classify_category_known_examples -v` → 1 passed
**Commit:** `feat(intel): add category detection + tests`

### Task 3 — Tier assignment (pure function + test)
**File:** Same as Task 2.
**Action:** Add `assign_tier(category, tradability_score, slug) -> str` using `TIER_PRIORS` + crypto-slug whitelist. Failing test `test_assign_tier` covering: BTC slug → S, NHL high-score → C (capped), unknown → D, politics_macro mid → A.
**Verify:** `./venv/bin/python -m pytest tests/test_market_intelligence.py::test_assign_tier -v` → 1 passed
**Commit:** `feat(intel): add tier assignment + tests`

### Task 4 — Score functions (pure, with missing-data fallback)
**File:** Same.
**Action:** Add `clip_map`, `liquidity_score`, `spread_score`, `activity_score`, `volatility_score`, `news_heat_score`, `time_score`. All accept `None` and return `30` (conservative fallback) except `time_score` which uses `end_date` fallback `50`. Add `tradability_score(scores) -> float` using `WEIGHTS`. Failing test `test_scores_with_none_inputs_return_fallback` and `test_tradability_weighted_sum`.
**Verify:** `./venv/bin/python -m pytest tests/test_market_intelligence.py -k "scores or tradability" -v`
**Commit:** `feat(intel): add scoring functions + missing-data fallback`

### Task 5 — Shadow profile builder (pure + test)
**File:** Same.
**Action:** Add `build_shadow_profile(tier) -> dict` returning `TIER_DEFAULTS[tier]` copy. Add test `test_build_shadow_profile_all_tiers`.
**Verify:** `./venv/bin/python -m pytest tests/test_market_intelligence.py::test_build_shadow_profile_all_tiers -v`
**Commit:** `feat(intel): add shadow capital/stoploss profile builder`

### Task 6 — Orderbook cache I/O (no network yet, just file logic)
**File:** Same.
**Action:** Add `_load_cache()`, `_save_cache(cache)`, `_cache_get(slug)` (returns dict if fresh else `None`). Failing test `test_cache_ttl_expiry` using monkeypatched `datetime.now`.
**Verify:** `./venv/bin/python -m pytest tests/test_market_intelligence.py::test_cache_ttl_expiry -v`
**Commit:** `feat(intel): add orderbook cache file I/O with TTL`

### Task 7 — Optional CLOB enrichment (network, fully optional, fault-tolerant)
**File:** Same.
**Action:** Add `_enrich_market(slug)` calling `https://gamma-api.polymarket.com/markets?slug=...` then `https://clob.polymarket.com/book?token_id=...` using `urllib.request` with 3s timeout. **Wrap entire body in try/except — any failure returns `None`, increments `api_errors`, NEVER raises.** Add test `test_enrich_handles_network_error` with `urllib.request.urlopen` patched to raise.
**Verify:** `./venv/bin/python -m pytest tests/test_market_intelligence.py::test_enrich_handles_network_error -v`
**Commit:** `feat(intel): add fault-tolerant CLOB enrichment`

### Task 8 — End-to-end `run()` method
**File:** Same.
**Action:** Add `run()` method:
1. Load `data/latest_data.json` → `polymarket_markets` (list of 100 dicts with `id/slug/question/outcomes/outcome_prices/liquidity/volume/end_date`).
2. For each market: classify → score → tradability → tier → shadow profile.
3. Aggregate `tier_distribution`, `category_distribution`, `run_stats`.
4. Write `data/market_intelligence.json` atomically (write tmp + rename).
5. Return path.
**Failing test:** `test_run_produces_valid_json_for_fixture` using a 3-market fixture written to a tmp `latest_data.json` under a tmpdir set via `PA_BASE_DIR`.
**Verify:** `./venv/bin/python -m pytest tests/test_market_intelligence.py::test_run_produces_valid_json_for_fixture -v`
**Commit:** `feat(intel): add end-to-end run() with atomic write`

### Task 9 — CLI entry point
**File:** Same.
**Action:** Add `if __name__ == "__main__":` block calling `MarketIntelligence().run()` and printing summary line (`category_distribution`, `tier_distribution`, `duration_ms`).
**Verify (real data):**
```
./venv/bin/python market_intelligence.py
```
Expect: exit 0, prints summary, `data/market_intelligence.json` updated, schema validates by:
```
./venv/bin/python -c "import json; d=json.load(open('data/market_intelligence.json')); assert d['schema_version']=='phase1.0' and len(d['markets'])>0; print('OK', d['tier_distribution'])"
```
**Commit:** `feat(intel): add CLI entry point`

### Task 10 — Latest-data missing fallback test
**File:** `tests/test_market_intelligence.py`
**Action:** Add `test_run_handles_missing_latest_data` — call `run()` when `latest_data.json` absent; assert returns gracefully, writes empty markets dict with `data_quality.note="latest_data_missing"`, no exception.
**Verify:** `./venv/bin/python -m pytest tests/test_market_intelligence.py::test_run_handles_missing_latest_data -v`
**Commit:** `test(intel): cover missing latest_data fallback`

### Task 11 — Full pytest run
**Verify:**
```
./venv/bin/python -m pytest tests/test_market_intelligence.py -v
./venv/bin/python -m pytest tests/test_smoke.py -v
```
Expect: both green. No existing test regresses.
**Commit:** (no code change — verification gate)

### Task 12 — Orchestrator shadow hook (smallest possible)
**File:** `orchestrator.py`
**Action:** In `run_once()` between current step 2 (`regime_detector`) and step 3 (`strategy_manager`), insert:
```python
# 步骤 2.5：市场智能层（Phase 1 影子模式，零下游消费）
self.log("步骤 2.5/19: 市场智能层 (Market Intelligence, shadow)")
try:
    from market_intelligence import MarketIntelligence
    MarketIntelligence(self.base_dir).run()
except Exception as e:
    self.log(f"⚠️  market_intelligence 失败（影子层，不中断）: {e}")
```
Also update step count strings `/16` → `/19` only on the new line and the line above/below (cosmetic).
**Constraint:** No other line in `orchestrator.py` is modified.
**Verify:**
```
./venv/bin/python -m pytest tests/test_smoke.py -v
./venv/bin/python -c "from orchestrator import Orchestrator; Orchestrator()"
```
Expect: green + import clean.
**Commit:** `feat(intel): hook market_intelligence into orchestrator as shadow step 2.5`

### Task 13 — Single live cycle dry-run verification
**Action:** Run one orchestrator cycle under DRY_RUN, confirm shadow file refreshed and no downstream schema changed.
```
cd /opt/data/polymarket_arbitrage && \
EXECUTOR_DRY_RUN=1 PM_TRADER_PATH=/tmp/mock_pm_trader.sh \
  ./venv/bin/python -c "from orchestrator import Orchestrator; Orchestrator().run_once()"
```
**Acceptance checks:**
- `data/market_intelligence.json` mtime within last 60 s.
- `data/signals.json` schema unchanged (sample diff against pre-run copy).
- `data/review_results.json` schema unchanged.
- `data/capital_allocation.json` schema unchanged.
- `data/positions.json` schema unchanged.
**No commit.** Verification gate.

### Task 14 — 24h observation notes file
**File:** `reports/market_intelligence_phase1_observation.md`
**Action:** Stub with sections: tier distribution per hour, category distribution per hour, cache hit/miss, api_errors, anomalies. Will be filled by cron summary tomorrow.
**Commit:** `docs(intel): add 24h observation report stub`

---

## 7. TDD Order

```
T1 scaffold
T2 RED→GREEN test_classify_category_known_examples
T3 RED→GREEN test_assign_tier
T4 RED→GREEN test_scores_with_none_inputs_return_fallback + test_tradability_weighted_sum
T5 RED→GREEN test_build_shadow_profile_all_tiers
T6 RED→GREEN test_cache_ttl_expiry
T7 RED→GREEN test_enrich_handles_network_error
T8 RED→GREEN test_run_produces_valid_json_for_fixture
T9 manual CLI smoke
T10 RED→GREEN test_run_handles_missing_latest_data
T11 full pytest gate (all green)
T12 orchestrator hook + smoke pytest gate
T13 single live cycle DRY_RUN verification
T14 observation stub
```

---

## 8. Validation Commands

```bash
ROOT=/opt/data/polymarket_arbitrage
PY=$ROOT/venv/bin/python

# Unit + integration
$PY -m pytest $ROOT/tests/test_market_intelligence.py -v

# Regression
$PY -m pytest $ROOT/tests/test_smoke.py -v

# Standalone CLI
cd $ROOT && $PY market_intelligence.py

# Schema sanity
$PY -c "import json; d=json.load(open('$ROOT/data/market_intelligence.json')); \
        assert d['schema_version']=='phase1.0'; \
        assert 'markets' in d and 'tier_distribution' in d; \
        print('schema OK', d['tier_distribution'])"

# Single live cycle (DRY_RUN forced)
cd $ROOT && EXECUTOR_DRY_RUN=1 PM_TRADER_PATH=/tmp/mock_pm_trader.sh \
  $PY -c "from orchestrator import Orchestrator; Orchestrator().run_once()"

# Confirm downstream schemas unchanged (compare keys)
$PY -c "import json; \
  print('signals keys:', set(json.load(open('$ROOT/data/signals.json'))[0].keys())); \
  print('review keys:', set(json.load(open('$ROOT/data/review_results.json')).keys())); \
  print('capital keys:', set(json.load(open('$ROOT/data/capital_allocation.json')).keys()))"
```

Expected key sets must match pre-Phase-1 snapshot (no new keys in any of those three files).

---

## 9. Rollback

Each task is its own commit; rollback options ordered by scope.

| Scope | Command |
|---|---|
| Disable shadow hook only | `git revert <Task 12 commit>` — orchestrator returns to 18-step flow, module still exists but never called |
| Remove module entirely | `git revert <Task 1..12 commits>` in reverse order |
| Emergency live disable (no git) | `mv market_intelligence.py market_intelligence.py.disabled` — next cycle logs warning, continues |
| Delete stale data | `rm data/market_intelligence.json data/orderbook_cache.json` — regenerated next cycle or stays absent |

Any rollback path leaves all of: `signals.json`, `review_results.json`, `capital_allocation.json`, `positions.json`, `sell_signals.json` **bit-identical to today's schema**. No downstream consumer reads the new file in Phase 1.

---

## 10. Expected 24h Observations

After Task 13 lands, let it run 24 h, then evaluate against acceptance thresholds.

| Metric | Acceptance Range | Action if outside |
|---|---|---|
| `market_intelligence.json` write success rate | ≥ 95 % of cycles | If < 95 %: inspect orchestrator log `step 2.5` |
| Tier S share | 1–15 % | If > 15 %: tighten `TIER_S_CRYPTO_SLUG_TOKENS`; if 0 %: investigate BTC/ETH slugs |
| Tier D share | 30–70 % | If > 70 %: relax fallback floor; if < 30 %: tighten priors |
| Category `entertainment` share with `tier ∈ {S,A}` | 0 (must be 0 by prior cap) | If > 0: bug in `assign_tier` cap |
| `api_errors / (cache_hits+misses)` | < 30 % | If higher: increase TTL or accept fallback-only mode |
| `cache_hits / (hits+misses)` after warm-up (>10 min) | ≥ 50 % | If lower: TTL too short or cache write failing |
| `tradability_score` distribution | non-degenerate (std > 5) | If degenerate: scoring inputs all None → check `latest_data.polymarket_markets` shape |
| Downstream files schema | unchanged | If changed: **immediate rollback Task 12** |
| Existing P&L / win-rate / signal count | within ±10 % of last 24 h baseline | If outside: **immediate rollback Task 12**, investigate orchestrator timing |

Phase 1 success = 24 h elapsed with all rows in acceptable range AND zero impact on downstream schemas.

Only then propose Phase 2.
