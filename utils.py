import pandas as pd
from ta.trend import SMAIndicator
import matplotlib.pyplot as plt
import mplfinance as mpf
import os
import ccxt
from config import KUCOIN_API_KEY, KUCOIN_SECRET_KEY, KUCOIN_PASSPHRASE
from ta.trend import ADXIndicator

def init_kucoin_futures():
    return ccxt.kucoinfutures({
        'apiKey': KUCOIN_API_KEY,
        'secret': KUCOIN_SECRET_KEY,
        'password': KUCOIN_PASSPHRASE,
        'enableRateLimit': True
    })

def set_leverage(exchange, symbol, leverage=10):
    market = exchange.market(symbol)
    try:
        response = exchange.set_leverage(leverage, symbol)
        return response
    except Exception as e:
        return {'error': str(e)}

def place_futures_order(exchange, symbol, side, usdt_amount, tp_price, sl_price, leverage=10):
    try:
        # Set leverage
        set_leverage(exchange, symbol, leverage)

        # Get current price
        ticker = exchange.fetch_ticker(symbol)
        price = ticker['last']
        base_amount = usdt_amount / price

        # Market entry
        entry_order = exchange.create_market_order(
            symbol=symbol,
            side=side,
            amount=round(base_amount, 4),
            params={'leverage': leverage}
        )

        # Determine opposite side for TP/SL
        close_side = 'sell' if side == 'buy' else 'buy'

        # Create TAKE PROFIT conditional order
        tp_order = exchange.create_order(
            symbol=symbol,
            type='takeProfitMarket',
            side=close_side,
            amount=round(base_amount, 4),
            params={
                'stopPrice': round(tp_price, 4),
                'reduceOnly': True,
                'leverage': leverage
            }
        )

        # Create STOP LOSS conditional order
        sl_order = exchange.create_order(
            symbol=symbol,
            type='stopMarket',
            side=close_side,
            amount=round(base_amount, 4),
            params={
                'stopPrice': round(sl_price, 4),
                'reduceOnly': True,
                'leverage': leverage
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

    prev = df.iloc[-2]
    last = df.iloc[-1]

    # Crossover condition (MA10 crosses above MA20)
    crossover = prev['ma10'] < prev['ma20'] and last['ma10'] > last['ma20']

    # Continuation condition (MA10 stays above MA20)
    continuation = last['ma10'] > last['ma20']

    # Shared trend confirmation
    alignment = last['ma20'] > last['ma50']
    momentum = last['close'] > last['ma10']
    confirmed = confirm_trend(df, len(df)-1, 'ma50', lambda ma, close: close > ma, lookahead)

    return (crossover or continuation) and alignment and momentum and confirmed


def check_short_signal(df, lookahead=10):
    if len(df) < 51:
        return False

    prev = df.iloc[-2]
    last = df.iloc[-1]

    crossover = prev['ma10'] > prev['ma20'] and last['ma10'] < last['ma20']
    continuation = last['ma10'] < last['ma20']

    alignment = last['ma20'] < last['ma50']
    momentum = last['close'] < last['ma10']
    confirmed = confirm_trend(df, len(df)-1, 'ma50', lambda ma, close: close < ma, lookahead)

    return (crossover or continuation) and alignment and momentum and confirmed

def save_chart(df, symbol):
    df = df.copy()
    df.index = pd.to_datetime(df['timestamp'])
    add_plot = [
        mpf.make_addplot(df['ma10'], color='blue'),
        mpf.make_addplot(df['ma20'], color='orange'),
        mpf.make_addplot(df['ma50'], color='green')
    ]
    path = f'charts/{symbol.replace("/", "_")}.png'
    mpf.plot(df, type='candle', style='charles', addplot=add_plot, volume=True,
             title=f"{symbol} MA Crossover", savefig=path)
    return path

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