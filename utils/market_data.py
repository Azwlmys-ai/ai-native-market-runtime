"""Helpers for reading normalized market data snapshots."""


def normalize_polymarket_market(market):
    """Return a copy with legacy yes_price/no_price fields populated."""
    item = dict(market)
    prices = item.get("outcome_prices") or item.get("prices") or []
    outcomes = item.get("outcomes") or []

    if "yes_price" not in item or "no_price" not in item:
        try:
            yes_index = next(
                (i for i, outcome in enumerate(outcomes) if str(outcome).upper() == "YES"),
                0,
            )
            no_index = next(
                (i for i, outcome in enumerate(outcomes) if str(outcome).upper() == "NO"),
                1,
            )
            item.setdefault("yes_price", float(prices[yes_index]))
            item.setdefault("no_price", float(prices[no_index]))
        except (IndexError, TypeError, ValueError):
            pass

    return item


def get_polymarket_markets(data):
    markets = data.get("markets")
    if markets is None:
        markets = data.get("polymarket_markets", [])
    if not isinstance(markets, list):
        return []
    return [normalize_polymarket_market(market) for market in markets]


def get_okx_btc_context(data):
    okx_data = data.get("okx", {})
    coins = okx_data.get("data", []) if isinstance(okx_data, dict) else []
    btc = next((item for item in coins if item.get("symbol") == "BTC"), {})

    btc_price = data.get("btc_price") or btc.get("spot_price")
    funding_rate = data.get("okx_funding_rate")
    if funding_rate is None:
        funding_rate = data.get("btc_funding_rate")
    if funding_rate is None:
        funding_rate = btc.get("funding_rate")

    return btc_price, funding_rate
