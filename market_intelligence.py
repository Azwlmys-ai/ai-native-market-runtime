"""
Market Intelligence Layer (Phase 1 — Shadow Mode)

为每个 Polymarket 市场生成画像（category / tier / 评分 / 影子参数）。

⚠️ Phase 1 仅产出 data/market_intelligence.json，**不被任何下游消费**：
   - 不参与资金分配
   - 不参与 review
   - 不参与买入/卖出执行
   - 不参与止损

由 orchestrator 在 step 2.5 调用，失败被外层 try/except 兜住，绝不阻断主流程。
"""

import json
import re
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _paths import get_base_dir


SCHEMA_VERSION = "phase1.0"


# Order matters: first match wins. Patterns are compiled lazily once.
CATEGORY_PATTERNS = [
    ("breaking_news",  [r"\b(ukraine|russia|israel|hamas|gaza|ceasefire|invasion|war|attack|earthquake|tsunami)\b"]),
    ("weather",        [r"\b(hurricane|storm|temperature|snow|rainfall|noaa|cyclone|typhoon|tornado)\b"]),
    ("ai_tech",        [r"\b(openai|gpt[-\s]?[0-9]?|anthropic|claude|grok|gemini|llm|ai\s+model|nvidia|tsmc|chatgpt)\b"]),
    ("crypto",         [r"\b(bitcoin|btc|ethereum|eth|solana|sol|xrp|ripple|doge|crypto|altcoin|usdt|stablecoin)\b"]),
    ("politics_macro", [r"\b(fed|fomc|interest rate|rate cut|rate hike|etf|election|president|trump|biden|harris|spx|s&p\s*500)\b"]),
    ("sports",         [r"\b(nba|nhl|nfl|mlb|premier league|champions league|stanley cup|world cup|playoffs?|super bowl|knights|lakers|celtics|ducks|avalanche)\b"]),
    ("entertainment",  [r"\b(gta|grammy|oscar|billboard|netflix|album|rihanna|drake|taylor swift|movie|tv show|emmy|disney)\b"]),
    ("politics_other", [r"\b(senate|congress|governor|mayor|cabinet|impeach|parliament|prime minister)\b"]),
]
_COMPILED_CATEGORY_PATTERNS = [
    (cat, [re.compile(p, re.IGNORECASE) for p in patterns])
    for cat, patterns in CATEGORY_PATTERNS
]


def classify_category(question: str) -> str:
    """Classify a market question into one of the known categories.

    Returns "other" if no pattern matches. Pure function, no side effects.
    """
    if not question:
        return "other"
    text = str(question)
    for category, regexes in _COMPILED_CATEGORY_PATTERNS:
        for rx in regexes:
            if rx.search(text):
                return category
    return "other"


# Tier priors: (allowed_tier_set, default_tier).
# 类别先验保证 sports / entertainment 即使评分高也不会跳到 S。
TIER_PRIORS = {
    "crypto":         ({"S", "A", "B", "C"}, "A"),
    "politics_macro": ({"A", "B", "C"},      "A"),
    "politics_other": ({"B", "C", "D"},      "C"),
    "breaking_news":  ({"B", "C"},           "B"),
    "ai_tech":        ({"B", "C"},           "B"),
    "weather":        ({"B", "C"},           "C"),
    "sports":         ({"C", "D"},           "C"),
    "entertainment":  ({"C", "D"},           "D"),
    "other":          ({"C", "D"},           "D"),
}

# Crypto slug tokens that force Tier S (case-insensitive substring match on slug).
TIER_S_CRYPTO_SLUG_TOKENS = (
    "btc", "bitcoin", "eth", "ethereum", "sol", "solana", "xrp", "ripple",
)

_TIER_ORDER = ["S", "A", "B", "C", "D"]


def _bucket_from_score(score: float) -> str:
    """Map tradability_score (0-100) to a raw bucket before category priors."""
    if score >= 80:
        return "S"
    if score >= 60:
        return "A"
    if score >= 40:
        return "B"
    if score >= 20:
        return "C"
    return "D"


def assign_tier(category: str, tradability_score: float, slug: str) -> str:
    """Assign tier S/A/B/C/D.

    Priority:
      1. crypto + slug 命中白名单 → S
      2. 否则按 tradability_score 算 raw bucket
      3. 用 TIER_PRIORS[category] 把 bucket 收敛到 allowed 集合（取不高于 bucket 的最近 allowed 档）
      4. 找不到则返回 category 的 default_tier

    Pure function. Never raises for unknown category — falls back to "other" priors.
    """
    slug_lower = (slug or "").lower()
    if category == "crypto":
        if any(tok in slug_lower for tok in TIER_S_CRYPTO_SLUG_TOKENS):
            return "S"

    allowed, default = TIER_PRIORS.get(category, TIER_PRIORS["other"])

    try:
        score = float(tradability_score)
    except (TypeError, ValueError):
        return default

    bucket = _bucket_from_score(score)
    if bucket in allowed:
        return bucket
    # 从 bucket 起向下找最近的 allowed 档（不上调）
    start = _TIER_ORDER.index(bucket)
    for tier in _TIER_ORDER[start:]:
        if tier in allowed:
            return tier
    return default


class MarketIntelligence:
    def __init__(self, base_dir=None):
        self.base_dir = Path(base_dir) if base_dir else get_base_dir()
        self.data_dir = self.base_dir / "data"
        self.logs_dir = self.base_dir / "logs"
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.logs_dir.mkdir(parents=True, exist_ok=True)

    def log(self, message):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_msg = f"[{timestamp}] [Market Intelligence] {message}"
        print(log_msg, flush=True)
        log_file = self.logs_dir / f"market_intelligence_{datetime.now().strftime('%Y%m%d')}.log"
        try:
            with open(log_file, "a") as f:
                f.write(log_msg + "\n")
        except Exception:
            # 日志失败不能影响主流程
            pass


if __name__ == "__main__":
    # Task 1 阶段仅冒烟，后续任务实现 run()
    mi = MarketIntelligence()
    mi.log("scaffold ready (Task 1)")
