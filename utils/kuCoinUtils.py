
import ccxt
from config import KUCOIN_API_KEY, KUCOIN_SECRET_KEY, KUCOIN_PASSPHRASE
import time

from utils.coinGeckoData import fetch_market_caps
from utils.utils import get_decimal_places, log_event



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
        #print(f"✅ Loaded {len(markets)} markets.")
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

    print(f"🔥 Top {top_n} pairs filtered by market cap > {min_market_cap_usd} USD and volume > {min_volume} USD:")

    return sorted_pairs


def place_entry_order_with_fallback(exchange, symbol, side, amount, entry_price, leverage, tp_price, sl_price):
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
        #                     'takeProfit': {
        #     'price': tp_price,            # Your TP price
        #     'type': 'limit',
        #     'reduceOnly': True
        # },
        # 'stopLoss': {
        #     'price': sl_price,            # Your SL price
        #     'type': 'limit',
        #     'reduceOnly': True
        # }
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

def place_futures_order(exchange, symbol, side, usdt_amount, tp_price, sl_price, leverage=10):
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
        
        print(f"🧪 Raw TP: {tp_price}, Raw SL: {sl_price}, Precision: {price_precision}")
        # Round TP/SL
        tp_price = round(tp_price, price_precision)
        sl_price = round(sl_price, price_precision)

        if tp_price < min_price or sl_price < min_price:
            return {'status': 'error', 'message': f"TP/SL price too low. TP: {tp_price}, SL: {sl_price}, Min: {min_price}"}

        # Fetch balance
        balance = exchange.fetch_balance({'type': 'future'})
        available = balance['free'].get('USDT', 0)
        print(f"💰 Available USDT Balance (Futures): {balance}")

        # if available < usdt_amount:
        #     return {'status': 'error', 'message': f"Insufficient balance. Required: {usdt_amount}, Available: {available}"}

        # ✅ Place Entry Order
        entry_order = place_entry_order_with_fallback(exchange, symbol, side, amount, entry_price, leverage, tp_price, sl_price)

        # if not entry_order or not isinstance(entry_order, dict) or 'id' not in entry_order:
        #     return {'status': 'error', 'message': f"Entry order failed: {entry_order}"}

        # ✅ Wait for the entry order to fill
        # for _ in range(15):
        #     order_status = exchange.fetch_order(entry_order['id'], symbol)
        #     if order_status['status'] == 'closed':
        #         break
        #     time.sleep(1)
        # else:
        #     return {'status': 'error', 'message': 'Entry order not filled in time'}

        order_id = entry_order['id']

        print(f"❌ CHECK ORDER ID BEFORE FETCHING: {entry_order}")
        # 🕒 Poll for order fill
        max_wait_seconds = 100
        poll_interval = 1

        for _ in range(max_wait_seconds):
            try:
                order_status = exchange.fetch_order(order_id, symbol)
                if order_status['status'] == 'done':  # or 'done' depending on exchange
                    print(f"✅ Entry order {order_id} filled.")
                    break
                else:
                    log_event(f"⏳ Waiting for order {order_id} to fill, current status: {order_status['status']}")
            except Exception as e:
                print(f"❌ Error fetching order status: {e}")
            time.sleep(poll_interval)
        else:
            return {'status': 'error', 'message': 'Entry order not filled in time'}

        print(f"❌ CHECK ORDER STATUS BEFORE TP/SL: {order_status}")
        tp_sl_result = place_tp_sl_orders(exchange, symbol, side, amount, tp_price, sl_price)

        if tp_sl_result['status'] != 'success':
            log_event(f"❌ TP/SL placement failed: {tp_sl_result['message']}")
        else:
            log_event(f"📈 TP and 📉 SL orders successfully placed.: {tp_sl_result}")
            return {
                    'status': 'success',
                    'entry_order': entry_order,
                    'tp_order': tp_sl_result['tp_order'],
                    'sl_order': tp_sl_result['sl_order'],
                }

    except Exception as e:
        return {'status': 'error', 'message': str(e)}


def place_tp_sl_orders(exchange, symbol, side, amount, tp_price, sl_price):
    close_side = 'sell' if side == 'buy' else 'buy'

    try:
        # 📈 Take-Profit Order (limit reduce-only)
        tp_order = exchange.create_order(
            symbol=symbol,
            type='market',
            side=close_side,
            amount=amount,
            price=tp_price,
            params={
                'reduceOnly': True,
                'takeProfitPrice': tp_price,
                'stopPriceType': 'TP'

            }
        )

        # # 📉 Stop-Loss Order (stop-market reduce-only)
        sl_order = exchange.create_order(
            symbol=symbol,
            type='market',  # stop-limit order
            side=close_side,   # or 'buy' if closing a short
            amount=amount,
            price=sl_price,  # order execution price once stop triggers
            params={
                'stop': 'down' if close_side == 'sell' else 'up',            # 'down' for stop-sell (long SL), 'up' for stop-buy (short SL)
                'stopPrice': sl_price, # trigger level
                'reduceOnly': True,
                "stopType": "loss",
                #'stopPriceType': 'SL'
                
            }
        )

        log_event("✅ TP and SL orders placed.")
        return {
            'tp_order': tp_order,
            'sl_order': sl_order,
            'status': 'success'
        }

    except Exception as e:
        return {'status': 'error', 'message': f"Failed to place TP/SL orders: {str(e)}"}