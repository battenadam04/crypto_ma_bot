import pandas as pd
from ta.trend import SMAIndicator
import matplotlib.pyplot as plt
import mplfinance as mpf
import os
import ccxt
from config import KUCOIN_API_KEY, KUCOIN_SECRET_KEY, KUCOIN_PASSPHRASE
from ta.trend import ADXIndicator


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

def has_max_open_orders():
    try:
        kucoin_futures = init_kucoin_futures()
        positions = kucoin_futures.fetch_positions()
        for p in positions:
            if float(p['contracts']) > 0:
                print(f"📈 Open Position: {p['symbol']}, Size: {p['contracts']}, Side: {p['side']}")
        return len(positions) > 3
    except Exception as e:
        print(f"❌ Error fetching open orders: {e}")
        return False

def set_leverage(exchange, symbol, leverage=10):
    market = exchange.market(symbol)
    try:
        response = exchange.set_leverage(leverage, symbol)
        return response
    except Exception as e:
        return {'error': str(e)}
    
def set_leverage(exchange, symbol, leverage):
    try:
        exchange.set_leverage(
            leverage=leverage,
            symbol=symbol,
            #params={"marginMode": "cross"}  # ✅ Required for KuCoin Futures
        )
    except Exception as e:
        print(f"⚠️ Failed to set leverage for {symbol}: {str(e)}")

def set_margin_mode(exchange, symbol, mode='cross'):
    try:
        exchange.set_margin_mode(
            marginMode=mode,
            symbol=symbol
        )
        print(f"✅ Margin mode set to {mode} for {symbol}")
    except Exception as e:
        print(f"⚠️ Failed to set margin mode for {symbol}: {str(e)}")

def get_decimal_places(value):
    if isinstance(value, int):
        return 0
    elif isinstance(value, float):
        str_val = f"{value:.8f}".rstrip('0')  # limit to 8 decimals
        if '.' in str_val:
            return len(str_val.split('.')[1])
    return 0


def place_futures_order(exchange, symbol, side, usdt_amount, tp_price, sl_price, leverage=10):
    try:
        exchange.load_markets()
        market = exchange.market(symbol)

        # Get current price
        ticker = exchange.fetch_ticker(symbol)
        price = ticker['last']
        amount_precision = get_decimal_places(market['precision']['amount'])
        price_precision = get_decimal_places(market['precision']['price'])
        # 2. Get the contract size (usually 1 for KuCoin linear futures, but confirm)
        contract_value = float(market.get('contractSize', 1))  # Default to 1 if not defined

        # 3. Calculate the notional value per unit of base currency
        price = ticker['last']
        notional_per_unit = price * contract_value

        # 4. Apply leverage
        max_notional = usdt_amount * leverage

        # 5. Calculate the amount of base asset you can afford at leverage
        raw_amount = max_notional / notional_per_unit

        # 6. Round to allowed precision
        amount = round(raw_amount, amount_precision)

        # Determine entry price with small buffer
        buffer = 0.05
        entry_price = price * (1 + buffer / 100) if side == 'buy' else price * (1 - buffer / 100)
        entry_price = round(entry_price, price_precision)

        balance = exchange.fetch_balance({'type': 'future'})  # Specify futures account
        available = balance['free'].get('USDT', 0)
        print(f"💰 Available {'USDT'} Balance (Futures): {available}")

        # Entry Order
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

        close_side = 'sell' if side == 'buy' else 'buy'

        # Take-Profit Order (use 'takeProfit' type)
        tp_order = exchange.create_order(
            symbol=symbol,
            type='takeProfit',
            side=close_side,
            amount=amount,
            price=round(tp_price, price_precision),
            params={
                'reduceOnly': True,
                'stopPrice': round(tp_price, price_precision),
                'triggerType': 'last',  # or 'mark'
            }
        )

        # Stop-Loss Order (use 'stopLoss' type)
        sl_order = exchange.create_order(
            symbol=symbol,
            type='stopLoss',
            side=close_side,
            amount=amount,
            price=round(sl_price, price_precision),
            params={
                'reduceOnly': True,
                'stopPrice': round(sl_price, price_precision),
                'triggerType': 'last',
            }
        )


        return {
            'status': 'success',
            'entry_order': entry_order,
            'tp_order': tp_order,
            'sl_order': sl_order
        }

    except Exception as e:
        return {'status': 'error', 'message': str(e)}



def calculate_mas(df):
    df['ma10'] = SMAIndicator(df['close'], window=10).sma_indicator()
    df['ma20'] = SMAIndicator(df['close'], window=20).sma_indicator()
    df['ma50'] = SMAIndicator(df['close'], window=50).sma_indicator()
    return df

def check_ma_crossover(prev_ma1, prev_ma2, curr_ma1, curr_ma2, direction="long"):
    if direction == "long":
        return prev_ma1 < prev_ma2 and curr_ma1 > curr_ma2
    else:
        return prev_ma1 > prev_ma2 and curr_ma1 < curr_ma2

def confirm_trend(df, last_idx, ma_key, condition_func, lookahead):
    for j in range(1, lookahead + 1):
        idx = last_idx + j
        if idx >= len(df):
            break
        if condition_func(df.iloc[idx][ma_key], df.iloc[idx]['close']):
            return True
    return False

def check_long_signal(df, lookahead=10):
    if len(df) < 51:
        return False

    last = df.iloc[-1]
    prev = df.iloc[-2]

    # Crossover condition: MA10 crosses above MA20
    crossover = prev['ma10'] < prev['ma20'] and last['ma10'] > last['ma20']

    # Continuation condition: MA10 remains above MA20
    continuation = last['ma10'] > last['ma20']

    # Trend alignment: MA20 above MA50 (higher timeframe trend)
    alignment = last['ma20'] > last['ma50']

    # Momentum: price above MA10 (showing bullish momentum)
    momentum = last['close'] > last['ma10']

    # Optional: bullish candle confirmation (price closed higher than open)
    bullish_candle = last['close'] > last['open']

    # Combine conditions: crossover or continuation + momentum + alignment + bullish candle
    if (crossover or continuation) and alignment and momentum and bullish_candle and not is_near_resistance(df):
        print(f"LONG SIGNAL TRIGGERED at {last['timestamp']}")
        return True

    return False

def check_short_signal(df, lookahead=10):
    if len(df) < 51:
        return False

    last = df.iloc[-1]

    # Basic bearish structure: MA10 < MA20 < MA50 and price below MA10
    condition = (
        last['ma10'] < last['ma20'] and
        last['ma20'] < last['ma50'] and
        last['close'] < last['ma10']
    )

    # Optional: basic bearish candle confirmation
    bearish_candle = last['close'] < last['open']
    small_lower_wick = (last['close'] - last['low']) < (last['high'] - last['low']) * 0.3

    if condition and bearish_candle and small_lower_wick:
        print(f"SHORT SIGNAL TRIGGERED at {last['timestamp']}")
        return True

    return False

# def save_chart(df, symbol):
#     df = df.copy()
#     df.index = pd.to_datetime(df['timestamp'])
#     add_plot = [
#         mpf.make_addplot(df['ma10'], color='blue'),
#         mpf.make_addplot(df['ma20'], color='orange'),
#         mpf.make_addplot(df['ma50'], color='green')
#     ]
#     path = f'charts/{symbol.replace("/", "_")}.png'
#     mpf.plot(df, type='candle', style='charles', addplot=add_plot, volume=True,
#              title=f"{symbol} MA Crossover", savefig=path)
#     return path

def calculate_trade_levels(price, direction, tp_pct=10.0, sl_pct=1.0):
    if direction == 'long':
        tp = price * (1 + tp_pct / 100)
        sl = price * (1 - sl_pct / 100)
    else:
        tp = price * (1 - tp_pct / 100)
        sl = price * (1 + sl_pct / 100)
    return {
        'entry': round(price, 4),
        'take_profit': round(tp, 4),
        'stop_loss': round(sl, 4)
    }

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

def is_near_resistance(df, threshold=0.005, lookahead=10):  # 0.5% proximity
    recent_high = df['high'].iloc[-lookahead:].max()
    current_price = df.iloc[-1]['close']
    return (recent_high - current_price) / recent_high < threshold

def is_weak_trend(df, period=14, threshold=20):
    adx = ADXIndicator(df['high'], df['low'], df['close'], window=period)
    df['adx'] = adx.adx()
    return df['adx'].iloc[-1] < threshold

def are_mas_compressed(df, threshold_pct=0.3):
    last = df.iloc[-1]
    ma_values = [last['ma10'], last['ma20'], last['ma50']]
    max_ma = max(ma_values)
    min_ma = min(ma_values)
    spread = ((max_ma - min_ma) / min_ma) * 100
    return spread < threshold_pct

def is_consolidating(df, lookback=20, threshold_pct=1.5):
    recent = df.tail(lookback)
    high = recent['high'].max()
    low = recent['low'].min()
    range_pct = ((high - low) / low) * 100

    return range_pct < threshold_pct and are_mas_compressed(df)  # Returns True if it's consolidating

def should_trade(df):
    if is_consolidating(df):
        return False
    if are_mas_compressed(df):
        return False
    if is_weak_trend(df):
        return False
    return True


def is_early_breakout(df):
    last = df.iloc[-1]
    prev = df.iloc[-2]

    # MA10 crossing MA20
    crossover = prev['ma10'] < prev['ma20'] and last['ma10'] > last['ma20']

    # Both are still under or near MA50
    under_ma50 = last['ma10'] < last['ma50'] and last['ma20'] < last['ma50']

    # Price is approaching MA50
    near_ma50 = abs(last['close'] - last['ma50']) / last['ma50'] < 0.005  # within 0.5%

    return crossover and (under_ma50 or near_ma50)

def is_ranging(df, window=50, threshold=0.02):
    high = df['high'][-window:].max()
    low = df['low'][-window:].min()
    range_pct = (high - low) / low
    return range_pct < threshold  # e.g., less than 2% movement

def check_range_long(df):
    support = df['low'][-20:].min()
    last_close = df.iloc[-1]['close']
    return last_close <= support * 1.01  # near support

def check_range_short(df):
    resistance = df['high'][-20:].max()
    last_close = df.iloc[-1]['close']
    return last_close >= resistance * 0.99  # near resistance

def check_trend_continuation(df):
    if len(df) < 51:
        return False
    last = df.iloc[-1]
    return (
        last['ma10'] > last['ma20'] and
        last['ma20'] > last['ma50'] and
        last['close'] > last['ma10']
    )

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
