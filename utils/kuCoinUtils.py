
import ccxt
from config import KUCOIN_API_KEY, KUCOIN_SECRET_KEY, KUCOIN_PASSPHRASE, TRADING_SIGNALS_ONLY
import time
from datetime import datetime, timezone

from utils.coinGeckoData import fetch_market_caps
from utils.utils import calculate_trade_levels, get_decimal_places, get_filled_price, log_event, safe_place_tp_sl, send_telegram


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
MAX_LOSSES = 5
MAX_OPEN_ORDERS = 3


# TODO: update loss tracker
def can_place_order(symbol):
    try:
        kucoin_futures = init_kucoin_futures()
        positions = kucoin_futures.fetch_positions()

        open_positions = [
            p for p in positions if float(p['contracts']) > 0
        ]

        for p in open_positions:
            if p['symbol'] == symbol:
                return False, f"{symbol} already in open position."

        if len(open_positions) >= MAX_OPEN_ORDERS:

            return False, f"Max open positions reached ({MAX_OPEN_ORDERS})."

        if loss_tracker.get(symbol, 0) >= MAX_LOSSES:
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

def place_futures_order(exchange, df, symbol, side, capital, leverage=10, strategy_type="range"):
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

        balance = exchange.fetch_balance()
        usdt_balance = balance['free'].get('USDT', 0)

        if usdt_balance == 0:
            print("❌ No available USDT balance for futures trading.")
            return None

        # Use only a portion of balance (e.g., 5% of capital)
        capital_pct=0.25
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

        # Entry price (with buffer)
        buffer = 0.05
        raw_entry_price = price * (1 + buffer / 100) if side == 'buy' else price * (1 - buffer / 100)

        if raw_entry_price <= min_price:
            return {'status': 'error', 'message': f"Raw entry price {raw_entry_price} is below min allowed: {min_price}"}

        entry_price = round(raw_entry_price, price_precision)

        if entry_price <= 0:
            return {'status': 'error', 'message': f"Final entry price is invalid: {entry_price}"}
        

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

            # 🔒 Step 3: Place TP and SL with retry
            attempt = 1
            while True:
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

                    attempt += 1
                    print(f"🔁 Retry #{attempt} in 2 seconds...")
                    time.sleep(2)
                else:
                    print("🚫 Skipping order due to unsafe TP/SL values.")
                    continue

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

    for attempt in range(1, max_retries + 1):
        print(f"🔁 Order attempt {attempt}: Creating TP/SL orders...")

        try:
            # Get current market price to validate SL placement
            ticker = exchange.fetch_ticker(symbol)
            last_price = ticker.get('last')
            if last_price is None:
                raise Exception("Couldn't fetch current market price.")

            # 🚨 Validate TP/SL logic before placing
            # if not is_valid_tp_sl(tp_price, sl_price, filled_price, last_price, side):
            #     print(f"⚠️ Invalid TP/SL for current conditions. Adjusting..TP:{tp_price}, SL:{sl_price}")

            #     # Apply minimal offset adjustment to make them valid
            #     adjust_pct = 1  #1% nudge
            #     if side == 'buy':
            #         tp_price = max(filled_price * (1 + adjust_pct), tp_price)
            #         sl_price = min(filled_price * (1 - adjust_pct), sl_price)
            #     else:
            #         tp_price = min(filled_price * (1 - adjust_pct), tp_price)
            #         sl_price = max(filled_price * (1 + adjust_pct), sl_price)

            #     print(f"🛠️ Adjusted TP: {tp_price}, SL: {sl_price}")


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
                    'stopPriceType': 'TP'
                }
            )

            tp_id = tp_order['id']
            sl_id = sl_order['id']
            print(f"✅ TP/SL orders successfully placed.")
            # print(f"• TP ID: {tp_id}, Price: {tp_price}")
            # print(f"• SL ID: {sl_id}, Stop Price: {sl_price}")

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

def fetch_kucoin_balance_and_notify():
    try:
        global start_of_day_balance
        balance = init_kucoin_futures().fetch_balance()
        start_of_day_balance = balance
        usdt = balance['total'].get('USDT', 0)
        available = balance['free'].get('USDT', 0)
        timestamp = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')

        message = (
            f"📊 KuCoin Futures Balance at {timestamp}:\n"
            f"Total USDT: {usdt:.2f}\n"
            f"Available USDT: {available:.2f}"
        )
        send_telegram(message)
        print("✅ Balance sent to Telegram.")
        return balance
    except Exception as e:
        print("❌ Error fetching balance or sending message:", e)