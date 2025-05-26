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

def calculate_trade_levels(price, direction, df, atr_period=7, atr_multiplier_sl=2.0, atr_multiplier_tp=3.0):
    """
    Calculate TP/SL levels using real ATR.

    Parameters:
    - price: Current price
    - direction: 'long' or 'short'
    - df: DataFrame with OHLCV
    - atr_period: Period to use for ATR calculation
    - atr_multiplier_sl: Multiplier for stop-loss distance
    - atr_multiplier_tp: Multiplier for take-profit distance
    """

    if 'ATR' not in df.columns:
        # Calculate True Range
        df['H-L'] = df['high'] - df['low']
        df['H-PC'] = abs(df['high'] - df['close'].shift(1))
        df['L-PC'] = abs(df['low'] - df['close'].shift(1))
        df['TR'] = df[['H-L', 'H-PC', 'L-PC']].max(axis=1)
        df['ATR'] = df['TR'].rolling(window=atr_period).mean()
        df.drop(columns=['H-L', 'H-PC', 'L-PC', 'TR'], inplace=True)

    atr = df['ATR'].iloc[-1]

    # Fallback in case ATR is still NaN
    if atr is None or atr == 0 or pd.isna(atr):
        atr = 0.01  # Reasonable default or consider skipping the trade
        print("⚠️ ATR calculation failed or is too small. Using fallback value.")

    sl_distance = atr * atr_multiplier_sl
    tp_distance = atr * atr_multiplier_tp

    if direction == 'long':
        tp = float(price + tp_distance)
        sl = float(price - sl_distance)
    else:
        tp = float(price - tp_distance)
        sl = float(price + sl_distance)

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

def is_ranging(df, window=50, range_threshold=0.05, adx_threshold=20):
    if len(df) < window:
        return False  # Not enough data to decide

    recent = df[-window:]
    high = recent['high'].max()
    low = recent['low'].min()
    range_pct = (high - low) / low
    adx_recent = df['adx'].iloc[-1]

    # Must have low price movement AND weak trend
    is_range = range_pct < range_threshold and adx_recent < adx_threshold

    # Debugging (optional)
    #print(f"[{df.iloc[-1]['timestamp']}] Range %: {range_pct:.4f}, ADX: {adx_recent:.2f} -> {'RANGE' if is_range else 'TREND'}")

    return is_range


def check_range_trade(df):
    last = df.iloc[-1]

    buy_signal = (
        last['close'] <= last['support'] * 1.02 and  # Looser buffer
        last['rsi'] < 35
    )

    sell_signal = (
        last['close'] >= last['resistance'] * 0.98 and
        last['rsi'] > 65
    )
    
    return buy_signal, sell_signal

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
