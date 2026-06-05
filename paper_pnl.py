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
    market_slug: str = ""
    slug: str = ""
    market: str = ""
    question: str = ""
    title: str = ""
    market_aliases: list[str] = None
    closed_at: str = ""
    exit_price: Optional[float] = None
    price_source: str = ""
    realized_pnl: Optional[float] = 0.0
    close_reason: str = ""
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
        market_slug = str(
            signal.get("market_slug")
            or signal.get("slug")
            or signal.get("market_evidence", {}).get("market_slug")
            or ""
        )
        market = str(signal.get("market") or market_slug or "")
        question = str(
            signal.get("question")
            or signal.get("market_question")
            or signal.get("market_name")
            or signal.get("title")
            or ""
        )
        aliases = _dedupe_strings([
            market_slug,
            signal.get("slug"),
            market,
            signal.get("market_id"),
            signal.get("market_evidence", {}).get("market_slug"),
        ])
        return PaperPosition(
            market_id=str(signal.get("market_id", "")),
            market_name=str(signal.get("market_name") or question),
            direction=direction,
            entry_price=float(price),
            position_size=ps,
            notional_usd=notional,
            opened_at=datetime.now(timezone.utc).isoformat(),
            source=str(signal.get("source", "")),
            market_slug=market_slug,
            slug=market_slug,
            market=market,
            question=question,
            title=str(signal.get("title") or ""),
            market_aliases=aliases,
        )

    def to_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_dict(d: dict) -> PaperPosition:
        allowed = [
            "market_id", "market_name", "direction", "entry_price",
            "position_size", "notional_usd", "opened_at", "source",
            "market_slug", "slug", "market", "question", "title",
            "market_aliases", "closed_at", "exit_price", "price_source",
            "realized_pnl", "close_reason", "synthetic", "dry_run",
        ]
        data = {
            k: d[k]
            for k in allowed
            if k in d
        }
        if data.get("market_aliases") is None:
            data["market_aliases"] = []
        return PaperPosition(**data)

    def __post_init__(self):
        if self.market_aliases is None:
            self.market_aliases = []


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
        # Phase 0 写入收敛：经 runtime.datastore 门面落盘（json 输出逐字节不变：indent=2, ensure_ascii=False）
        from runtime import datastore as _ds
        _ds.save_portfolio([p.to_dict() for p in self.positions], base_dir=self.base_dir)

    def _record_trade(self, trade: dict):
        """Append one trade record to the paper_trades.jsonl file（经 datastore 门面）。"""
        from runtime import datastore as _ds
        _ds.append_paper_trade(trade, base_dir=self.base_dir)

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
            "market_slug": pos.market_slug,
            "market": pos.market,
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
        direction = _normalize_direction(
            sell_signal.get("outcome")
            or sell_signal.get("token_id")
            or sell_signal.get("direction")
        )
        exit_price, price_source = self._resolve_exit_price(sell_signal, direction)

        # find earliest matching open position
        for pos in self.positions:
            if (
                not pos.closed_at
                and self._position_matches_sell(pos, sell_signal)
                and pos.direction == direction
            ):
                pos.closed_at = datetime.now(timezone.utc).isoformat()
                pos.exit_price = exit_price
                pos.price_source = price_source
                pos.close_reason = str(sell_signal.get("reason") or "sell_executed")
                if exit_price is None:
                    pos.realized_pnl = None
                    print(
                        "[PaperP&L] WARNING missing exit price; "
                        "closed position without realized PnL"
                    )
                else:
                    pos.realized_pnl = self._calc_realized_pnl(pos, exit_price)
                self._save()

                self._record_trade({
                    "ts": pos.closed_at,
                    "type": "close",
                    "market_id": pos.market_id,
                    "market_slug": pos.market_slug,
                    "market": pos.market,
                    "market_name": pos.market_name,
                    "side": pos.direction,
                    "entry_price": pos.entry_price,
                    "exit_price": exit_price,
                    "price_source": price_source,
                    "size": pos.position_size,
                    "notional_usd": pos.notional_usd,
                    "realized_pnl": pos.realized_pnl,
                    "close_reason": pos.close_reason,
                    "source": pos.source,
                })

                if pos.realized_pnl is None:
                    print(
                        f"[PaperP&L] CLOSE {pos.direction} {pos.market_name[:60]} "
                        "realized_pnl=missing"
                    )
                else:
                    print(
                        f"[PaperP&L] CLOSE {pos.direction} {pos.market_name[:60]} "
                        f"realized_pnl=${pos.realized_pnl:+.2f}"
                    )
                return pos

        # --- Fallback: synthesise position from positions.json snapshot ---
        # Handles markets that were tracked by Agent P (positions.json) but
        # never explicitly opened through signal_executor (paper_portfolio.json).
        sell_slug = _norm_key(
            sell_signal.get("market_slug")
            or sell_signal.get("slug")
            or sell_signal.get("market")
        )
        synth = self._synthesise_position_from_snapshot(sell_signal, sell_slug, direction)
        if synth is not None:
            synth.closed_at = datetime.now(timezone.utc).isoformat()
            synth.exit_price = exit_price
            synth.price_source = price_source
            synth.close_reason = str(sell_signal.get("reason") or "sell_executed")
            if exit_price is None:
                synth.realized_pnl = None
            else:
                synth.realized_pnl = self._calc_realized_pnl(synth, exit_price)
            self.positions.append(synth)
            self._save()
            self._record_trade({
                "ts": synth.closed_at,
                "type": "close",
                "market_id": synth.market_id,
                "market_slug": synth.market_slug,
                "market": synth.market,
                "market_name": synth.market_name,
                "side": synth.direction,
                "entry_price": synth.entry_price,
                "exit_price": exit_price,
                "price_source": price_source,
                "size": synth.position_size,
                "notional_usd": synth.notional_usd,
                "realized_pnl": synth.realized_pnl,
                "close_reason": synth.close_reason,
                "source": synth.source,
                "note": "synthesised_from_positions_snapshot",
            })
            print(
                f"[PaperP&L] CLOSE(synth) {synth.direction} {synth.market_name[:60]} "
                f"realized_pnl=${synth.realized_pnl:+.2f}"
                if synth.realized_pnl is not None
                else f"[PaperP&L] CLOSE(synth) {synth.direction} {synth.market_name[:60]} realized_pnl=missing"
            )
            return synth

        market_ref = _first_string(
            sell_signal.get("market_id"),
            sell_signal.get("market_slug"),
            sell_signal.get("slug"),
            sell_signal.get("market"),
        )
        self._record_trade({
            "ts": datetime.now(timezone.utc).isoformat(),
            "type": "unmatched_sell",
            "market_id": str(sell_signal.get("market_id") or ""),
            "market_slug": str(
                sell_signal.get("market_slug")
                or sell_signal.get("slug")
                or sell_signal.get("market")
                or ""
            ),
            "side": direction,
            "exit_price": exit_price,
            "price_source": price_source,
            "size": 0.0,
            "notional_usd": 0.0,
            "source": "sell_executor_unmatched",
        })
        print(
            f"[PaperP&L] UNMATCHED SELL {market_ref} "
            "no open position found; logged for audit only"
        )
        return None

    def _synthesise_position_from_snapshot(
        self, sell_signal: dict, sell_slug: str, direction: str
    ) -> "Optional[PaperPosition]":
        """
        Build a synthetic PaperPosition from positions.json data when no
        corresponding open paper position exists.  Used as a last-resort in
        close_position so that Agent-P stop-loss signals for markets that were
        never opened through signal_executor can still be settled in the paper
        portfolio.
        """
        positions_file = self.data_dir / "positions.json"
        if not positions_file.exists():
            return None
        try:
            with open(positions_file) as f:
                snapshot = json.load(f)
        except Exception:
            return None

        norm_slug = _norm_key(sell_slug).lower()
        norm_dir = direction.upper()
        for entry in snapshot:
            if not isinstance(entry, dict):
                continue
            if _norm_key(entry.get("market_slug", "")).lower() != norm_slug:
                continue
            entry_outcome = _normalize_direction(entry.get("outcome", ""))
            if entry_outcome and entry_outcome != norm_dir:
                continue
            # Build a synthetic position closed immediately
            avg_entry = entry.get("avg_entry_price") or ENTRY_PRICE_DEFAULT
            try:
                avg_entry = float(avg_entry)
            except (TypeError, ValueError):
                avg_entry = ENTRY_PRICE_DEFAULT
            total_cost = entry.get("total_cost") or 0.0
            try:
                total_cost = float(total_cost)
            except (TypeError, ValueError):
                total_cost = 0.0
            if total_cost <= 0:
                total_cost = DEFAULT_ACCOUNT_BALANCE * 0.10
            question = str(entry.get("market_question") or entry.get("question") or sell_slug)
            return PaperPosition(
                market_id=str(sell_signal.get("market_id") or sell_slug),
                market_name=question,
                direction=norm_dir,
                entry_price=avg_entry,
                position_size=round(total_cost / DEFAULT_ACCOUNT_BALANCE, 4),
                notional_usd=round(total_cost, 2),
                opened_at=datetime.now(timezone.utc).isoformat(),
                source="positions_snapshot",
                market_slug=sell_slug,
                slug=sell_slug,
                market=sell_slug,
                question=question,
                market_aliases=[sell_slug],
                synthetic=True,
                dry_run=True,
            )
        return None

    def _position_matches_sell(self, pos: PaperPosition, sell_signal: dict) -> bool:
        sell_market_id = _norm_key(sell_signal.get("market_id"))
        if sell_market_id and _norm_key(pos.market_id) == sell_market_id:
            return True

        sell_slug = _norm_key(
            sell_signal.get("market_slug")
            or sell_signal.get("slug")
            or sell_signal.get("market")
        )
        if sell_slug:
            for value in (pos.market_slug, pos.slug, pos.market):
                if _norm_key(value) == sell_slug:
                    return True
            if sell_slug in {_norm_key(alias) for alias in pos.market_aliases}:
                return True

            # Try 3: slug → positions.json market_question → pos.market_name
            # Handles the common case where open positions only have numeric
            # market_id (e.g. "540844") while sell signals only carry the slug
            # (e.g. "will-bitcoin-hit-1m-before-gta-vi-872").
            market_question = self._slug_to_market_question(sell_slug)
            if market_question:
                if _norm_key(market_question).lower() == _norm_key(pos.market_name).lower():
                    return True

        return False

    def _slug_to_market_question(self, slug: str) -> Optional[str]:
        """
        Look up market_question from data/positions.json using market_slug.
        Agent P writes positions.json with both slug and market_question fields,
        giving us the slug ↔ human-readable name bridge.
        """
        positions_file = self.data_dir / "positions.json"
        if not positions_file.exists():
            return None
        try:
            with open(positions_file) as f:
                snapshot = json.load(f)
        except Exception:
            return None
        norm_slug = _norm_key(slug).lower()
        for entry in snapshot:
            if not isinstance(entry, dict):
                continue
            if _norm_key(entry.get("market_slug", "")).lower() == norm_slug:
                q = entry.get("market_question") or entry.get("question") or ""
                if q:
                    return str(q)
        return None

    def _resolve_exit_price(
        self, sell_signal: dict, direction: str
    ) -> tuple[Optional[float], str]:
        for key in (
            "price", "exit_price", "current_price", "live_price",
            "mid", "mid_price", "best_bid", "bid", "best_ask", "ask",
        ):
            price = _valid_price(sell_signal.get(key))
            if price is not None:
                return price, key

        nested_price = self._price_from_nested_signal(sell_signal)
        if nested_price is not None:
            return nested_price

        latest_price = self._price_from_latest_data(sell_signal, direction)
        if latest_price is not None:
            return latest_price

        print("[PaperP&L] WARNING missing exit price; not defaulting to 0.5")
        return None, "missing"

    def _price_from_nested_signal(
        self, sell_signal: dict
    ) -> Optional[tuple[float, str]]:
        for parent_key in ("signal", "market_evidence", "quote"):
            nested = sell_signal.get(parent_key)
            if not isinstance(nested, dict):
                continue
            for key in (
                "price", "exit_price", "current_price", "live_price",
                "mid", "mid_price", "best_bid", "bid", "best_ask", "ask",
            ):
                price = _valid_price(nested.get(key))
                if price is not None:
                    return price, f"{parent_key}.{key}"
        return None

    def _price_from_latest_data(
        self, sell_signal: dict, direction: str
    ) -> Optional[tuple[float, str]]:
        latest_file = self.data_dir / "latest_data.json"
        if not latest_file.exists():
            return None
        try:
            with open(latest_file) as f:
                latest = json.load(f)
        except Exception:
            return None

        markets = latest.get("polymarket_markets") or []
        sell_ids = {
            _norm_key(sell_signal.get("market_id")),
            _norm_key(sell_signal.get("market_slug")),
            _norm_key(sell_signal.get("slug")),
            _norm_key(sell_signal.get("market")),
        }
        sell_ids.discard("")
        for market in markets:
            if not isinstance(market, dict):
                continue
            market_ids = {
                _norm_key(market.get("id")),
                _norm_key(market.get("market_id")),
                _norm_key(market.get("slug")),
                _norm_key(market.get("market_slug")),
            }
            if not sell_ids.intersection(market_ids):
                continue
            price = _price_from_market_outcomes(market, direction)
            if price is not None:
                return price, "latest_data.outcome_prices"
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
        realized = sum(p.realized_pnl for p in closed_pos if p.realized_pnl is not None)
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


def _norm_key(value) -> str:
    return str(value or "").strip()


def _first_string(*values) -> str:
    for value in values:
        text = _norm_key(value)
        if text:
            return text
    return ""


def _dedupe_strings(values) -> list[str]:
    seen = set()
    output = []
    for value in values:
        text = _norm_key(value)
        if text and text not in seen:
            seen.add(text)
            output.append(text)
    return output


def _normalize_direction(value) -> str:
    direction = str(value or "").upper()
    if direction in ("BUY_NO", "NO"):
        return "NO"
    if direction in ("BUY_YES", "YES"):
        return "YES"
    return direction


def _valid_price(value) -> Optional[float]:
    try:
        price = float(value)
    except (TypeError, ValueError):
        return None
    if price <= 0:
        return None
    return price


def _price_from_market_outcomes(market: dict, direction: str) -> Optional[float]:
    outcomes = market.get("outcomes") or []
    prices = market.get("outcome_prices") or []
    if isinstance(outcomes, str):
        try:
            outcomes = json.loads(outcomes)
        except Exception:
            outcomes = []
    if isinstance(prices, str):
        try:
            prices = json.loads(prices)
        except Exception:
            prices = []
    for index, outcome in enumerate(outcomes):
        if str(outcome).upper() == direction and index < len(prices):
            return _valid_price(prices[index])
    return None


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
