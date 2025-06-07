from ta.trend import SMAIndicator
from ta.trend import ADXIndicator
import pandas as pd

    
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
    #  and not is_near_resistance(df)
    if (crossover or continuation) and alignment and momentum and bullish_candle:
        #print(f"LONG SIGNAL TRIGGERED at {last['timestamp']}")
        return True

    return False

def check_short_signal(df, lookahead=10):
    if len(df) < 51:
        return False

    last = df.iloc[-1]
    prev = df.iloc[-2]

    # Crossover condition: MA10 crosses below MA20
    crossover = prev['ma10'] > prev['ma20'] and last['ma10'] < last['ma20']

    # Continuation condition: MA10 remains below MA20
    continuation = last['ma10'] < last['ma20']

    # Trend alignment: MA20 below MA50 (higher timeframe bearish trend)
    alignment = last['ma20'] < last['ma50']

    # Momentum: price below MA10 (bearish momentum)
    momentum = last['close'] < last['ma10']

    # Optional: bearish candle confirmation (close < open)
    bearish_candle = last['close'] < last['open']

    # Avoid signals near support (you can define a function similar to `is_near_resistance`)
    not_near_support = not is_near_support(df)  # You need to implement this function

    if (crossover or continuation) and alignment and momentum and bearish_candle and not_near_support:
       #print(f"SHORT SIGNAL TRIGGERED at {last['timestamp']}")
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

def add_atr_column(df, period=7):
    df = df.copy()
    df['H-L'] = df['high'] - df['low']
    df['H-PC'] = abs(df['high'] - df['close'].shift(1))
    df['L-PC'] = abs(df['low'] - df['close'].shift(1))
    df['TR'] = df[['H-L', 'H-PC', 'L-PC']].max(axis=1)
    df['ATR'] = df['TR'].rolling(window=period).mean()
    df.drop(columns=['H-L', 'H-PC', 'L-PC', 'TR'], inplace=True)
    return df

def calculate_trade_levels(price, direction, df, start_idx, atr_multiplier_sl=2.0, atr_multiplier_tp=2.5):
    if 'ATR' not in df.columns:
        raise ValueError("ATR not computed. Call add_atr_column(df) first.")

    atr = df['ATR'].iloc[start_idx]

    # Fallback if ATR isn't usable
    if pd.isna(atr) or atr == 0:
        atr = price * 0.005  # 0.5% of price as fallback
        print(f"⚠️ Using fallback ATR at index {start_idx}: {atr:.5f}")

    sl_distance = atr * atr_multiplier_sl
    tp_distance = atr * atr_multiplier_tp

    if direction == 'long':
        tp = price + tp_distance
        sl = price - sl_distance
    else:
        tp = price - tp_distance
        sl = price + sl_distance

    return {
        'entry': round(price, 4),
        'take_profit': round(tp, 4),
        'stop_loss': round(sl, 4)
    }

def is_near_support(df, buffer=0.01):
    """
    Returns True if the current price is near the support level within the given buffer percentage.
    """
    last = df.iloc[-1]
    support = last['support']
    price = last['close']

    # Near support means price is within buffer % above support level
    return price <= support * (1 + buffer)

def is_near_resistance(df, threshold=0.01, lookback=50, buffer_multiplier=1.0):
    """
    Checks if the current price is near recent resistance with volatility-adjusted buffer.
    - threshold: percentage distance to consider "near"
    - lookback: number of past candles to define resistance level
    - buffer_multiplier: scales buffer zone based on ATR
    """
    if len(df) < lookback + 1:
        return False  # not enough data

    recent_high = df['high'].iloc[-lookback:].max()
    current_price = df.iloc[-1]['close']

    # Use ATR for dynamic buffer zone
    atr = df['close'].rolling(14).apply(lambda x: max(x) - min(x)).iloc[-1]
    dynamic_buffer = atr * buffer_multiplier if not pd.isna(atr) else current_price * threshold

    return (recent_high - current_price) <= dynamic_buffer


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

def is_ranging(df, window=50, range_threshold=0.05, adx_threshold=25):
    if len(df) < window or 'adx' not in df.columns:
        return False

    recent = df[-window:]
    high = recent['high'].max()
    low = recent['low'].min()
    range_pct = (high - low) / recent['close'].iloc[-1]
    adx_recent = df['adx'].iloc[-1]

    return range_pct < range_threshold and adx_recent < adx_threshold

# def check_range_trade(df):
#     last = df.iloc[-1]

#     buy_signal = (
#         last['close'] <= last['support'] * 1.02 and  # Looser buffer
#         last['rsi'] < 35
#     )

#     sell_signal = (
#         last['close'] >= last['resistance'] * 0.98 and
#         last['rsi'] > 65
#     )
    
#     return buy_signal, sell_signal

def check_range_trade(df):
    last = df.iloc[-1]

    support_buffer = 1.02  # changed from 1.01
    resistance_buffer = 0.98  # changed from 0.99
    buy_signal = (
        last['close'] <= last['support'] * support_buffer
        and last['rsi'] < 35
    )

    sell_signal = (
        last['close'] >= last['resistance'] * resistance_buffer
        and last['rsi'] > 65
    )
    
    return buy_signal, sell_signal


def check_trend_continuation(df):
    if len(df) < 51:
        return False
    last = df.iloc[-1]
    return (
        last['ma10'] > last['ma20'] and
        last['ma20'] > last['ma50'] and
        last['close'] > last['ma10']
    )
