"""Tests for market_intelligence.py (Phase 1 — Shadow Mode)."""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import pytest  # noqa: E402

from market_intelligence import classify_category  # noqa: E402


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
