"""Tests for market_intelligence.py (Phase 1 — Shadow Mode)."""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import pytest  # noqa: E402

from market_intelligence import classify_category, assign_tier  # noqa: E402


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
