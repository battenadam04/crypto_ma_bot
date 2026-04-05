
import ccxt
import config
import os
from config import KUCOIN_API_KEY, KUCOIN_SECRET_KEY, KUCOIN_PASSPHRASE, TRADING_SIGNALS_ONLY
import time
from datetime import datetime, timezone

from utils.coinGeckoData import fetch_market_caps
from utils.telegramUtils import send_telegram
from utils.utils import calculate_trade_levels, get_decimal_places, get_filled_price, log_event, safe_place_tp_sl


max_wait_seconds = 300
poll_interval = 1
MAX_TP_SL_RETRIES = 10

# Normalize so Render/dashboard env vars like "PHEMEX" or "phemex " still match.
EXCHANGE_RAW = os.getenv("EXCHANGE", "phemex") or "phemex"
EXCHANGE_NAME = EXCHANGE_RAW.strip().lower()

def init_exchange():
    if EXCHANGE_NAME == "phemex":
        exchange = ccxt.phemex({
            'apiKey': os.getenv("PHEMEX_API_KEY", ""),
            'secret': os.getenv("PHEMEX_SECRET", ""),
            'enableRateLimit': True,
            'options': {
                'defaultType': 'swap',
            },
        })
        if os.getenv("PHEMEX_SANDBOX", "false").lower() == "true":
            exchange.set_sandbox_mode(True)
            log_event("PHEMEX_SANDBOX=true: using Phemex testnet API.")

    elif EXCHANGE_NAME == "kucoin":
        exchange = ccxt.kucoin({
            'apiKey': os.getenv("KUCOIN_API_KEY"),
            'secret': os.getenv("KUCOIN_SECRET_KEY"),
            'password': os.getenv("KUCOIN_PASSPHRASE"),
            'enableRateLimit': True
        })
    
    elif EXCHANGE_NAME == "kucoin_futures":
        exchange = ccxt.kucoinfutures({
            'apiKey': os.getenv("KUCOIN_API_KEY"),
            'secret': os.getenv("KUCOIN_SECRET_KEY"),
            'password': os.getenv("KUCOIN_PASSPHRASE"),
            'enableRateLimit': True
        })
    
    elif EXCHANGE_NAME == "binance_margin":
        exchange = ccxt.binance({
            'apiKey': os.getenv("BINANCE_API_KEY"),
            'secret': os.getenv("BINANCE_SECRET_KEY"),
            'enableRateLimit': True,
            'options': {
                'defaultType': 'margin'  # very important for margin trading
            }
        })
        # Sandbox: use Binance Spot Test Network. Must be set before load_markets().
        # Note: Binance Spot Test Network does not support /sapi (margin) endpoints;
        # margin-specific calls may fail; use for connectivity and spot order flow testing only.
        if os.getenv("BINANCE_SANDBOX", "false").lower() == "true":
            exchange.set_sandbox_mode(True)
            log_event("BINANCE_SANDBOX=true: using Binance testnet (testnet.binance.vision). Margin APIs may not work on spot testnet.")
    
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


from config import MAX_OPEN_TRADES as MAX_OPEN_ORDERS, MAX_LOSSES_PER_SYMBOL, ENTRY_BUFFER_PCT

loss_tracker = {}


def can_place_order(symbol):
    try:
        exchange = get_exchange()
        positions = exchange.fetch_positions()

        open_positions = [
            p for p in positions if float(p['contracts']) > 0
        ]

        for p in open_positions:
            if p['symbol'] == symbol:
                return False, f"{symbol} already in open position."

        if len(open_positions) >= MAX_OPEN_ORDERS:

            return False, f"Max open positions reached ({MAX_OPEN_ORDERS})."

        if loss_tracker.get(symbol, 0) >= MAX_LOSSES_PER_SYMBOL:
            return False, f"{symbol} hit max loss cap: {loss_tracker[symbol]}"


        return True, "Can place order."

    except Exception as e:
        return False, f"Error checking position: {e}"



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





def _emergency_close_position(exchange, symbol, side, amount):
    """Force-close a position via market order when TP/SL placement fails."""
    close_side = 'sell' if side == 'buy' else 'buy'
    try:
        close_order = exchange.create_market_order(
            symbol=symbol,
            side=close_side,
            amount=amount,
            params={'reduceOnly': True}
        )
        send_telegram(
            f"🚨 EMERGENCY CLOSE: {symbol}\n"
            f"TP/SL placement failed after {MAX_TP_SL_RETRIES} retries.\n"
            f"Position force-closed to protect capital.\n"
            f"Order ID: {close_order.get('id', 'N/A')}"
        )
        log_event(f"🚨 Emergency close for {symbol}: {close_order}")
        return close_order
    except Exception as e:
        send_telegram(
            f"🚨🚨 CRITICAL: Failed to emergency close {symbol}!\n"
            f"Error: {e}\n"
            f"MANUAL INTERVENTION REQUIRED!"
        )
        log_event(f"🚨🚨 CRITICAL: Failed to emergency close {symbol}: {e}")
        return None


def place_entry_order_with_fallback(exchange, symbol, side, amount, entry_price, leverage):
    lev = int(leverage)
    lev_s = str(lev)

    if getattr(exchange, "id", None) == "phemex":
        try:
            exchange.set_margin_mode("isolated", symbol, {"leverage": lev_s})
            return exchange.create_limit_order(symbol, side, amount, entry_price, params={})
        except Exception as e:
            if "margin" in str(e).lower() or "leverage" in str(e).lower():
                print("⚠️ Phemex isolated margin/leverage failed. Retrying cross...")
                try:
                    exchange.set_margin_mode("cross", symbol, {"leverage": lev_s})
                    return exchange.create_limit_order(symbol, side, amount, entry_price, params={})
                except Exception as retry_error:
                    print(f"❌ Phemex cross margin retry failed: {retry_error}")
                    return None
            print(f"❌ Phemex entry order failed: {e}")
            return None

    try:
        exchange.set_margin_mode('isolated', symbol)
        # First attempt with 'isolated'
        return exchange.create_limit_order(
                symbol=symbol,
                side=side,
                amount=amount,
                price=entry_price,
                params={
                    'leverage': lev,
                }
            )
    except Exception as e:
        if 'margin mode' in str(e).lower():
            print("⚠️ Isolated margin failed. Retrying with 'cross' margin mode...")
            try:
                # Retry with 'cross'
                exchange.set_margin_mode('cross', symbol)
                return exchange.create_limit_order(
                    symbol=symbol,
                    side=side,
                    amount=amount,
                    price=entry_price,
                    params={
                        'leverage': lev,
                    }
                )
            except Exception as retry_error:
                print(f"❌ Retry with cross margin also failed: {retry_error}")
                return None
        else:
            print(f"❌ Failed placing order: {e}")
            return None

def place_futures_order(exchange, df, symbol, side, capital, leverage=10, strategy_type="range"):
    try:

        if not config.TRADING_ENABLED:
         return {"status": "skipped", "reason": "Trading disabled"}
    
        exchange.load_markets()
        market = exchange.market(symbol)

        # Precision
        amount_precision = get_decimal_places(market['precision']['amount'])
        price_precision = min(max(get_decimal_places(market['precision']['price']), 6), 12)

        # Minimums
        min_price = market.get('limits', {}).get('price', {}).get('min', 0)
        min_amount = market.get('limits', {}).get('amount', {}).get('min', 0)

        # Get current price
        ticker = exchange.fetch_ticker(symbol)
        price = ticker['last']

        if price is None or price <= 0:
            return {'status': 'error', 'message': f"Invalid ticker data for {symbol}: {ticker}"}

        # Signals-only: never touch balance, sizing, or orders — only market + last price for indicative TP/SL.
        if TRADING_SIGNALS_ONLY:
            log_event(f"📣 Signals-only: {symbol} — indicative levels (no orders, no balance check).")
            levels = calculate_trade_levels(price, side, df, len(df) - 1, strategy_type)
            tp_price = round(levels['take_profit'], price_precision)
            sl_price = round(levels['stop_loss'], price_precision)
            return {
                'status': 'success',
                'filled_entry': price,
                'tp_order': tp_price,
                'sl_order': sl_price,
            }

        contract_value = float(market.get('contractSize') or 1.0)

        balance = exchange.fetch_balance()
        usdt_balance = balance['free'].get('USDT', 0)

        if usdt_balance == 0:
            msg = "No available USDT balance for futures trading."
            print(f"❌ {msg}")
            return {"status": "error", "message": msg, "filled_entry": None, "tp_order": None, "sl_order": None}

        # Use only a portion of balance (configurable)
        capital_pct = getattr(config, 'TRADE_CAPITAL_PCT', 0.25)
        capital_to_use = usdt_balance * capital_pct

        # Apply leverage to get max notional
        notional = capital_to_use * leverage

        # Calculate raw amount of contracts
        raw_amount = notional / (price * contract_value)
        amount = round(raw_amount, amount_precision)

        print(f"✅ Capital to use: {capital_to_use:.2f} USDT | Leverage: x{leverage}")
        print(f"• Price: {price} | Notional: {notional:.2f} | Amount: {amount}")

        # Skip if amount is below minimum
        if amount < min_amount:
            return {'status': 'error', 'message': f"Amount {amount} is below min allowed: {min_amount}"}

        raw_entry_price = price * (1 + ENTRY_BUFFER_PCT / 100) if side == 'buy' else price * (1 - ENTRY_BUFFER_PCT / 100)

        if raw_entry_price <= min_price:
            return {'status': 'error', 'message': f"Raw entry price {raw_entry_price} is below min allowed: {min_price}"}

        entry_price = round(raw_entry_price, price_precision)

        if entry_price <= 0:
            return {'status': 'error', 'message': f"Final entry price is invalid: {entry_price}"}

        # ✅ Place entry + TP/SL (live path only; signals-only returns earlier)
        entry_order = place_entry_order_with_fallback(exchange, symbol, side, amount, entry_price, leverage)

        if not entry_order or not isinstance(entry_order, dict) or 'id' not in entry_order:
            return {'status': 'error', 'message': f"Entry order failed: {entry_order}"}

        # 🕒 Poll for order fill
        filled_price = None

        for _ in range(max_wait_seconds):
            try:
                order_id = entry_order['id']
                order_status = exchange.fetch_order(order_id, symbol)
                status = order_status.get('status')
                filled = float(order_status.get('filled', 0))
                amount = float(order_status.get('amount', 1))

                if status == 'closed' or (status == 'open' and filled >= amount):
                    filled_price_fetched = get_filled_price(order_status)
                    filled_price = filled_price_fetched
                    print(f"✅ Entry order {order_id} filled with filled price:{filled_price}")
                    break
                else:
                    log_event(f"⏳ Waiting for order {order_id} to fill, current status: {status}")
            except Exception as e:
                print(f"❌ Error fetching order status: {e}")
            time.sleep(poll_interval)
        else:
            return {'status': 'error', 'message': 'Entry order not filled in time'}

        # 🔒 Place TP and SL with retry (capped to protect capital)
        for attempt in range(1, MAX_TP_SL_RETRIES + 1):
            levels = calculate_trade_levels(filled_price, side, df, len(df)-1, strategy_type)
            tp_price = round(levels['take_profit'], price_precision)
            sl_price = round(levels['stop_loss'], price_precision)

            validated = safe_place_tp_sl(
                tp_price,
                sl_price,
                entry_price=filled_price,
                direction=side,
                symbol=symbol
            )

            if validated and validated.get('valid'):
                tp_sl_result = place_tp_sl_orders(exchange, symbol, side, amount, validated['take_profit'], validated['stop_loss'], filled_price)

                if tp_sl_result['status'] in ['tp_filled', 'sl_filled', 'success']:
                    print(f"✅ TP and SL successfully placed on attempt {attempt}.")
                    return {
                        'status': 'success',
                        'filled_entry': filled_price,
                        'tp_order': tp_sl_result['tp_order'],
                        'sl_order': tp_sl_result['sl_order']
                    }

            print(f"🔁 TP/SL attempt {attempt}/{MAX_TP_SL_RETRIES} failed, retrying in 2s...")
            time.sleep(2)

        log_event(f"🚨 TP/SL failed after {MAX_TP_SL_RETRIES} attempts for {symbol}. Force-closing position.")
        _emergency_close_position(exchange, symbol, side, amount)
        return {'status': 'error', 'message': f"TP/SL failed after {MAX_TP_SL_RETRIES} attempts. Position force-closed."}

    except Exception as e:
        return {'status': 'error', 'message': f"Unexpected error: {str(e)}"}


def is_order_valid(order):
    valid_statuses = ['open', 'triggered', 'active', 'new', 'live']

    if not order:
        return False

    # If order is just a status string (e.g. 'open'), treat it directly
    if isinstance(order, str):
        return order in valid_statuses

    # If order is a dict, check the 'status' key safely
    if isinstance(order, dict):
        return order.get('status') in valid_statuses

    # If order is some other unexpected type
    return False


def place_tp_sl_orders(exchange, symbol, side, amount, tp_price, sl_price, filled_price, max_retries=3, delay=1, poll_interval=2, max_poll_time=60):
    close_side = 'sell' if side == 'buy' else 'buy'
    # Phemex conditional market orders: triggerDirection + stopPrice (ccxt unified)
    if side == 'buy':
        tp_trigger_dir, sl_trigger_dir = 'up', 'down'
    else:
        tp_trigger_dir, sl_trigger_dir = 'down', 'up'

    for attempt in range(1, max_retries + 1):
        print(f"🔁 Order attempt {attempt}: Creating TP/SL orders...")

        try:
            # Get current market price to validate SL placement
            ticker = exchange.fetch_ticker(symbol)
            last_price = ticker.get('last')
            if last_price is None:
                raise Exception("Couldn't fetch current market price.")

            if getattr(exchange, 'id', None) == 'phemex':
                phemex_cond = {
                    'reduceOnly': True,
                    'triggerType': 'ByMarkPrice',
                }
                tp_order = exchange.create_order(
                    symbol=symbol,
                    type='market',
                    side=close_side,
                    amount=amount,
                    params={
                        **phemex_cond,
                        'stopPrice': tp_price,
                        'triggerDirection': tp_trigger_dir,
                    },
                )
                sl_order = exchange.create_order(
                    symbol=symbol,
                    type='market',
                    side=close_side,
                    amount=amount,
                    params={
                        **phemex_cond,
                        'stopPrice': sl_price,
                        'triggerDirection': sl_trigger_dir,
                    },
                )
            else:
                # ✅ KuCoin-style params (and similar)
                tp_order = exchange.create_order(
                    symbol=symbol,
                    type='market',
                    side=close_side,
                    amount=amount,
                    params={
                        'stop': 'up',
                        'reduceOnly': True,
                        'stopPrice': tp_price,
                        'stopPriceType': 'TP'
                    }
                )

                sl_order = exchange.create_order(
                    symbol=symbol,
                    type='market',
                    side=close_side,
                    amount=amount,
                    params={
                        'stop': 'down',
                        'stopPrice': sl_price,
                        'reduceOnly': True,
                        'stopType': 'loss',
                        'stopPriceType': 'TP'
                    }
                )

            tp_id = tp_order['id']
            sl_id = sl_order['id']
            print(f"✅ TP/SL orders successfully placed.")

            # 🔄 Step 2: Poll for one of the orders to fill
            start_time = time.time()
            tp_check, sl_check = None, None

            while time.time() - start_time < max_poll_time:
                try:
                    tp_check = exchange.fetch_order(tp_id, symbol)
                except Exception as e:
                    if 'orderNotExist' in str(e):
                        print(f"⏳ TP order not filled yet, retrying...")
                        time.sleep(0.5)
                        continue
                    else:
                        raise

                try:
                    sl_check = exchange.fetch_order(sl_id, symbol)
                except Exception as e:
                    if 'orderNotExist' in str(e):
                        print(f"⏳ SL order not found yet, retrying...")
                        time.sleep(0.5)
                        continue
                    else:
                        raise

                print(f"🔍 TP Status: {tp_check.get('status')}, SL Status: {sl_check.get('status')}")

                if is_order_valid(tp_check):
                    filled_tp_price = tp_check.get('average') or tp_check.get('price')
                    print(f"🎯 TP filled at {filled_tp_price}")
                    return {
                        'tp_order': tp_check,
                        'sl_order': sl_check,
                        'status': 'tp_filled',
                        'filled_price': filled_tp_price
                    }

                if is_order_valid(sl_check):
                    filled_sl_price = sl_check.get('average') or sl_check.get('price')
                    print(f"🛑 SL filled at {filled_sl_price}")
                    return {
                        'tp_order': tp_check,
                        'sl_order': sl_check,
                        'status': 'sl_filled',
                        'filled_price': filled_sl_price
                    }

                # ✅ NEW: Exit early if both orders are no longer valid (canceled or done with no fill)
                if not is_order_valid(tp_check) and not is_order_valid(sl_check):
                    print("❌ TP and SL both canceled or inactive. Exiting polling loop.")
                    return {
                        'tp_order': tp_check,
                        'sl_order': sl_check,
                        'status': 'canceled_or_invalid',
                        'filled_price': None
                    }
                print(f"⏳ Polling... waiting for TP or SL to fill (every {poll_interval}s)")
                time.sleep(poll_interval)

            # Timeout fallback
            print("⚠️ TP/SL orders not filled within polling window.")
            return {
                'tp_order': tp_check,
                'sl_order': sl_check,
                'status': 'timeout',
                'filled_price': None
            }


        except Exception as e:
            print(f"❌ Error placing TP/SL: {e}")
            time.sleep(delay)

    # All retries failed
    print("❌ Max retries reached. TP/SL placement failed.")
    return {
        'tp_order': None,
        'sl_order': None,
        'status': 'error',
        'filled_price': None
    }

def fetch_balance_and_notify():
    try:
        ex = get_exchange()
        is_binance_margin = (EXCHANGE_NAME == "binance_margin")

        if is_binance_margin:
            spot_bal = ex.fetch_balance({'type': 'spot'})
            margin_bal = ex.fetch_balance({'type': 'margin'})
            spot_total = spot_bal['total'].get('USDT', 0)
            spot_free = spot_bal['free'].get('USDT', 0)
            margin_total = margin_bal['total'].get('USDT', 0)
            margin_free = margin_bal['free'].get('USDT', 0)
            combined = spot_total + margin_total
            timestamp = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')
            message = (
                f"📊 Balance at {timestamp}:\n"
                f"Spot:   {spot_total:.2f} USDT (avail: {spot_free:.2f})\n"
                f"Margin: {margin_total:.2f} USDT (avail: {margin_free:.2f})\n"
                f"Combined: {combined:.2f} USDT"
            )
            send_telegram(message)
            print("✅ Balance sent to Telegram.")
            return combined
        else:
            balance = ex.fetch_balance()
            usdt = balance['total'].get('USDT', 0)
            available = balance['free'].get('USDT', 0)
            timestamp = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')
            message = (
                f"📊 Balance at {timestamp}:\n"
                f"Total USDT: {usdt:.2f}\n"
                f"Available USDT: {available:.2f}"
            )
            send_telegram(message)
            print("✅ Balance sent to Telegram.")
            return usdt
    except Exception as e:
        print("❌ Error fetching balance or sending message:", e)
        return None