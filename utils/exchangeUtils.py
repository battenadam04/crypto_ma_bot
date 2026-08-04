import ccxt
import os

from utils.coinGeckoData import fetch_market_caps
from utils.utils import calculate_trade_levels, get_decimal_places, log_event


# Normalize so Render/dashboard env vars like "PHEMEX" or "phemex " still match.
EXCHANGE_RAW = os.getenv("EXCHANGE", "phemex") or "phemex"
EXCHANGE_NAME = EXCHANGE_RAW.strip().lower()


def init_exchange():
    """Public/read-only market-data client. API keys are optional (not used for orders)."""
    if EXCHANGE_NAME == "phemex":
        exchange = ccxt.phemex({
            'enableRateLimit': True,
            'options': {'defaultType': 'swap'},
        })
        if os.getenv("PHEMEX_SANDBOX", "false").lower() == "true":
            exchange.set_sandbox_mode(True)
            log_event("PHEMEX_SANDBOX=true: using Phemex testnet API.")

    elif EXCHANGE_NAME == "kucoin":
        exchange = ccxt.kucoin({'enableRateLimit': True})

    elif EXCHANGE_NAME == "kucoin_futures":
        exchange = ccxt.kucoinfutures({'enableRateLimit': True})

    elif EXCHANGE_NAME == "binance_margin":
        exchange = ccxt.binance({
            'enableRateLimit': True,
            'options': {'defaultType': 'margin'},
        })
        if os.getenv("BINANCE_SANDBOX", "false").lower() == "true":
            exchange.set_sandbox_mode(True)
            log_event("BINANCE_SANDBOX=true: using Binance testnet (testnet.binance.vision).")

    else:
        raise ValueError(f"Unsupported exchange: {EXCHANGE_NAME}")

    exchange.load_markets()
    return exchange


_cached_exchange = None


def get_exchange():
    """Return a cached exchange instance (created once, reused everywhere)."""
    global _cached_exchange
    if _cached_exchange is None:
        _cached_exchange = init_exchange()
    return _cached_exchange


def get_top_volume_pairs(exchange, quote='USDT', top_n=5):
    print("⏳ Fetching tickers...")
    try:
        tickers = exchange.fetch_tickers()
        print(f"✅ Fetched {len(tickers)} tickers.")
    except Exception as e:
        print("❌ Error fetching tickers:", e)
        return []

    volume_data = []

    # List of stablecoins to filter out
    stablecoins = {'USDT', 'USDC', 'BUSD', 'TUSD', 'DAI', 'FDUSD', 'UST'}

    for symbol, ticker in tickers.items():
            if not symbol.endswith(f"/{quote}"):
                continue

            base = symbol.split('/')[0]

            if base in stablecoins:
                continue  # skip stablecoin-to-stablecoin pairs

            volume = ticker.get('quoteVolume')
            if volume:
                try:
                    volume = float(volume)
                    volume_data.append((symbol, volume))
                except ValueError:
                    continue

    top_pairs = sorted(volume_data, key=lambda x: x[1], reverse=True)[:top_n]
    print("🔥 Top pairs:", top_pairs)
    return [pair[0] for pair in top_pairs]


def _binance_quote_volumes(exchange):
    """
    Build {symbol: quote_volume_float} using Binance public 24h ticker.
    No reliance on markets_by_id; we map ids -> unified symbols via safe_symbol().
    """
    if exchange is None:
        return {}

    volumes = {}
    try:
        raw = exchange.publicGetTicker24hr()  # public spot endpoint (works for margin routing too)
    except Exception:
        raw = []

    markets = getattr(exchange, "markets", {}) or {}

    for item in raw or []:
        market_id = item.get("symbol")  # e.g., 'BTCUSDT'
        if not market_id:
            continue

        # Get a unified symbol like 'BTC/USDT'
        try:
            sym = exchange.safe_symbol(market_id)
        except Exception:
            sym = None
        if not sym or sym not in markets:
            continue  # skip symbols not in the loaded markets

        qv = item.get("quoteVolume") or item.get("quoteAssetVolume") or item.get("volume")
        try:
            volumes[sym] = float(qv) if qv is not None else 0.0
        except Exception:
            volumes[sym] = 0.0

    return volumes


def _fetch_binance_margin_symbols(exchange_obj, quote='USDT'):
    """
    Fetch the actual margin-enabled symbols from Binance's margin API.
    Uses isolated + cross margin endpoints; isMarginTradingAllowed in exchange
    info can be inaccurate (e.g. TON/USDT has spot but NOT margin).
    """
    allowed = set()
    try:
        # Isolated margin pairs (GET /sapi/v1/margin/isolated/allPairs)
        isolated = exchange_obj.sapi_get_margin_isolated_allpairs()
        for p in isolated or []:
            if p.get('quote') == quote and p.get('isMarginTrade', False):
                allowed.add(str(p.get('symbol', '')).replace('/', ''))
        # Cross margin pairs (GET /sapi/v1/margin/allPairs)
        cross = exchange_obj.sapi_get_margin_allpairs()
        for p in cross or []:
            sym = str(p.get('symbol', '')).replace('/', '')
            if p.get('quote') == quote or (sym and sym.endswith(quote)):
                allowed.add(sym)
    except Exception as e:
        log_event(f"⚠️ Could not fetch Binance margin pairs: {e}. Falling back to isMarginTradingAllowed.")
        return None  # caller will fall back to exchange info
    return allowed


def get_top_phemex_usdt_swaps(
    exchange,
    top_n=20,
    min_quote_volume=1_000_000,
    min_market_cap_usd=0,
):
    """
    Rank active USDT-settled perpetuals on Phemex by 24h quote volume.

    If min_market_cap_usd > 0, CoinGecko is used to keep only bases whose market cap
    meets that USD threshold (same idea as Binance path). Sort: (cap, volume) desc;
    if cap filter off, sort by volume only.
    """
    stablecoins = {
        'USDT', 'USDC', 'BUSD', 'TUSD', 'DAI',
        'FDUSD', 'UST', 'USDE', 'USD1',
    }
    use_cap = min_market_cap_usd is not None and float(min_market_cap_usd) > 0
    caps = fetch_market_caps(float(min_market_cap_usd)) if use_cap else {}
    if use_cap and not caps:
        log_event(
            "get_top_phemex_usdt_swaps: CoinGecko returned no caps (rate limit/error). "
            "Using volume-only ranking; set BACKTEST_COINGECKO_MIN_CAP=0 to skip CoinGecko intentionally."
        )
        use_cap = False
    exchange.load_markets()
    try:
        tickers = exchange.fetch_tickers()
    except Exception as e:
        log_event(f"get_top_phemex_usdt_swaps: fetch_tickers failed: {e}")
        return []

    rows = []
    for symbol, m in (exchange.markets or {}).items():
        if not m.get('swap') or m.get('settle') != 'USDT':
            continue
        if not m.get('active', True):
            continue
        base = m.get('base')
        if not base or base in stablecoins:
            continue
        if use_cap and base not in caps:
            continue
        t = tickers.get(symbol) or {}
        qv = t.get('quoteVolume')
        if qv is None:
            continue
        try:
            vol = float(qv)
        except (TypeError, ValueError):
            continue
        if vol < float(min_quote_volume):
            continue
        cap_val = caps.get(base, 0.0) if use_cap else 0.0
        rows.append((symbol, cap_val, vol))

    if use_cap:
        rows.sort(key=lambda x: (x[1], x[2]), reverse=True)
    else:
        rows.sort(key=lambda x: x[2], reverse=True)
    return rows[: int(top_n)]


def get_auto_backtest_pairs(exchange):
    """
    Optional universe for backtests when BACKTEST_AUTO_TOP_PAIRS=true.
    Respects BACKTEST_TOP_N, BACKTEST_MIN_QUOTE_VOLUME, BACKTEST_COINGECKO_MIN_CAP (0 = skip CoinGecko, volume only).
    """
    eid = getattr(exchange, "id", None)
    if eid not in ("binance", "phemex", "kucoinfutures"):
        log_event(
            "BACKTEST_AUTO_TOP_PAIRS: built-in discovery needs EXCHANGE=binance_margin, phemex, or "
            f"kucoin_futures (ccxt id was {eid!r}). Set BACKTEST_PAIRS or CRYPTO_PAIRS instead."
        )
        return []
    top_n = int(os.getenv("BACKTEST_TOP_N", "20"))
    min_vol = float(os.getenv("BACKTEST_MIN_QUOTE_VOLUME", "1000000"))
    cap_raw = os.getenv("BACKTEST_COINGECKO_MIN_CAP", "1000000000").strip()
    try:
        min_cap = float(cap_raw) if cap_raw else 0.0
    except ValueError:
        min_cap = 1_000_000_000.0
    return get_top_tradable_pairs(
        exchange,
        top_n=top_n,
        min_volume=min_vol,
        min_market_cap_usd=min_cap,
    )


def get_top_tradable_pairs(
    exchange_or_markets,
    quote='USDT',
    top_n=15,
    min_volume=1_000_000,
    min_market_cap_usd=1_000_000_000,
):
    """
    Discover liquid symbols on the connected exchange (for backtests / screening).

    CoinGecko: when min_market_cap_usd > 0, only bases present in CoinGecko's top listings
    with market cap >= that USD value are kept. That is a *large-cap* filter, not "top volume
    from CoinGecko" — volume still comes from the exchange (24h quote volume).

    Ranking: (market_cap, 24h_quote_volume) descending when the cap filter is on; otherwise
    by 24h quote volume only.

    - Binance (margin): margin-enabled USDT spot pairs.
    - Phemex: USDT-settled perpetual swaps.
    - KuCoin futures: linear USDT contracts (ccxt id kucoinfutures), or a legacy markets dict.
    """

    stablecoins = {
        'USDT', 'USDC', 'BUSD', 'TUSD', 'DAI',
        'FDUSD', 'UST', 'USDE', 'USD1'
    }

    use_cap_filter = min_market_cap_usd is not None and float(min_market_cap_usd) > 0
    market_caps = fetch_market_caps(float(min_market_cap_usd)) if use_cap_filter else {}
    if use_cap_filter and not market_caps:
        log_event(
            "get_top_tradable_pairs: CoinGecko returned no caps (rate limit/error). "
            "Using volume-only ranking for this run."
        )
        use_cap_filter = False
    filtered_pairs = []

    # Allow passing exchange OR markets dict
    if isinstance(exchange_or_markets, dict):
        markets = exchange_or_markets
        exchange_obj = None
    else:
        exchange_obj = exchange_or_markets
        markets = exchange_obj.markets or {}

    is_binance = exchange_obj and exchange_obj.id == "binance"
    is_phemex = exchange_obj and exchange_obj.id == "phemex"
    use_kucoin_futures_markets = isinstance(exchange_or_markets, dict) or (
        exchange_obj and exchange_obj.id == "kucoinfutures"
    )

    if is_phemex and exchange_obj is not None:
        return get_top_phemex_usdt_swaps(
            exchange_obj,
            top_n=top_n,
            min_quote_volume=float(min_volume),
            min_market_cap_usd=float(min_market_cap_usd) if use_cap_filter else 0.0,
        )

    # =========================
    # BINANCE — MARGIN
    # =========================
    if is_binance:
        # Fetch actual margin-enabled symbols from Binance API
        margin_symbols = _fetch_binance_margin_symbols(exchange_obj, quote)

        # Binance public 24h ticker → LIST
        tickers_24h = exchange_obj.publicGetTicker24hr()

        # 🔑 Convert LIST → DICT for O(1) lookup
        volume_by_symbol = {}
        for t in tickers_24h:
            symbol = t.get('symbol')
            if symbol:
                volume_by_symbol[symbol] = float(
                    t.get('quoteVolume', 0) or 0
                )

        for symbol, market in markets.items():
            if market.get('quote') != quote:
                continue
            if not market.get('spot', False):
                continue
            if not market.get('active', True):
                continue

            binance_symbol = symbol.replace("/", "")
            if margin_symbols is not None:
                if binance_symbol not in margin_symbols:
                    continue
            else:
                info = market.get('info', {})
                if not info.get('isMarginTradingAllowed', False):
                    continue

            base = market.get('base')
            if not base or base in stablecoins:
                continue
            if use_cap_filter and base not in market_caps:
                continue

            volume = volume_by_symbol.get(binance_symbol, 0.0)
            if volume < float(min_volume):
                continue

            cap_val = market_caps[base] if use_cap_filter else 0.0
            filtered_pairs.append((symbol, cap_val, volume))

    # =========================
    # KUCOIN — FUTURES (or legacy markets dict)
    # =========================
    elif use_kucoin_futures_markets:
        for symbol, market in markets.items():
            if not market.get('future', False):
                continue
            if not market.get('linear', False):
                continue
            if market.get('quote') != quote:
                continue
            if not market.get('active', False):
                continue

            base = market.get('base')
            if not base or base in stablecoins:
                continue
            if use_cap_filter and base not in market_caps:
                continue

            vol = market.get('info', {}).get('volumeOf24h')
            if vol is None:
                continue

            try:
                volume = float(vol)
            except Exception:
                continue

            if volume < float(min_volume):
                continue

            cap_val = market_caps[base] if use_cap_filter else 0.0
            filtered_pairs.append((symbol, cap_val, volume))

    else:
        return []

    if use_cap_filter:
        filtered_pairs.sort(key=lambda x: (x[1], x[2]), reverse=True)
    else:
        filtered_pairs.sort(key=lambda x: x[2], reverse=True)

    return filtered_pairs[:top_n]


def build_indicative_levels(exchange, df, symbol, side, strategy_type="trend"):
    """
    Read-only: last price + ATR-based indicative TP/SL for a signal message.
    Never places orders or reads account balances.
    """
    try:
        exchange.load_markets()
        market = exchange.market(symbol)
        price_precision = min(max(get_decimal_places(market['precision']['price']), 6), 12)

        ticker = exchange.fetch_ticker(symbol)
        price = ticker.get('last')
        if price is None or price <= 0:
            return {'status': 'error', 'message': f"Invalid ticker data for {symbol}: {ticker}"}

        levels = calculate_trade_levels(price, side, df, len(df) - 1, strategy_type)
        tp_price = round(levels['take_profit'], price_precision)
        sl_price = round(levels['stop_loss'], price_precision)
        return {
            'status': 'success',
            'filled_entry': price,
            'tp_order': tp_price,
            'sl_order': sl_price,
            'tp_price': tp_price,
            'sl_price': sl_price,
        }
    except Exception as e:
        return {'status': 'error', 'message': f"Unexpected error: {str(e)}"}
