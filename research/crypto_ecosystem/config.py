"""Audit universe — Crypto Ecosystem Lead-Lag V0."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AuditSymbol:
    ticker: str
    layer: str
    longbridge_symbol: str | None
    yahoo_ticker: str | None
    local_json: str | None = None


AUDIT_SYMBOLS: list[AuditSymbol] = [
    AuditSymbol("BTC", "L1 Crypto", "BTCUSD.US", "BTC-USD", "BTC.json"),
    AuditSymbol("ETH", "L1 Crypto", "ETHUSD.US", "ETH-USD", "ETH.json"),
    AuditSymbol("SOL", "L1 Crypto", "SOLUSD.US", "SOL-USD", "SOL.json"),
    AuditSymbol("IBIT", "L2 Spot ETF", "IBIT.US", "IBIT", None),
    AuditSymbol("FBTC", "L2 Spot ETF", "FBTC.US", "FBTC", None),
    AuditSymbol("CP00048", "L3 Crypto Index", "CP00048.US", None, None),
    AuditSymbol("MSTR", "L4 Core Stock", "MSTR.US", "MSTR", None),
    AuditSymbol("COIN", "L4 Core Stock", "COIN.US", "COIN", None),
    AuditSymbol("CRCL", "L4 Core Stock", "CRCL.US", "CRCL", None),
    AuditSymbol("BLOK", "L5 Blockchain ETF", "BLOK.US", "BLOK", None),
    AuditSymbol("WGMI", "L5 Blockchain ETF", "WGMI.US", "WGMI", None),
]

LEAD_LAG_PAIRS: list[tuple[str, str]] = [
    ("BTC", "CP00048"),
    ("BTC", "MSTR"),
    ("BTC", "COIN"),
    ("BTC", "BLOK"),
    ("BTC", "WGMI"),
    ("CP00048", "MSTR"),
    ("CP00048", "COIN"),
]

LEAD_LAG_LAGS: tuple[int, ...] = (0, 1, 2, 3, 5)
