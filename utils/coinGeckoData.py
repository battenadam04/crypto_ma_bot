import requests

def fetch_market_caps(min_market_cap_usd=1_000_000_000):
    """Fetch market caps from CoinGecko and return a dict of {symbol: market_cap}"""
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