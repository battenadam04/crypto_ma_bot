
import ccxt
from config import KUCOIN_API_KEY, KUCOIN_SECRET_KEY, KUCOIN_PASSPHRASE, TRADING_SIGNALS_ONLY
import time

from utils.coinGeckoData import fetch_market_caps
from utils.utils import calculate_trade_levels, get_decimal_places, log_event


max_wait_seconds = 300
poll_interval = 1

EXCHANGE = ccxt.kucoin({
        'apiKey': KUCOIN_API_KEY,
        'secret': KUCOIN_SECRET_KEY,
        'password': KUCOIN_PASSPHRASE,
        'enableRateLimit': True
})

def init_kucoin_futures():
    futures = ccxt.kucoinfutures({
        'apiKey': KUCOIN_API_KEY,
        'secret': KUCOIN_SECRET_KEY,
        'password': KUCOIN_PASSPHRASE,
        'enableRateLimit': True
    })
    futures.load_markets()
    return futures

loss_tracker = {}
MAX_LOSSES = 3
MAX_OPEN_ORDERS = 3


def can_place_order(symbol, can_trade_event):

    try:
        kucoin_futures = init_kucoin_futures()
        positions = kucoin_futures.fetch_positions()

        open_positions = [
            p for p in positions if float(p['contracts']) > 0
        ]

        for p in open_positions:
            print(f"📈 Open Position: {p['symbol']}, Size: {p['contracts']}, Side: {p['side']}")

        # Block if too many open positions
        if len(open_positions) == MAX_OPEN_ORDERS:
            print(f"⛔ Max open positions reached ({MAX_OPEN_ORDERS}). Skipping {symbol}.")
            can_trade_event.clear()  # Pause all threads
            return False

        can_trade_event.set() # Resume if conditions are OK
        # Block if this symbol hit its loss cap
        if loss_tracker.get(symbol, 0) == MAX_LOSSES:
            print(f"⛔ {symbol} skipped due to {loss_tracker[symbol]} recent losses.")
            return False

        return True

    except Exception as e:
        print(f"❌ Error in can_place_order: {e}")
        return False


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


def get_top_futures_tradable_pairs(exchange, quote='USDT', top_n=15, min_volume=1_000_000, min_market_cap_usd=1_000_000_000):
    print("⏳ Loading KuCoin Futures markets...")
    try:
        markets = exchange.load_markets()
    except Exception as e:
        print("❌ Error loading markets:", e)
        return []
    market_caps = fetch_market_caps(min_market_cap_usd)
    stablecoins = {'USDT', 'USDC', 'BUSD', 'TUSD', 'DAI', 'FDUSD', 'UST'}
    filtered_pairs = []

    for symbol, market in markets.items():
        # Filter for futures markets with the specified quote currency
        if market.get('future', False):
            continue
        if market.get('quote') != quote:
            continue
        if not market.get('linear', False):
            continue
        if not market.get('active', False):
            continue

        base = market.get('base')
        if base in stablecoins:
            continue  # Skip stablecoin-to-stablecoin pairs

        if base not in market_caps:
            # Skip pairs whose base coin market cap is below threshold
            continue

               # Check 24h volume
        vol_value = market.get('info', {}).get('volumeOf24h')
        if vol_value is None:
            continue
        try:
            volume = float(vol_value)
        except Exception:
            continue

        if volume < min_volume:
            continue

        filtered_pairs.append((symbol, market_caps[base], volume))

    # Sort by market cap descending, then volume descending
    sorted_pairs = sorted(filtered_pairs, key=lambda x: (x[1], x[2]), reverse=True)[:top_n]
    print(f"{sorted_pairs}")

    #print(f"🔥 Top {top_n} pairs filtered by market cap > {min_market_cap_usd} USD and volume > {min_volume} USD:")

    return sorted_pairs


def place_entry_order_with_fallback(exchange, symbol, side, amount, entry_price, leverage):
    try:
        exchange.set_margin_mode('isolated', symbol)
        # First attempt with 'isolated'
        return exchange.create_limit_order(
                symbol=symbol,
                side=side,
                amount=amount,
                price=entry_price,
                params={
                    'leverage': int(leverage),
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
                        'leverage': int(leverage),
                    }
                )
            except Exception as retry_error:
                print(f"❌ Retry with cross margin also failed: {retry_error}")
                return None
        else:
            print(f"❌ Failed placing order: {e}")
            return None

def place_futures_order(exchange, df, symbol, side, usdt_amount, leverage=10, strategy_type="range"):
    try:
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

        contract_value = float(market.get('contractSize', 1))

        # Notional & leverage
        max_notional = usdt_amount * leverage
        raw_amount = max_notional / (price * contract_value)
        amount = round(raw_amount, amount_precision)

        # Skip if amount is below minimum
        if amount < min_amount:
            return {'status': 'error', 'message': f"Amount {amount} is below min allowed: {min_amount}"}

        # Entry price (with buffer)
        buffer = 0.05
        raw_entry_price = price * (1 + buffer / 100) if side == 'buy' else price * (1 - buffer / 100)

        if raw_entry_price <= min_price:
            return {'status': 'error', 'message': f"Raw entry price {raw_entry_price} is below min allowed: {min_price}"}

        entry_price = round(raw_entry_price, price_precision)

        if entry_price <= 0:
            return {'status': 'error', 'message': f"Final entry price is invalid: {entry_price}"}
        

        # Fetch balance
        balance = exchange.fetch_balance({'type': 'contract'})
        available = balance['free'].get('USDT', 0)
        #print(f"💰 Available USDT Balance (Futures): {balance}")

        # if available < usdt_amount:
        #     return {'status': 'error', 'message': f"Insufficient balance. Required: {usdt_amount}, Available: {available}"}

        # ✅ Place Entry Order


        # only return data for trading signals for manual trading and ignore bot setting trades
        if not TRADING_SIGNALS_ONLY:
            entry_order = place_entry_order_with_fallback(exchange, symbol, side, amount, entry_price, leverage)

            if not entry_order or not isinstance(entry_order, dict) or 'id' not in entry_order:
                return {'status': 'error', 'message': f"Entry order failed: {entry_order}"}

            # 🕒 Poll for order fill
            filled_price = None

            for _ in range(max_wait_seconds):
                try:
                    order_id = entry_order['id']
                    order_status = exchange.fetch_order(order_id, symbol)
                    if order_status['status'] == 'closed':
                        price_value = order_status['price']
                        filled_price = price_value
                        print(f"✅ Entry order {order_id} filled with filled price:{price_value}")
                        break
                    else:
                        log_event(f"⏳ Waiting for order {order_id} to fill, current status: {order_status['status']}")
                except Exception as e:
                    print(f"❌ Error fetching order status: {e}")
                time.sleep(poll_interval)
            else:
                return {'status': 'error', 'message': 'Entry order not filled in time'}

            # 🔒 Step 3: Place TP and SL with retry
            attempt = 1
            start_time = time.time()
            while True:
                levels = calculate_trade_levels(filled_price, side, df, len(df)-1, strategy_type)
                tp_price = round(levels['take_profit'], price_precision)
                sl_price = round(levels['stop_loss'], price_precision)

                if tp_price < min_price or sl_price < min_price:
                    print(f"⚠️ TP/SL price too low (TP: {tp_price}, SL: {sl_price}). Retrying...")
                    time.sleep(2)
                    continue

                tp_sl_result = place_tp_sl_orders(exchange, symbol, side, amount, tp_price, sl_price, filled_price)

                if tp_sl_result['status'] in ['tp_filled', 'sl_filled', 'success']:
                    print(f"✅ TP and SL successfully placed on attempt {attempt}.")
                    return {
                        'status': 'success',
                        'filled_entry': filled_price,
                        'tp_order': tp_sl_result['tp_order'],
                        'sl_order': tp_sl_result['sl_order']
                    }

                # ⏳ Timeout after 90 seconds
                # if time.time() - start_time > 200:
                #     print(f"⚠️ TP/SL placement window exceeded. Placing SL only for safety.")
                #     try:
                #         close_side = 'sell' if side == 'buy' else 'buy'
                #         fallback_sl = exchange.create_order(
                #             symbol=symbol,
                #             type='market',
                #             side=close_side,
                #             amount=amount,
                #             params={
                #                 'stop': 'down' if close_side == 'sell' else 'up',
                #                 'stopPrice': sl_price,
                #                 'reduceOnly': True,
                #                 'stopType': 'loss',
                #             }
                #         )
                #         return {
                #             'status': 'partial',
                #             'filled_entry': filled_price,
                #             'tp_order': None,
                #             'sl_order': fallback_sl
                #         }
                #     except Exception as e:
                #         return {'status': 'error', 'message': f"SL fallback failed: {e}"}

                attempt += 1
                print(f"🔁 Retry #{attempt} in 2 seconds...")
                time.sleep(2)

            #return {'status': 'error', 'message': f"Failed to place TP/SL after {max_attempts} attempts."}
        else:
            print(f"🔁TRADING SIGNALS ONLY...")
            levels = calculate_trade_levels(price, side, df, len(df)-1, strategy_type)
            tp_price = round(levels['take_profit'], price_precision)
            sl_price = round(levels['stop_loss'], price_precision)
            return {
                'status': 'success',
                'filled_entry': price,
                'tp_order': tp_price,
                'sl_order': sl_price
            }

    except Exception as e:
        return {'status': 'error', 'message': f"Unexpected error: {str(e)}"}


def is_order_valid(order):
    if not order:
        return False
    return order['status'] in ['open', 'triggered', 'active', 'new', 'live']

def is_valid_tp_sl(tp, sl, filled, market, side):
    if side == 'buy':
        if tp <= filled or sl >= filled or sl >= market:
            return False
        else:  # sell
            if tp >= filled or sl <= filled or sl <= market:
                return False
    return True

def place_tp_sl_orders(exchange, symbol, side, amount, tp_price, sl_price, filled_price, max_retries=3, delay=1, poll_interval=2, max_poll_time=60):
    close_side = 'sell' if side == 'buy' else 'buy

    for attempt in range(1, max_retries + 1):
        print(f"🔁 Order attempt {attempt}: Creating TP/SL orders...")

        try:
            # Get current market price to validate SL placement
            ticker = exchange.fetch_ticker(symbol)
            last_price = ticker.get('last')
            if last_price is None:
                raise Exception("Couldn't fetch current market price.")

            # 🚨 Validate TP/SL logic before placing
            if not is_valid_tp_sl(tp_price, sl_price, filled_price, last_price, side):
                print(f"⚠️ Invalid TP/SL for current conditions. Adjusting...")

                # Apply minimal offset adjustment to make them valid
                adjust_pct = 0.002  # 0.2% nudge
                if side == 'buy':
                    tp_price = max(filled_price * (1 + adjust_pct), tp_price)
                    sl_price = min(filled_price * (1 - adjust_pct), sl_price)
                else:
                    tp_price = min(filled_price * (1 - adjust_pct), tp_price)
                    sl_price = max(filled_price * (1 + adjust_pct), sl_price)

                print(f"🛠️ Adjusted TP: {tp_price}, SL: {sl_price}")


            # ✅ Place TP (limit order)
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

            # ✅ Place SL (stop-market order)
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
                }
            )

            tp_id = tp_order['id']
            sl_id = sl_order['id']
            print(f"✅ TP/SL orders successfully placed.")
            print(f"• TP ID: {tp_id}, Price: {tp_price}")
            print(f"• SL ID: {sl_id}, Stop Price: {sl_price}")

            # 🔄 Step 2: Poll for one of the orders to fill
            start_time = time.time()
            tp_check, sl_check = None, None

            while time.time() - start_time < max_poll_time:
                try:
                    tp_check = exchange.fetch_order(tp_id, symbol)
                except Exception as e:
                    if 'orderNotExist' in str(e):
                        print(f"⏳ TP order not found yet, retrying...")
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

                if tp_check.get('status') == 'closed':
                    filled_tp_price = tp_check.get('average') or tp_check.get('price')
                    print(f"🎯 TP filled at {filled_tp_price}")
                    return {
                        'tp_order': tp_check,
                        'sl_order': sl_check,
                        'status': 'tp_filled',
                        'filled_price': filled_tp_price
                    }

                if sl_check.get('status') == 'closed':
                    filled_sl_price = sl_check.get('average') or sl_check.get('price')
                    print(f"🛑 SL filled at {filled_sl_price}")
                    return {
                        'tp_order': tp_check,
                        'sl_order': sl_check,
                        'status': 'sl_filled',
                        'filled_price': filled_sl_price
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
