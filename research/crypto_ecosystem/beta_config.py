"""Beta Attribution universe — Crypto Ecosystem Research V0."""

from __future__ import annotations

DRIVERS: tuple[str, ...] = ("BTC", "ETH", "SOL")

# primary driver for main report
PRIMARY_DRIVER = "BTC"

RESPONSE_LAYER: tuple[str, ...] = (
    "CP00048",
    "MSTR",
    "COIN",
    "BLOK",
    "WGMI",
    "IBIT",
    "FBTC",
)

SPECIAL_REPORTS: tuple[str, ...] = ("MSTR", "COIN", "CP00048")

ROLLING_WINDOWS: tuple[int, ...] = (30, 60, 120)

EXTREME_THRESHOLDS: tuple[float, ...] = (0.03, 0.05, 0.08)

# Yahoo / local mapping (reuse audit universe)
SYMBOL_DATA: dict[str, dict] = {
    "BTC": {"yahoo": "BTC-USD", "local": "BTC.json"},
    "ETH": {"yahoo": "ETH-USD", "local": "ETH.json"},
    "SOL": {"yahoo": "SOL-USD", "local": "SOL.json"},
    "MSTR": {"yahoo": "MSTR"},
    "COIN": {"yahoo": "COIN"},
    "BLOK": {"yahoo": "BLOK"},
    "WGMI": {"yahoo": "WGMI"},
    "IBIT": {"yahoo": "IBIT"},
    "FBTC": {"yahoo": "FBTC"},
    "CP00048": {"longbridge": "CP00048.US"},
}
