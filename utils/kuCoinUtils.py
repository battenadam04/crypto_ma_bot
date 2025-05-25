
import ccxt
from config import KUCOIN_API_KEY, KUCOIN_SECRET_KEY, KUCOIN_PASSPHRASE
import time

from utils.utils import get_decimal_places



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


def can_place_order(symbol):
    try:
        kucoin_futures = init_kucoin_futures()
        positions = kucoin_futures.fetch_positions()

        open_positions = [
            p for p in positions if float(p['contracts']) > 0
        ]

        for p in open_positions:
            print(f"📈 Open Position: {p['symbol']}, Size: {p['contracts']}, Side: {p['side']}")

        # Block if too many open positions
        if len(open_positions) >= MAX_OPEN_ORDERS:
            print(f"⛔ Max open positions reached ({MAX_OPEN_ORDERS}). Skipping {symbol}.")
            return False

        # Block if this symbol hit its loss cap
        if loss_tracker.get(symbol, 0) >= MAX_LOSSES:
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


def get_top_futures_tradable_pairs(exchange, quote='USDT', top_n=15):
    print("⏳ Loading KuCoin Futures markets...")
    try:
        markets = exchange.load_markets()
        print(f"✅ Loaded {len(markets)} markets.")
    except Exception as e:
        print("❌ Error loading markets:", e)
        return []

    stablecoins = {'USDT', 'USDC', 'BUSD', 'TUSD', 'DAI', 'FDUSD', 'UST'}
    volume_data = []

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

        # Retrieve volume information
        vol_value = market.get('info', {}).get('volumeOf24h')
        if vol_value is None:
            print(f"Skipping {market}: Missing volValue.")
            continue

        try:
            volume = float(vol_value)
            volume_data.append((symbol, volume))
        except ValueError:
            print(f"Skipping {symbol}: Invalid volValue '{vol_value}'.")
            continue

    # Sort by volume in descending order and select top N pairs
    top_pairs = sorted(volume_data, key=lambda x: x[1], reverse=True)[:top_n]
    print(f"🔥 Top {top_n} tradable futures pairs:", top_pairs)

    return [pair[0] for pair in top_pairs]


def place_entry_order_with_fallback(exchange, symbol, side, amount, entry_price, leverage):
    try:
        # First attempt with 'isolated'
        return exchange.create_limit_order(
            symbol=symbol,
            side=side,
            amount=amount,
            price=entry_price,
            params={
                'leverage': int(leverage),
                'marginMode': 'isolated'
            }
        )
    except Exception as e:
        if 'margin mode' in str(e).lower():
            print("⚠️ Isolated margin failed. Retrying with 'cross' margin mode...")
            try:
                # Retry with 'cross'
                return exchange.create_limit_order(
                    symbol=symbol,
                    side=side,
                    amount=amount,
                    price=entry_price,
                    params={
                        'leverage': int(leverage),
                        'marginMode': 'cross'
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
        price_precision = get_decimal_places(market['precision']['price'])

        # Minimums
        min_price = market.get('limits', {}).get('price', {}).get('min', 0)
        min_amount = market.get('limits', {}).get('amount', {}).get('min', 0)

        # Get current price
        ticker = exchange.fetch_ticker(symbol)
        price = ticker['last']
        contract_value = float(market.get('contractSize', 1))

        if not price or price <= 0:
            return {'status': 'error', 'message': f"Invalid market price for {symbol}: {price}"}

        # Notional & leverage
        max_notional = usdt_amount * leverage
        raw_amount = max_notional / (price * contract_value)
        amount = round(raw_amount, amount_precision)

        # Skip if amount is below minimum
        if amount < min_amount:
            return {'status': 'error', 'message': f"Amount {amount} is below min allowed: {min_amount}"}

        # Entry price (with buffer)
        buffer = 0.05
        entry_price = price * (1 + buffer / 100) if side == 'buy' else price * (1 - buffer / 100)
        entry_price = round(entry_price, price_precision)

        if entry_price < min_price:
            return {'status': 'error', 'message': f"Entry price {entry_price} is below min allowed: {min_price}"}

        # Round TP/SL and validate
        tp_price = round(tp_price, price_precision)
        sl_price = round(sl_price, price_precision)

        if tp_price < min_price or sl_price < min_price:
            return {'status': 'error', 'message': f"TP/SL price too low. TP: {tp_price}, SL: {sl_price}, Min: {min_price}"}

        # Fetch available balance
        balance = exchange.fetch_balance({'type': 'future'})
        available = balance['free'].get('USDT', 0)
        print(f"💰 Available USDT Balance (Futures): {available}")

        if entry_price > 0:

            # Place Entry Order
            entry_order = exchange.create_limit_order(
                symbol=symbol,
                side=side,
                amount=amount,
                price=entry_price,
                params={
                    'leverage': int(leverage),
                    'marginMode': 'isolated'
                }
            )

            order_id = entry_order['id']

            # 🕒 Poll until filled or timeout
            for _ in range(15):  # Retry up to 15 times (~15 seconds)
                order_status = exchange.fetch_order(order_id, symbol)
                if order_status['status'] == 'closed':
                    break
                time.sleep(1)
            else:
                return {'status': 'error', 'message': 'Entry order not filled in time'}
            
            close_side = 'sell' if side == 'buy' else 'buy'

            # Take Profit (stop-limit)
            tp_order = exchange.create_order(
                symbol=symbol,
                type='lLimit',           # or 'stopLimit' if your ccxt supports it explicitly
                side=close_side,
                amount=amount,
                price=tp_price,
                params={
                    'leverage': 10,
                    'stopPrice': tp_price,     # trigger price
                    'reduceOnly': True,
                    'timeInForce': 'GTC',
                    'closePosition': False,
                    'triggerType': 'LastPrice',  # or 'MarkPrice', check your exchange docs
                    'stopPriceType': 'TP'
                }
            )

            # Stop Loss (stop-limit)
            sl_order = exchange.create_order(
                symbol=symbol,
                type='limit',          # or 'stopLimit'
                side=close_side,
                amount=amount,
                price=sl_price,
                params={
                    'leverage': 10,
                    'stopPrice': sl_price,
                    'reduceOnly': True,
                    'timeInForce': 'GTC',
                    'closePosition': False,
                    'triggerType': 'LastPrice',
                    'stopPriceType': 'SL'
                }
            )
            
            print(f"CHECKING TP {tp_order}")
            print(f"CHECKING SL {sl_order}")

            return {
                'status': 'success',
                'entry_order': entry_order,
                'tp_order': tp_order,
                'sl_order': sl_order
             }

        else:
            return {'status': 'error', 'Balance below entry price requirement': {balance}}

    except Exception as e:
        return {'status': 'error', 'message': str(e)}
