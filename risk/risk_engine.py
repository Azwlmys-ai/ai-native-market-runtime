"""
Minimal Risk Engine — P0 quantitative risk layer.

Outputs data/risk_snapshot.json each cycle.
Consumed by Agent M during signal review.

Implements:
  - rolling volatility (on available price data)
  - simple correlation matrix (Pearson)
  - exposure limit check (single asset / theme / total)
  - max drawdown placeholder
  - basic historical VaR (simple percentile, clearly labeled as fallback)
"""

import json
import math
from pathlib import Path
from datetime import datetime


class RiskEngine:
    def __init__(self, base_dir: Path):
        self.base_dir = Path(base_dir)
        self.data_dir = self.base_dir / "data"
        self.data_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _returns(series):
        if len(series) < 2:
            return []
        ret = []
        for i in range(1, len(series)):
            if series[i - 1] and series[i] and series[i - 1] != 0:
                ret.append((series[i] - series[i - 1]) / series[i - 1])
        return ret

    @staticmethod
    def _pearson(x, y):
        n = min(len(x), len(y))
        if n < 5:
            return None  # insufficient data
        x1 = x[:n]
        y1 = y[:n]
        mx = sum(x1) / n
        my = sum(y1) / n
        cov = sum((a - mx) * (b - my) for a, b in zip(x1, y1)) / (n - 1)
        sx = math.sqrt(sum((a - mx) ** 2 for a in x1) / (n - 1))
        sy = math.sqrt(sum((b - my) ** 2 for b in y1) / (n - 1))
        if sx == 0 or sy == 0:
            return None
        return cov / (sx * sy)

    @staticmethod
    def _historical_var(returns, confidence=0.95):
        """Simple historical VaR — clearly labeled as fallback."""
        if len(returns) < 10:
            return None
        sorted_ret = sorted(returns)
        idx = int(len(sorted_ret) * (1 - confidence))
        return sorted_ret[idx]

    # ------------------------------------------------------------------
    # data loading
    # ------------------------------------------------------------------

    def _load_price_series(self):
        """Load closing prices from available data files.
        Returns dict: {asset_key: [price, ...]}"""
        series = {}
        hist_dir = self.data_dir / "historical"

        # Polymarket latest data
        latest_file = self.data_dir / "latest_data.json"
        if latest_file.exists():
            try:
                ld = json.loads(latest_file.read_text())
                pm_markets = ld.get("polymarket_markets", ld.get("markets", []))
                for m in pm_markets:
                    slug = m.get("slug", "")
                    price = m.get("price") or m.get("outcome_price")
                    if slug and price is not None:
                        key = f"pm:{slug}"
                        if key not in series:
                            series[key] = []
                        series[key].append(float(price))
            except Exception:
                pass

        # Historical JSON files
        for fname in ["okx_klines_march_april_2026.json",
                      "us_stocks_march_april_2026.json",
                      "commodities_march_april_2026.json"]:
            fpath = hist_dir / fname
            if not fpath.exists():
                continue
            try:
                data = json.loads(fpath.read_text())
                for symbol, info in data.items():
                    prices = []
                    raw = info.get("data", []) if isinstance(info, dict) else (info if isinstance(info, list) else [])
                    for d in raw:
                        close = d.get("close", d.get("c", None))
                        if close is not None:
                            prices.append(float(close))
                    if prices:
                        series[fname.split("_")[0] + ":" + symbol] = prices
            except Exception:
                pass

        return series

    # ------------------------------------------------------------------
    # risk calculations
    # ------------------------------------------------------------------

    def calc_volatility(self, price_series):
        """Rolling volatility per asset."""
        vol = {}
        for asset, prices in price_series.items():
            ret = self._returns(prices)
            if len(ret) < 5:
                vol[asset] = {"volatility": None, "periods": len(ret), "status": "insufficient_data"}
                continue
            mean_ret = sum(ret) / len(ret)
            var = sum((r - mean_ret) ** 2 for r in ret) / (len(ret) - 1)
            ann_vol = math.sqrt(var) * math.sqrt(365) if var > 0 else 0.0
            vol[asset] = {
                "volatility_daily": round(math.sqrt(var), 6),
                "volatility_annualized": round(ann_vol, 4),
                "periods": len(ret),
                "status": "ok",
            }
        return vol

    def calc_correlations(self, price_series):
        """Pairwise Pearson correlation for assets with sufficient data."""
        pairs = []
        assets = list(price_series.keys())
        for i in range(len(assets)):
            for j in range(i + 1, len(assets)):
                r1 = self._returns(price_series[assets[i]])
                r2 = self._returns(price_series[assets[j]])
                if len(r1) < 10 or len(r2) < 10:
                    continue
                corr = self._pearson(r1, r2)
                if corr is not None and abs(corr) > 0.3:
                    pairs.append({"a": assets[i], "b": assets[j], "pearson": round(corr, 4)})
        pairs.sort(key=lambda x: abs(x["pearson"]), reverse=True)
        return pairs[:20]

    def check_exposure(self):
        """Check exposure limits from positions and approved signals."""
        limits = {
            "max_single_asset_pct": 0.20,
            "max_single_theme_pct": 0.30,
            "max_total_exposure_pct": 0.80,
        }
        exposures = {
            "positions_count": 0,
            "by_asset": {},
            "violations": [],
        }

        by_theme = {}
        total_exposure = 0.0

        pos_file = self.data_dir / "positions.json"
        if pos_file.exists():
            try:
                positions = json.loads(pos_file.read_text())
                exposures["positions_count"] = len(positions)
                for p in positions:
                    slug = p.get("market_slug", p.get("slug", "unknown"))
                    size = self._position_exposure_usd(p)
                    theme = self._theme_key(p)
                    if slug not in exposures["by_asset"]:
                        exposures["by_asset"][slug] = 0.0
                    exposures["by_asset"][slug] += size
                    by_theme[theme] = by_theme.get(theme, 0.0) + size
                    total_exposure += size
                    if exposures["by_asset"][slug] > limits["max_single_asset_pct"] * 10000:
                        exposures["violations"].append({
                            "type": "single_asset_exposure",
                            "asset": slug,
                            "value": round(exposures["by_asset"][slug], 2),
                            "limit": limits["max_single_asset_pct"],
                        })
            except Exception:
                pass

        for theme, value in sorted(by_theme.items()):
            if value > limits["max_single_theme_pct"] * 10000:
                exposures["violations"].append({
                    "type": "single_theme_exposure",
                    "theme": theme,
                    "value": round(value, 2),
                    "limit": limits["max_single_theme_pct"],
                })

        if total_exposure > limits["max_total_exposure_pct"] * 10000:
            exposures["violations"].append({
                "type": "total_exposure",
                "value": round(total_exposure, 2),
                "limit": limits["max_total_exposure_pct"],
            })

        exposures["by_asset"] = {k: round(v, 2) for k, v in exposures["by_asset"].items()}
        exposures["by_theme"] = {k: round(v, 2) for k, v in sorted(by_theme.items())}
        exposures["total_exposure"] = round(total_exposure, 2)
        exposures["limits"] = limits
        return exposures

    @staticmethod
    def _position_exposure_usd(position):
        """Return USD exposure for both old signal-style and pm-trader position rows."""
        for key in ("current_value", "total_cost", "amount_usd", "position_size"):
            value = position.get(key)
            if value in (None, ""):
                continue
            try:
                value = float(value)
            except (TypeError, ValueError):
                continue
            if value > 0:
                return value
        return 0.0

    @staticmethod
    def _theme_key(position):
        text = " ".join([
            str(position.get("market_question", "")),
            str(position.get("market_slug", "")),
            str(position.get("market_name", "")),
        ]).lower()

        if "2028" in text and "democratic" in text and "presidential" in text:
            return "2028_democratic_presidential_nomination"
        if "nhl stanley cup" in text:
            return "nhl_stanley_cup"
        if "nba finals" in text:
            return "nba_finals"
        if "gta vi" in text:
            return "gta_vi_related"
        return position.get("market_slug", position.get("slug", "unknown"))

    def calc_var_placeholder(self, price_series):
        """Basic VaR with fallback label."""
        all_returns = []
        for prices in price_series.values():
            ret = self._returns(prices)
            all_returns.extend(ret)

        var95 = self._historical_var(all_returns, confidence=0.95)
        if var95 is None:
            return {
                "method": "historical_simple",
                "confidence": 0.95,
                "VaR_95": None,
                "status": "insufficient_data_fallback",
                "label": "SIMPLE_HISTORICAL_VAR_FALLBACK — not a full risk model",
            }

        return {
            "method": "historical_simple",
            "confidence": 0.95,
            "VaR_95_daily": round(var95, 6),
            "VaR_95_annualized_approx": round(var95 * math.sqrt(365), 4),
            "sample_size": len(all_returns),
            "status": "ok",
            "label": "SIMPLE_HISTORICAL_VAR_FALLBACK — not a full risk model",
        }

    def calc_max_drawdown_placeholder(self, price_series):
        """Max drawdown on available series."""
        dd = {}
        for asset, prices in price_series.items():
            if len(prices) < 5:
                dd[asset] = None
                continue
            peak = prices[0]
            max_dd = 0.0
            for p in prices:
                if p > peak:
                    peak = p
                if peak == 0:
                    continue
                dd_val = (p - peak) / peak
                if dd_val < max_dd:
                    max_dd = dd_val
            dd[asset] = round(max_dd, 4)
        return dd

    # ------------------------------------------------------------------
    # main
    # ------------------------------------------------------------------

    def run(self):
        price_series = self._load_price_series()
        has_data = bool(price_series)

        vol = self.calc_volatility(price_series) if has_data else {}
        corr = self.calc_correlations(price_series) if has_data else []
        exposure = self.check_exposure()
        var_result = self.calc_var_placeholder(price_series) if has_data else {}
        max_dd = self.calc_max_drawdown_placeholder(price_series) if has_data else {}

        snapshot = {
            "timestamp": datetime.now().isoformat(),
            "data_available": has_data,
            "asset_count": len(price_series),
            "volatility": vol,
            "correlations": corr,
            "exposure": exposure,
            "var": var_result if var_result else {"status": "no_data", "label": "SIMPLE_HISTORICAL_VAR_FALLBACK"},
            "max_drawdown": max_dd,
            "_note": "Minimal P0 risk layer. Markov/HMM/Monte-Carlo/Bayesian not implemented.",
        }

        output_file = self.data_dir / "risk_snapshot.json"
        with open(output_file, "w") as f:
            json.dump(snapshot, f, indent=2, ensure_ascii=False)

        print(f"[RiskEngine] risk_snapshot.json written — {len(price_series)} assets, data_available={has_data}")
        return output_file


def main():
    from _paths import get_base_dir
    engine = RiskEngine(get_base_dir())
    engine.run()


if __name__ == "__main__":
    main()
