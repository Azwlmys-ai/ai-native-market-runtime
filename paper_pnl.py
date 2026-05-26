"""
Paper P&L Tracker — Minimal portfolio + trade history recorder.

This module is imported by signal_executor, sell_executor, and orchestrator
in dry-run mode.  It records every paper trade to data/paper_trades.jsonl
and maintains current positions in data/paper_portfolio.json.

No complex PnL, no real-time mark-to-market, no equity curve, no UI.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from _paths import get_base_dir

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
DEFAULT_ACCOUNT_BALANCE = 10_000  # USD virtual account principal
ENTRY_PRICE_DEFAULT = 0.50        # fallback entry price when signal has none

# ---------------------------------------------------------------------------
# PaperPosition — a single virtual position
# ---------------------------------------------------------------------------
@dataclass
class PaperPosition:
    market_id: str
    market_name: str
    direction: str            # "YES" or "NO"
    entry_price: float
    position_size: float      # 0.01 – 1.0
    notional_usd: float
    opened_at: str            # ISO-8601
    source: str = ""
    closed_at: str = ""
    realized_pnl: float = 0.0
    synthetic: bool = True
    dry_run: bool = True

    @staticmethod
    def from_signal(signal: dict) -> PaperPosition:
        direction = (signal.get("direction") or "").upper() or "YES"
        price = signal.get("price")
        if price is None or not isinstance(price, (int, float)) or price <= 0:
            price = ENTRY_PRICE_DEFAULT
        ps = signal.get("position_size", 0.10)
        try:
            ps = float(ps)
        except (TypeError, ValueError):
            ps = 0.10
        if ps <= 0:
            ps = 0.10
        notional = round(DEFAULT_ACCOUNT_BALANCE * ps, 2)
        return PaperPosition(
            market_id=str(signal.get("market_id", "")),
            market_name=str(signal.get("market_name", "")),
            direction=direction,
            entry_price=float(price),
            position_size=ps,
            notional_usd=notional,
            opened_at=datetime.now(timezone.utc).isoformat(),
            source=str(signal.get("source", "")),
        )

    def to_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_dict(d: dict) -> PaperPosition:
        return PaperPosition(**{
            k: d[k]
            for k in [
                "market_id", "market_name", "direction", "entry_price",
                "position_size", "notional_usd", "opened_at", "source",
                "closed_at", "realized_pnl", "synthetic", "dry_run",
            ]
            if k in d
        })


# ---------------------------------------------------------------------------
# PaperPortfolio — portfolio manager
# ---------------------------------------------------------------------------
class PaperPortfolio:
    def __init__(self, base_dir: Optional[Path] = None):
        self.base_dir = Path(base_dir) if base_dir else get_base_dir()
        self.data_dir = self.base_dir / "data"
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.portfolio_file = self.data_dir / "paper_portfolio.json"
        self.trades_file = self.data_dir / "paper_trades.jsonl"

        self.positions: list[PaperPosition] = []
        self._load()

    # ---- persistence ----
    def _load(self):
        if self.portfolio_file.exists():
            try:
                with open(self.portfolio_file) as f:
                    raw = json.load(f)
                self.positions = [PaperPosition.from_dict(d) for d in raw]
            except Exception:
                self.positions = []

    def _save(self):
        with open(self.portfolio_file, "w") as f:
            json.dump(
                [p.to_dict() for p in self.positions],
                f,
                indent=2,
                ensure_ascii=False,
            )

    def _record_trade(self, trade: dict):
        """Append one trade record to the paper_trades.jsonl file."""
        with open(self.trades_file, "a") as f:
            json.dump(trade, f, ensure_ascii=False)
            f.write("\n")

    # ---- operations ----
    def open_position(self, signal: dict) -> PaperPosition:
        """Record a virtual BUY in paper_trades.jsonl + portfolio."""
        pos = PaperPosition.from_signal(signal)
        self.positions.append(pos)
        self._save()

        # record trade history
        self._record_trade({
            "ts": pos.opened_at,
            "type": "open",
            "market_id": pos.market_id,
            "side": pos.direction,
            "entry_price": pos.entry_price,
            "size": pos.position_size,
            "notional_usd": pos.notional_usd,
            "source": pos.source,
        })

        print(
            f"[PaperP&L] OPEN  {pos.direction} {pos.market_name[:60]} "
            f"@{pos.entry_price:.3f} size={pos.position_size:.0%} "
            f"notional=${pos.notional_usd:.0f}"
        )
        return pos

    def close_position(self, sell_signal: dict) -> Optional[PaperPosition]:
        """Match and close a position; record in paper_trades.jsonl."""
        market_id = str(
            sell_signal.get("market_id")
            or sell_signal.get("market")
            or ""
        )
        direction = (
            str(sell_signal.get("outcome") or sell_signal.get("token_id") or "")
            .upper()
        )
        exit_price = sell_signal.get("price")
        if (
            exit_price is None
            or not isinstance(exit_price, (int, float))
            or exit_price <= 0
        ):
            exit_price = ENTRY_PRICE_DEFAULT
        exit_price = float(exit_price)

        # find earliest matching open position
        for pos in self.positions:
            if (
                not pos.closed_at
                and pos.market_id == market_id
                and pos.direction == direction
            ):
                pos.closed_at = datetime.now(timezone.utc).isoformat()
                pos.realized_pnl = self._calc_realized_pnl(pos, exit_price)
                self._save()

                self._record_trade({
                    "ts": pos.closed_at,
                    "type": "close",
                    "market_id": pos.market_id,
                    "side": pos.direction,
                    "entry_price": pos.entry_price,
                    "exit_price": exit_price,
                    "size": pos.position_size,
                    "notional_usd": pos.notional_usd,
                    "realized_pnl": pos.realized_pnl,
                    "source": pos.source,
                })

                print(
                    f"[PaperP&L] CLOSE {pos.direction} {pos.market_name[:60]} "
                    f"realized_pnl=${pos.realized_pnl:+.2f}"
                )
                return pos

        # unmatched sell — record for audit
        fallback = PaperPosition(
            market_id=market_id,
            market_name=str(sell_signal.get("market_name") or ""),
            direction=direction,
            entry_price=exit_price,
            position_size=0.0,
            notional_usd=0.0,
            opened_at=datetime.now(timezone.utc).isoformat(),
            source="sell_executor_unmatched",
            closed_at=datetime.now(timezone.utc).isoformat(),
            realized_pnl=0.0,
        )
        self.positions.append(fallback)
        self._save()
        self._record_trade({
            "ts": fallback.opened_at,
            "type": "unmatched_sell",
            "market_id": market_id,
            "side": direction,
            "entry_price": exit_price,
            "size": 0.0,
            "notional_usd": 0.0,
            "source": "sell_executor_unmatched",
        })
        print(
            f"[PaperP&L] UNMATCHED SELL {market_id} "
            f"no open position found; logged for audit"
        )
        return None

    @staticmethod
    def _calc_realized_pnl(pos: PaperPosition, exit_price: float) -> float:
        if pos.entry_price <= 0:
            return 0.0
        if pos.direction == "NO":
            return round(
                (pos.entry_price - exit_price)
                * pos.notional_usd
                / pos.entry_price,
                4,
            )
        return round(
            (exit_price - pos.entry_price)
            * pos.notional_usd
            / pos.entry_price,
            4,
        )

    def get_open_positions(self) -> list[PaperPosition]:
        return [p for p in self.positions if not p.closed_at]

    def get_summary(self) -> dict:
        open_pos = self.get_open_positions()
        closed_pos = [p for p in self.positions if p.closed_at]
        realized = sum(p.realized_pnl for p in closed_pos)
        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "open_positions": len(open_pos),
            "closed_positions": len(closed_pos),
            "realized_pnl": round(realized, 4),
            "total_positions": len(self.positions),
        }

    def snapshot(self) -> dict:
        summary = self.get_summary()
        history_file = self.data_dir / "paper_pnl_history.jsonl"
        with open(history_file, "a") as f:
            json.dump(summary, f, ensure_ascii=False)
            f.write("\n")
        return summary

    def report(self) -> str:
        s = self.get_summary()
        return (
            f"[PaperP&L] open={s['open_positions']} "
            f"closed={s['closed_positions']} "
            f"realized=${s['realized_pnl']:+.2f} "
            f"total_positions={s['total_positions']}"
        )


# ---------------------------------------------------------------------------
# Convenience singleton
# ---------------------------------------------------------------------------
_GLOBAL_PORTFOLIO: Optional[PaperPortfolio] = None


def get_paper_portfolio() -> PaperPortfolio:
    global _GLOBAL_PORTFOLIO
    if _GLOBAL_PORTFOLIO is None:
        _GLOBAL_PORTFOLIO = PaperPortfolio()
    return _GLOBAL_PORTFOLIO


def main():
    pp = PaperPortfolio()
    print("=== Paper Portfolio Current ===")
    print(pp.report())
    print()
    print(json.dumps(pp.get_summary(), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()