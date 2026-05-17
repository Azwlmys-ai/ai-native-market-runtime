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


# ---------------- scoring functions ----------------
# 设计原则：
#   1. 全部纯函数，无 I/O
#   2. 任何 None / 异常输入 → 返回保守 fallback（30 分，time_score 返回 50）
#   3. 输出钳制在 [0, 100]

SCORE_FALLBACK = 30
TIME_SCORE_FALLBACK = 50

WEIGHTS = {
    "liquidity":  0.30,
    "spread":     0.20,
    "activity":   0.20,
    "volatility": 0.15,
    "news_heat":  0.10,
    "time":       0.05,
}


def clip_map(value, points, fallback=SCORE_FALLBACK):
    """Piecewise-linear interpolation through (x, y) anchor points.

    - points 必须按 x 升序
    - value <= points[0].x → points[0].y
    - value >= points[-1].x → points[-1].y
    - 中间段 → 线性插值
    - value 为 None 或非数 → fallback
    """
    if value is None:
        return fallback
    try:
        v = float(value)
    except (TypeError, ValueError):
        return fallback
    if v != v:  # NaN
        return fallback
    if v <= points[0][0]:
        return points[0][1]
    if v >= points[-1][0]:
        return points[-1][1]
    for i in range(1, len(points)):
        x0, y0 = points[i - 1]
        x1, y1 = points[i]
        if v <= x1:
            if x1 == x0:
                return y0
            ratio = (v - x0) / (x1 - x0)
            return y0 + ratio * (y1 - y0)
    return points[-1][1]


def liquidity_score(liquidity_usd, depth_1pct_usd):
    """Score based on 24h liquidity + 1%-depth (depth weighted higher)."""
    if liquidity_usd is None and depth_1pct_usd is None:
        return SCORE_FALLBACK
    base  = clip_map(liquidity_usd,   [(1e3, 0), (1e4, 30), (1e5, 60), (1e6, 90), (1e7, 100)])
    depth = clip_map(depth_1pct_usd,  [(50, 0), (500, 40), (5000, 80), (50000, 100)])
    return max(0.0, min(100.0, 0.4 * base + 0.6 * depth))


def spread_score(spread):
    """Score from spread (best_ask - best_bid)."""
    if spread is None:
        return SCORE_FALLBACK
    return clip_map(spread, [(0.001, 100), (0.01, 80), (0.03, 50), (0.05, 20), (0.10, 0)])


def activity_score(last_trade_age_sec, trade_freq_1h):
    """Score from recency + frequency of trades."""
    if last_trade_age_sec is None and trade_freq_1h is None:
        return SCORE_FALLBACK
    age  = clip_map(last_trade_age_sec, [(60, 100), (300, 80), (1800, 50), (3600, 20), (86400, 0)])
    freq = clip_map(trade_freq_1h,      [(0, 0), (1, 20), (5, 50), (20, 80), (50, 100)])
    return max(0.0, min(100.0, 0.5 * age + 0.5 * freq))


def volatility_score(std_short):
    """Score peaks at moderate volatility — dead and crazy markets both low."""
    if std_short is None:
        return SCORE_FALLBACK
    try:
        v = float(std_short)
    except (TypeError, ValueError):
        return SCORE_FALLBACK
    if v < 0.005:
        return 20.0
    if v > 0.20:
        return 30.0
    # 0.005 -> 20, 0.02 -> 80, 0.05 -> 100, 0.10 -> 70, 0.20 -> 30
    return clip_map(v, [(0.005, 20), (0.02, 80), (0.05, 100), (0.10, 70), (0.20, 30)])


_STOPWORDS = {
    "will", "the", "a", "an", "of", "in", "on", "at", "to", "for", "and",
    "or", "by", "before", "after", "this", "that", "with", "from", "be",
    "is", "are", "do", "does", "did", "vs", "v",
}


def _keywords_from_question(question, k=3):
    if not question:
        return []
    words = re.findall(r"[A-Za-z][A-Za-z0-9]+", str(question).lower())
    out = []
    for w in words:
        if w in _STOPWORDS or len(w) < 3:
            continue
        if w not in out:
            out.append(w)
        if len(out) >= k:
            break
    return out


def news_heat_score(question, news_text):
    if news_text is None:
        return SCORE_FALLBACK
    text = str(news_text).lower()
    if not text:
        return 0.0
    kws = _keywords_from_question(question, k=3)
    if not kws:
        return 0.0
    hits = sum(text.count(k) for k in kws)
    return clip_map(hits, [(0, 0), (2, 40), (5, 70), (10, 90), (20, 100)])


def time_score(end_date_iso):
    """Score based on days until market end. 越远越高，过期 = 0。"""
    if not end_date_iso:
        return TIME_SCORE_FALLBACK
    try:
        s = str(end_date_iso).replace("Z", "+00:00")
        end_dt = datetime.fromisoformat(s)
    except Exception:
        return TIME_SCORE_FALLBACK
    from datetime import timezone
    now = datetime.now(end_dt.tzinfo or timezone.utc)
    delta_hours = (end_dt - now).total_seconds() / 3600.0
    if delta_hours <= 0:
        return 0.0
    # 0h -> 0, 24h -> 30, 7d -> 60, 30d -> 85, 180d -> 100
    return clip_map(delta_hours, [(0, 0), (24, 30), (168, 60), (720, 85), (4320, 100)])


def tradability_score(scores):
    """Weighted sum of 6 axes. Missing axes count as SCORE_FALLBACK."""
    s = scores or {}
    total = (
        WEIGHTS["liquidity"]  * float(s.get("liquidity_score",  SCORE_FALLBACK))
        + WEIGHTS["spread"]     * float(s.get("spread_score",     SCORE_FALLBACK))
        + WEIGHTS["activity"]   * float(s.get("activity_score",   SCORE_FALLBACK))
        + WEIGHTS["volatility"] * float(s.get("volatility_score", SCORE_FALLBACK))
        + WEIGHTS["news_heat"]  * float(s.get("news_heat_score",  SCORE_FALLBACK))
        + WEIGHTS["time"]       * float(s.get("time_score",       TIME_SCORE_FALLBACK))
    )
    return max(0.0, min(100.0, total))


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
