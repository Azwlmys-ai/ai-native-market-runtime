"""Cross Market Research V0 — factor & target definitions."""

from __future__ import annotations

# Global factor composites (equal-weight daily returns)
FACTORS: dict[str, dict] = {
    "Factor_A": {
        "name": "AI Composite",
        "symbols": {"NVDA": "NVDA", "AMD": "AMD", "MSFT": "MSFT", "AMZN": "AMZN", "GOOGL": "GOOGL"},
        "category": "equity_us",
    },
    "Factor_B": {
        "name": "Semiconductor Composite",
        "symbols": {"SOXX": "SOXX", "TSM": "TSM", "ASML": "ASML"},
        "category": "equity_us",
    },
    "Factor_C": {
        "name": "Crypto Composite",
        "symbols": {"BTC": "BTC-USD", "ETH": "ETH-USD", "SOL": "SOL-USD"},
        "category": "crypto",
    },
    "Factor_D": {
        "name": "Commodity Composite",
        "symbols": {"Gold": "GC=F", "Oil": "CL=F", "Copper": "HG=F"},
        "category": "commodity",
    },
    "Factor_E": {
        "name": "Dollar Factor",
        "symbols": {"DXY": "DX-Y.NYB"},
        "category": "macro",
    },
    "Factor_F": {
        "name": "Rates Factor",
        "symbols": {"US10Y": "^TNX", "US2Y": "^IRX"},
        "category": "macro",
    },
}

# Research targets — indices only (phase 1)
US_TARGETS: dict[str, str] = {
    "QQQ": "QQQ",
    "SPY": "SPY",
    "SOXX": "SOXX",
}

CN_TARGETS: dict[str, dict] = {
    "000001": {"name": "上证指数", "source": "a_share_or_fetch", "baostock": "sh.000001"},
    "399001": {"name": "深成指", "source": "fetch", "baostock": "sz.399001", "akshare": "sz399001"},
    "399006": {"name": "创业板指", "source": "a_share_or_fetch", "baostock": "sz.399006"},
    "000300": {"name": "沪深300", "source": "fetch", "baostock": "sh.000300", "akshare": "sh000300"},
}

# P0 macro series stored under history/macro/
MACRO_SERIES: dict[str, str] = {
    "DXY": "DX-Y.NYB",
    "US10Y": "^TNX",
    "US2Y": "^IRX",
}

# P0 China flow
NORTHBOUND_KEY = "northbound"

# Lead-lag pairs to test (factor_or_macro -> target)
RESEARCH_QUESTIONS: list[dict] = [
    {"id": "Q1", "driver": "DXY", "target": "000001", "question": "DXY 是否真的影响 A股？"},
    {"id": "Q2", "driver": "US10Y", "target": "399006", "question": "US10Y 是否真的影响成长股？"},
    {"id": "Q3", "driver": "BTC", "target": "QQQ", "question": "BTC 是否领先 QQQ？"},
    {"id": "Q4", "driver": "Factor_A", "target": "399006", "question": "AI Composite 是否领先创业板？"},
    {"id": "Q5", "driver": "SOXX", "target": "000300", "question": "SOXX 是否领先沪深300？"},
    {"id": "Q6", "driver": "northbound", "target": "000001", "question": "北向资金是否具有预测能力？"},
]
