"""
price_history — 市场价格历史读取 + 波动率/最高水位（Phase 3b）
============================================================================
事实源：data/market_price_history.json（由 datastore.record_market_prices 维护，
每市场滚动 cap 个点）。agent_p 读这里算波动率与真实最高水位，**不依赖旁路 DB**。

纯函数，沙箱可单测。
"""

from __future__ import annotations

import json
import statistics
from pathlib import Path
from typing import List, Optional

from _paths import get_base_dir

# 波动退出默认参数（可被 strategy_config 覆盖）
MIN_SAMPLES = 5          # 样本不足不触发，避免薄数据误判
DEFAULT_VOL_THRESHOLD = 0.08   # 近窗口价格变动 stddev 阈值


def load_history(base_dir=None) -> dict:
    base = Path(base_dir) if base_dir else get_base_dir()
    p = base / "data" / "market_price_history.json"
    if not p.exists():
        return {}
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def series_for(history: dict, market_id: str, field: str = "yes_price") -> List[float]:
    """取某市场的价格序列（过滤掉 None / 非数值）。"""
    out: List[float] = []
    for pt in history.get(str(market_id) or "", []) or []:
        v = pt.get(field)
        try:
            if v is not None:
                out.append(float(v))
        except (TypeError, ValueError):
            continue
    return out


def realized_volatility(series: List[float]) -> Optional[float]:
    """近窗口已实现波动 = 相邻价格变动的样本标准差。

    预测市场价格在 [0,1]，用绝对变动（非对数收益，价格可为 0）。
    样本不足返回 None。
    """
    if not series or len(series) < MIN_SAMPLES:
        return None
    diffs = [series[i] - series[i - 1] for i in range(1, len(series))]
    if len(diffs) < 2:
        return None
    try:
        return statistics.pstdev(diffs)
    except statistics.StatisticsError:
        return None


def high_water(series: List[float]) -> Optional[float]:
    return max(series) if series else None


def low_water(series: List[float]) -> Optional[float]:
    return min(series) if series else None


def should_volatility_exit(series: List[float],
                           threshold: float = DEFAULT_VOL_THRESHOLD) -> Optional[float]:
    """高波动制度判定：近窗口已实现波动 >= 阈值则返回该波动值（触发退出），否则 None。

    样本不足（<MIN_SAMPLES）一律 None —— 数据没攒够前绝不误触发。
    """
    vol = realized_volatility(series)
    if vol is None:
        return None
    return vol if vol >= threshold else None
