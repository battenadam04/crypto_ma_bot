import requests

def fetch_market_caps(min_market_cap_usd=1_000_000_000):
    """
    Return {BASE_SYMBOL_UPPER: market_cap_usd} for CoinGecko top ~250 coins by market cap.

    Used by get_top_tradable_pairs / Phemex discovery as a *quality filter* (large-cap bases only),
    not as the volume source — 24h volume still comes from the exchange. Set
    BACKTEST_COINGECKO_MIN_CAP=0 to skip this filter and rank by volume only.
    """
    url = 'https://api.coingecko.com/api/v3/coins/markets'
    params = {
        'vs_currency': 'usd',
        'order': 'market_cap_desc',
        'per_page': 250,
        'page': 1
    }

    market_caps = {}
    try:
        response = requests.get(url, params=params)
        data = response.json()
        for coin in data:
            symbol = coin['symbol'].upper()
            cap = coin['market_cap']
            if cap and cap >= min_market_cap_usd:
                market_caps[symbol] = cap
    except Exception as e:
        print(f"❌ Failed to fetch market caps: {e}")
    return market_caps