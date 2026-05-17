"""Tests for market_intelligence.py (Phase 1 — Shadow Mode)."""

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import pytest  # noqa: E402

from market_intelligence import (  # noqa: E402
    classify_category,
    assign_tier,
    clip_map,
    liquidity_score,
    spread_score,
    activity_score,
    volatility_score,
    news_heat_score,
    time_score,
    tradability_score,
    WEIGHTS,
)


@pytest.mark.parametrize(
    "question,expected",
    [
        ("Will Bitcoin hit $100k by year end?", "crypto"),
        ("Will the Fed cut interest rates in December?", "politics_macro"),
        ("Will Ukraine-Russia ceasefire happen this month?", "breaking_news"),
        ("Will OpenAI release GPT-6 in 2026?", "ai_tech"),
        ("Will hurricane Delta hit Florida?", "weather"),
        ("Will the Vegas Golden Knights win the 2026 NHL Stanley Cup?", "sports"),
        ("New Rihanna Album before GTA VI?", "entertainment"),
        ("Will the price of bananas double?", "other"),
    ],
)
def test_classify_category_known_examples(question, expected):
    assert classify_category(question) == expected


def test_assign_tier_btc_slug_forces_s():
    # 高 tradability + crypto + BTC slug → S
    assert assign_tier("crypto", 75.0, "will-btc-hit-100k-2026") == "S"


def test_assign_tier_eth_slug_forces_s_even_with_moderate_score():
    # 即使 tradability 没到 80，ETH 仍强制 S（白名单）
    assert assign_tier("crypto", 55.0, "ethereum-above-3000-eoy") == "S"


def test_assign_tier_sports_high_score_capped_to_c():
    # sports allowed = {C, D}；即使 score 高也被先验封顶
    assert assign_tier("sports", 85.0, "vegas-golden-knights-stanley-cup") == "C"


def test_assign_tier_entertainment_low_score_falls_to_d():
    assert assign_tier("entertainment", 15.0, "new-rihanna-album-before-gta-vi-926") == "D"


def test_assign_tier_politics_macro_mid_score_to_a():
    # politics_macro allowed = {A, B, C}; tradability 65 → bucket A
    assert assign_tier("politics_macro", 65.0, "fed-cuts-december") == "A"


def test_assign_tier_unknown_category_defaults_to_d_or_c():
    # other allowed = {C, D}; low score → D
    assert assign_tier("other", 10.0, "random-market") == "D"


def test_assign_tier_breaking_news_high_score_to_b():
    # breaking_news allowed = {B, C}; score 75 (bucket A) → 收敛到 B
    assert assign_tier("breaking_news", 75.0, "ukraine-ceasefire-may") == "B"


def test_assign_tier_crypto_non_whitelist_uses_normal_bucket():
    # crypto allowed = {S,A,B,C}；DOGE 不在 S 白名单 → 走 bucket
    assert assign_tier("crypto", 65.0, "doge-to-1-dollar") == "A"  # 60-79 → A
    assert assign_tier("crypto", 45.0, "doge-to-1-dollar") == "B"  # 40-59 → B
    assert assign_tier("crypto", 25.0, "doge-to-1-dollar") == "C"  # 20-39 → C



# ---------------- scoring functions ----------------

def test_clip_map_monotonic_interpolation():
    points = [(0, 0), (10, 50), (100, 100)]
    assert clip_map(0, points) == 0
    assert clip_map(10, points) == 50
    assert clip_map(100, points) == 100
    # 区间外取边界
    assert clip_map(-5, points) == 0
    assert clip_map(200, points) == 100
    # 线性插值
    assert clip_map(5, points) == pytest.approx(25.0)
    assert clip_map(55, points) == pytest.approx(75.0)


def test_clip_map_handles_none():
    assert clip_map(None, [(0, 0), (10, 100)]) == 30  # 保守 fallback


def test_scores_with_none_inputs_return_fallback():
    # 所有非 time_score 的评分函数: None → 30
    assert liquidity_score(None, None) == 30
    assert spread_score(None) == 30
    assert activity_score(None, None) == 30
    assert volatility_score(None) == 30
    assert news_heat_score("anything", None) == 30
    # time_score: None → 50（不同 fallback）
    assert time_score(None) == 50


def test_liquidity_score_grows_with_volume_and_depth():
    low  = liquidity_score(500, 10)
    mid  = liquidity_score(10000, 500)
    high = liquidity_score(1_000_000, 50_000)
    assert low < mid < high
    assert 0 <= low <= 100 and 0 <= high <= 100


def test_spread_score_drops_with_wider_spread():
    tight = spread_score(0.001)
    mid   = spread_score(0.03)
    wide  = spread_score(0.10)
    assert tight > mid > wide
    assert 0 <= wide <= 100 and 0 <= tight <= 100


def test_activity_score_drops_with_stale_age():
    fresh = activity_score(60, 50)
    stale = activity_score(86400, 0)
    assert fresh > stale
    assert 0 <= stale <= 100 and 0 <= fresh <= 100


def test_volatility_score_dead_market_low_extreme_market_also_low():
    dead    = volatility_score(0.001)   # 死水
    healthy = volatility_score(0.03)    # 健康
    extreme = volatility_score(0.30)    # 太跳
    assert healthy > dead
    assert healthy > extreme


def test_news_heat_score_grows_with_hits():
    text_low  = "nothing here about bitcoin"
    text_high = ("bitcoin " * 30)
    low  = news_heat_score("Will Bitcoin hit $100k?", text_low)
    high = news_heat_score("Will Bitcoin hit $100k?", text_high)
    assert high >= low


def test_time_score_decays_near_expiry():
    from datetime import datetime, timedelta, timezone
    now = datetime.now(timezone.utc)
    far  = (now + timedelta(days=180)).isoformat().replace("+00:00", "Z")
    near = (now + timedelta(hours=12)).isoformat().replace("+00:00", "Z")
    past = (now - timedelta(days=1)).isoformat().replace("+00:00", "Z")
    assert time_score(far) > time_score(near)
    assert time_score(past) == 0  # 已过期


def test_tradability_weighted_sum():
    scores = {
        "liquidity_score":  100,
        "spread_score":     100,
        "activity_score":   100,
        "volatility_score": 100,
        "news_heat_score":  100,
        "time_score":       100,
    }
    assert tradability_score(scores) == pytest.approx(100.0)

    zero = {k: 0 for k in scores}
    assert tradability_score(zero) == pytest.approx(0.0)

    # 权重总和必须 = 1.0
    assert sum(WEIGHTS.values()) == pytest.approx(1.0)



# ---------------- build_profile ----------------

def test_build_profile_minimal_inputs_returns_required_keys():
    from market_intelligence import build_profile
    market = {
        "id": "mkt-1",
        "slug": "btc-100k-by-eoy",
        "question": "Will Bitcoin hit $100k by end of year?",
        "liquidity": 50000,
        "volume": 200000,
        "end_date": "2099-01-01T00:00:00Z",
    }
    profile = build_profile(market, orderbook=None, news_text=None)
    # 必备字段
    for k in [
        "id", "slug", "question", "category", "tier",
        "tradability_score", "scores",
        "liquidity_usd", "spread", "best_bid", "best_ask",
        "missing_fields", "shadow_capital_weight", "shadow_stop_loss",
        "shadow_take_profit", "phase", "schema_version",
    ]:
        assert k in profile, f"missing key: {k}"
    assert profile["phase"] == "shadow"
    assert profile["category"] == "crypto"
    assert profile["tier"] == "S"  # btc slug → S
    # missing_fields 应该包含 orderbook / news
    assert "orderbook" in profile["missing_fields"]
    assert "news_text" in profile["missing_fields"]


def test_build_profile_with_orderbook_extracts_spread():
    from market_intelligence import build_profile
    market = {
        "id": "mkt-2",
        "slug": "elections-2099",
        "question": "Will the incumbent win the 2099 election?",
        "liquidity": 100000,
        "end_date": "2099-11-05T00:00:00Z",
    }
    orderbook = {
        "best_bid": 0.42,
        "best_ask": 0.45,
        "bids": [{"price": 0.42, "size": 1000}, {"price": 0.41, "size": 2000}],
        "asks": [{"price": 0.45, "size": 800},  {"price": 0.46, "size": 1500}],
        "last_trade_age_sec": 90,
        "trade_freq_1h": 10,
        "std_short": 0.02,
    }
    profile = build_profile(market, orderbook=orderbook, news_text=None)
    assert profile["best_bid"]  == 0.42
    assert profile["best_ask"]  == 0.45
    assert profile["spread"]    == pytest.approx(0.03)
    assert profile["category"]  == "politics_macro"
    # tradability should not be the all-fallback value
    assert profile["tradability_score"] > 30


def test_build_profile_records_missing_fields_list():
    from market_intelligence import build_profile
    market = {"id": "mkt-3", "slug": "x", "question": "Random?", "end_date": None}
    profile = build_profile(market, orderbook=None, news_text=None)
    for f in ("orderbook", "news_text", "end_date"):
        assert f in profile["missing_fields"]
    # 全 fallback → tradability 应在 25~55 之间（保守区）
    assert 20 <= profile["tradability_score"] <= 60


def test_build_profile_shadow_params_match_tier():
    from market_intelligence import build_profile, TIER_DEFAULTS
    market = {
        "id": "mkt-4", "slug": "btc-200k",
        "question": "Will Bitcoin hit $200k?",
        "liquidity": 1_000_000,
        "end_date": "2099-12-31T00:00:00Z",
    }
    p = build_profile(market, orderbook=None, news_text=None)
    tier = p["tier"]
    defaults = TIER_DEFAULTS[tier]
    assert p["shadow_capital_weight"] == defaults["capital_weight"]
    assert p["shadow_stop_loss"]      == defaults["stop_loss"]
    assert p["shadow_take_profit"]    == defaults["take_profit"]


def test_build_profile_never_raises_on_garbage_input():
    from market_intelligence import build_profile
    garbage = {"id": None, "slug": None, "question": None}
    p = build_profile(garbage, orderbook=None, news_text=None)
    assert p["category"] == "other"
    assert p["tier"] in ("C", "D")



# ---------------- OrderbookCache ----------------

def test_orderbook_cache_set_get_roundtrip(tmp_path):
    from market_intelligence import OrderbookCache
    cache_file = tmp_path / "ob.json"
    c = OrderbookCache(cache_file, ttl_sec=120)
    c.set("mkt-1", {"best_bid": 0.42, "best_ask": 0.45})
    got = c.get("mkt-1")
    assert got["best_bid"] == 0.42


def test_orderbook_cache_expires_after_ttl(tmp_path):
    from market_intelligence import OrderbookCache
    cache_file = tmp_path / "ob.json"
    c = OrderbookCache(cache_file, ttl_sec=1)
    c.set("mkt-2", {"best_bid": 0.5})
    # Manually backdate the entry
    import json, time
    data = json.loads(cache_file.read_text())
    data["mkt-2"]["fetched_at"] = time.time() - 3600
    cache_file.write_text(json.dumps(data))
    c2 = OrderbookCache(cache_file, ttl_sec=1)
    assert c2.get("mkt-2") is None


def test_orderbook_cache_survives_corrupt_file(tmp_path):
    from market_intelligence import OrderbookCache
    cache_file = tmp_path / "ob.json"
    cache_file.write_text("{not valid json")
    c = OrderbookCache(cache_file, ttl_sec=120)
    # Should not raise; behaves as empty cache
    assert c.get("anything") is None
    c.set("mkt-3", {"best_bid": 0.6})
    assert c.get("mkt-3")["best_bid"] == 0.6


def test_orderbook_cache_persists_across_instances(tmp_path):
    from market_intelligence import OrderbookCache
    cache_file = tmp_path / "ob.json"
    c1 = OrderbookCache(cache_file, ttl_sec=600)
    c1.set("mkt-4", {"best_bid": 0.7})
    c2 = OrderbookCache(cache_file, ttl_sec=600)
    assert c2.get("mkt-4")["best_bid"] == 0.7


def test_orderbook_cache_missing_file_ok(tmp_path):
    from market_intelligence import OrderbookCache
    cache_file = tmp_path / "subdir" / "ob.json"
    c = OrderbookCache(cache_file, ttl_sec=120)
    assert c.get("anything") is None
    c.set("mkt-5", {"x": 1})
    assert cache_file.exists()



# ---------------- fetch_orderbook ----------------

def test_fetch_orderbook_returns_none_on_http_error(monkeypatch):
    from market_intelligence import fetch_orderbook
    class FakeResp:
        status_code = 500
        text = "boom"
        def json(self): return {}
    def fake_get(url, params=None, timeout=None):
        return FakeResp()
    import market_intelligence as mi
    monkeypatch.setattr(mi.requests, "get", fake_get)
    assert fetch_orderbook("0xabc") is None


def test_fetch_orderbook_returns_none_on_exception(monkeypatch):
    from market_intelligence import fetch_orderbook
    def boom(url, params=None, timeout=None):
        raise RuntimeError("network down")
    import market_intelligence as mi
    monkeypatch.setattr(mi.requests, "get", boom)
    assert fetch_orderbook("0xabc") is None


def test_fetch_orderbook_parses_clob_response(monkeypatch):
    from market_intelligence import fetch_orderbook
    payload = {
        "bids": [{"price": "0.42", "size": "1000"}, {"price": "0.41", "size": "2000"}],
        "asks": [{"price": "0.45", "size": "800"},  {"price": "0.46", "size": "1500"}],
    }
    class FakeResp:
        status_code = 200
        def json(self): return payload
    def fake_get(url, params=None, timeout=None):
        assert "clob.polymarket.com" in url or "polymarket" in url.lower()
        return FakeResp()
    import market_intelligence as mi
    monkeypatch.setattr(mi.requests, "get", fake_get)
    ob = fetch_orderbook("0xabc")
    assert ob is not None
    assert ob["best_bid"] == 0.42
    assert ob["best_ask"] == 0.45
    assert len(ob["bids"]) == 2
    assert len(ob["asks"]) == 2


def test_fetch_orderbook_empty_book_returns_none_prices(monkeypatch):
    from market_intelligence import fetch_orderbook
    class FakeResp:
        status_code = 200
        def json(self): return {"bids": [], "asks": []}
    def fake_get(url, params=None, timeout=None):
        return FakeResp()
    import market_intelligence as mi
    monkeypatch.setattr(mi.requests, "get", fake_get)
    ob = fetch_orderbook("0xabc")
    assert ob is not None
    assert ob["best_bid"] is None
    assert ob["best_ask"] is None


def test_fetch_orderbook_handles_missing_token_id():
    from market_intelligence import fetch_orderbook
    assert fetch_orderbook(None) is None
    assert fetch_orderbook("") is None



# ---------------- extract_token_id + enrich_market ----------------

def test_extract_token_id_handles_multiple_shapes():
    from market_intelligence import extract_token_id
    # Shape 1: clobTokenIds as JSON-encoded string
    m1 = {"clobTokenIds": '["0xabc","0xdef"]'}
    assert extract_token_id(m1) == "0xabc"
    # Shape 2: clobTokenIds as list
    m2 = {"clobTokenIds": ["0x111", "0x222"]}
    assert extract_token_id(m2) == "0x111"
    # Shape 3: tokens array
    m3 = {"tokens": [{"token_id": "0x333"}, {"token_id": "0x444"}]}
    assert extract_token_id(m3) == "0x333"
    # Shape 4: garbage
    assert extract_token_id({}) is None
    assert extract_token_id({"clobTokenIds": "not-json"}) is None
    assert extract_token_id(None) is None


def test_enrich_market_calls_fetcher_and_builds_profile(monkeypatch):
    from market_intelligence import enrich_market
    fake_book = {
        "best_bid": 0.42, "best_ask": 0.45,
        "bids": [{"price": 0.42, "size": 1000}],
        "asks": [{"price": 0.45, "size": 800}],
    }
    calls = []
    def fake_fetch(token_id):
        calls.append(token_id)
        return fake_book
    market = {
        "id": "mkt-A",
        "slug": "btc-100k",
        "question": "Will Bitcoin hit $100k?",
        "liquidity": 50000,
        "end_date": "2099-01-01T00:00:00Z",
        "clobTokenIds": '["0xtoken1","0xtoken2"]',
    }
    profile = enrich_market(market, fetcher=fake_fetch, cache=None, news_text=None)
    assert calls == ["0xtoken1"]
    assert profile["best_bid"] == 0.42
    assert profile["best_ask"] == 0.45


def test_enrich_market_uses_cache_when_present(tmp_path, monkeypatch):
    from market_intelligence import enrich_market, OrderbookCache
    cache = OrderbookCache(tmp_path / "ob.json", ttl_sec=600)
    cache.set("0xtoken-cached", {
        "best_bid": 0.10, "best_ask": 0.12,
        "bids": [], "asks": [],
    })
    fetcher_called = []
    def fetcher(token_id):
        fetcher_called.append(token_id)
        return None
    market = {
        "id": "mkt-B", "slug": "x", "question": "x",
        "clobTokenIds": '["0xtoken-cached"]',
    }
    profile = enrich_market(market, fetcher=fetcher, cache=cache, news_text=None)
    assert fetcher_called == []  # cache hit, no network
    assert profile["best_bid"] == 0.10


def test_enrich_market_no_token_records_missing(monkeypatch):
    from market_intelligence import enrich_market
    fetcher_called = []
    def fetcher(token_id):
        fetcher_called.append(token_id)
        return {"best_bid": 0.5, "best_ask": 0.6, "bids": [], "asks": []}
    market = {"id": "mkt-C", "slug": "x", "question": "x"}
    profile = enrich_market(market, fetcher=fetcher, cache=None, news_text=None)
    assert fetcher_called == []  # no token → no fetch attempt
    assert "orderbook" in profile["missing_fields"]
    assert profile["best_bid"] is None


def test_enrich_market_fetcher_failure_does_not_raise(monkeypatch):
    from market_intelligence import enrich_market
    def fetcher(token_id):
        return None
    market = {
        "id": "mkt-D", "slug": "x", "question": "x",
        "clobTokenIds": ["0xtok"],
    }
    profile = enrich_market(market, fetcher=fetcher, cache=None, news_text=None)
    assert "orderbook" in profile["missing_fields"]
    assert profile["best_bid"] is None



# ---------------- MarketIntelligence.run() ----------------

def test_market_intelligence_run_writes_output(tmp_path, monkeypatch):
    from market_intelligence import MarketIntelligence
    # Set up fake base_dir with data/latest_data.json
    base = tmp_path
    (base / "data").mkdir()
    latest = {
        "polymarket_markets": [
            {
                "id": "mkt-1",
                "slug": "btc-100k",
                "question": "Will Bitcoin hit $100k by EOY?",
                "liquidity": 50000,
                "end_date": "2099-01-01T00:00:00Z",
                "clobTokenIds": '["0xtok1"]',
            },
            {
                "id": "mkt-2",
                "slug": "election-2099",
                "question": "Will the incumbent win the 2099 election?",
                "liquidity": 100000,
                "end_date": "2099-11-05T00:00:00Z",
                "clobTokenIds": '["0xtok2"]',
            },
        ]
    }
    (base / "data" / "latest_data.json").write_text(json.dumps(latest))

    def fake_fetcher(token_id):
        return {
            "best_bid": 0.45, "best_ask": 0.48,
            "bids": [{"price": 0.45, "size": 500}],
            "asks": [{"price": 0.48, "size": 600}],
        }

    mi = MarketIntelligence(base_dir=base)
    result = mi.run(fetcher=fake_fetcher)

    assert result["success"] is True
    assert result["markets_processed"] == 2
    out_path = base / "data" / "market_intelligence.json"
    assert out_path.exists()
    written = json.loads(out_path.read_text())
    assert written["schema_version"]
    assert written["phase"] == "shadow"
    assert len(written["profiles"]) == 2
    assert written["profiles"][0]["id"] == "mkt-1"
    assert written["profiles"][0]["best_bid"] == 0.45


def test_market_intelligence_run_handles_missing_latest_data(tmp_path):
    from market_intelligence import MarketIntelligence
    base = tmp_path
    mi = MarketIntelligence(base_dir=base)
    result = mi.run(fetcher=lambda t: None)
    assert result["success"] is False
    assert "latest_data" in result["error"].lower()


def test_market_intelligence_run_skips_bad_markets(tmp_path):
    from market_intelligence import MarketIntelligence
    base = tmp_path
    (base / "data").mkdir()
    latest = {
        "polymarket_markets": [
            None,  # garbage
            {"id": "good", "slug": "x", "question": "x", "clobTokenIds": ["0xt"]},
            {},  # empty
        ]
    }
    (base / "data" / "latest_data.json").write_text(json.dumps(latest))
    mi = MarketIntelligence(base_dir=base)
    result = mi.run(fetcher=lambda t: None)
    assert result["success"] is True
    # Should process all 3 — bad ones get "other"/"D" profiles, never raises
    written = json.loads((base / "data" / "market_intelligence.json").read_text())
    assert len(written["profiles"]) == 3


def test_market_intelligence_run_uses_cache(tmp_path):
    from market_intelligence import MarketIntelligence
    base = tmp_path
    (base / "data").mkdir()
    latest = {"polymarket_markets": [
        {"id": "m1", "slug": "x", "question": "x", "clobTokenIds": ["0xCACHED"]},
    ]}
    (base / "data" / "latest_data.json").write_text(json.dumps(latest))

    fetch_calls = []
    def fetcher(tok):
        fetch_calls.append(tok)
        return {"best_bid": 0.5, "best_ask": 0.55, "bids": [], "asks": []}

    mi = MarketIntelligence(base_dir=base)
    mi.run(fetcher=fetcher)
    assert fetch_calls == ["0xCACHED"]
    # Second run should hit cache
    mi2 = MarketIntelligence(base_dir=base)
    mi2.run(fetcher=fetcher)
    assert fetch_calls == ["0xCACHED"]  # no new fetch


def test_market_intelligence_run_includes_metadata(tmp_path):
    from market_intelligence import MarketIntelligence
    base = tmp_path
    (base / "data").mkdir()
    (base / "data" / "latest_data.json").write_text(json.dumps({"polymarket_markets": []}))
    mi = MarketIntelligence(base_dir=base)
    mi.run(fetcher=lambda t: None)
    written = json.loads((base / "data" / "market_intelligence.json").read_text())
    assert "generated_at" in written
    assert "phase" in written
    assert "schema_version" in written
    assert "tier_distribution" in written  # 观察用：每档统计



# ---------------- CLI ----------------

def test_cli_parses_args():
    from market_intelligence import _parse_args
    args = _parse_args(["--max-markets", "5", "--no-network"])
    assert args.max_markets == 5
    assert args.no_network is True

    args2 = _parse_args([])
    assert args2.max_markets is None
    assert args2.no_network is False


def test_cli_main_no_network_uses_null_fetcher(tmp_path, monkeypatch):
    from market_intelligence import _main
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "latest_data.json").write_text(json.dumps({
        "polymarket_markets": [
            {"id": "m1", "slug": "x", "question": "x", "clobTokenIds": ["0xT"]},
        ]
    }))
    # 直接传 base_dir，验证 --no-network 不会调用任何 HTTP
    code = _main(["--no-network"], base_dir=tmp_path)
    assert code == 0
    written = json.loads((tmp_path / "data" / "market_intelligence.json").read_text())
    assert len(written["profiles"]) == 1
    assert "orderbook" in written["profiles"][0]["missing_fields"]


def test_cli_main_max_markets_limits_input(tmp_path):
    from market_intelligence import _main
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "latest_data.json").write_text(json.dumps({
        "polymarket_markets": [
            {"id": f"m{i}", "slug": "x", "question": "x"} for i in range(20)
        ]
    }))
    code = _main(["--no-network", "--max-markets", "3"], base_dir=tmp_path)
    assert code == 0
    written = json.loads((tmp_path / "data" / "market_intelligence.json").read_text())
    assert len(written["profiles"]) == 3
