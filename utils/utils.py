import requests
from ta.trend import SMAIndicator
from ta.trend import ADXIndicator
import pandas as pd

import time
import os
from datetime import datetime, timezone
from utils.configUtils import strategy_settings
from config import TELEGRAM_CHAT_ID, TELEGRAM_TOKEN

    
def set_leverage(exchange, symbol, leverage):
    try:
        exchange.set_leverage(
            leverage=leverage,
            symbol=symbol,
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
        if value == 0:
            return 10  # default fallback for zero
        str_val = f"{value:.12f}".rstrip('0')  # support very small floats
        if '.' in str_val:
            return max(len(str_val.split('.')[1]), 6)  # ensure minimum 6 decimals
    return 6  # fallback default

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


def add_atr_column(df, period=7):
    df = df.copy()
    df['H-L'] = df['high'] - df['low']
    df['H-PC'] = abs(df['high'] - df['close'].shift(1))
    df['L-PC'] = abs(df['low'] - df['close'].shift(1))
    df['TR'] = df[['H-L', 'H-PC', 'L-PC']].max(axis=1)
    df['ATR'] = df['TR'].rolling(window=period).mean()
    df.drop(columns=['H-L', 'H-PC', 'L-PC', 'TR'], inplace=True)
    return df

def calculate_trade_levels(price, direction, df, start_idx, strategy_type="trend"):
    if price is None or not isinstance(price, (int, float)):
        raise ValueError(f"Invalid price passed to calculate_trade_levels: {price}")

    if direction not in ["buy", "sell"]:
        raise ValueError(f"Invalid direction: {direction}")

    if start_idx >= len(df) or start_idx < 0:
        raise IndexError(f"start_idx {start_idx} is out of range for DataFrame length {len(df)}")

    if 'ATR' not in df.columns:
        raise ValueError("ATR not computed. Call add_atr_column(df) first.")

    atr = df['ATR'].iloc[start_idx]

    if pd.isna(atr) or atr == 0:
        atr = price * 0.003  # fallback ATR (0.3% of price)
        print(f"⚠️ Using fallback ATR at index {start_idx}: {atr:.10f}")

    config = strategy_settings.get(strategy_type, strategy_settings[strategy_type])

    # Calculate distances
    sl_distance = max(atr * config["atr_sl"], price * config["min_sl_pct"])
    tp_distance = max(atr * config["atr_tp"], price * config["min_tp_pct"])

    # Precision logic
    if price < 0.01:
        precision = 8
    elif price < 1:
        precision = 6
    elif price < 100:
        precision = 4
    else:
        precision = 2

    # Compute levels (before rounding)
    if direction == 'buy':
        raw_tp = price + tp_distance
        raw_sl = price - sl_distance
    else:
        raw_tp = price - tp_distance
        raw_sl = price + sl_distance

    # Round levels
    entry = round(price, precision)
    tp = round(raw_tp, precision)
    sl = round(raw_sl, precision)

    # 🚨 Force stop-loss to be on the correct side of entry
    if direction == 'buy' and sl >= entry:
        sl = round(entry - sl_distance, precision)
    elif direction == 'sell' and sl <= entry:
        sl = round(entry + sl_distance, precision)

    # Recalculate percentages for print
    tp_pct = ((tp - entry) / entry) * 100
    sl_pct = ((entry - sl) / entry) * 100 if direction == 'buy' else ((sl - entry) / entry) * 100

    print(f"🎯 {strategy_type.upper()} trade:")
    print(f"• Entry: {entry}")
    print(f"• TP: {tp} ({tp_pct:.2f}%)")
    print(f"• SL: {sl} ({sl_pct:.2f}%)")
    print(f"• ATR: {atr:.6f}")

    return {
        'entry': entry,
        'take_profit': tp,
        'stop_loss': sl
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

def is_near_resistance(df, threshold=0.01, lookback=20, buffer_multiplier=1.0):
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
    if (crossover or continuation) and alignment and momentum and bullish_candle and not is_near_resistance(df):
        #log_event(f"LONG SIGNAL TRIGGERED at {last['timestamp']}")
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
    # not_near_support = not is_near_support(df)  # You need to implement this function

    if (crossover or continuation) and alignment and momentum and bearish_candle and not is_near_support(df) :
        #log_event(f"SHORT SIGNAL TRIGGERED at {last['timestamp']}")
        return True

    return False

# Log rotation: max size before rotating (5 MB), keep this many old logs
MAX_LOG_BYTES = 5 * 1024 * 1024
LOG_BACKUP_COUNT = 2

def _rotate_log_if_needed():
    """Rotate logs/trades.log if it exceeds MAX_LOG_BYTES."""
    log_path = 'logs/trades.log'
    if not os.path.exists(log_path):
        return
    if os.path.getsize(log_path) < MAX_LOG_BYTES:
        return
    # Remove oldest backup if it exists
    oldest = f'{log_path}.{LOG_BACKUP_COUNT}'
    if os.path.exists(oldest):
        os.remove(oldest)
    # Shift backups: .2 -> .3, .1 -> .2, current -> .1
    for i in range(LOG_BACKUP_COUNT - 1, 0, -1):
        src = f'{log_path}.{i}'
        dst = f'{log_path}.{i + 1}'
        if os.path.exists(src):
            os.rename(src, dst)
    os.rename(log_path, f'{log_path}.1')

def log_event(text):
    os.makedirs('logs', exist_ok=True)
    _rotate_log_if_needed()
    log_text = f"[{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')}] {text}"
    print(log_text)
    with open('logs/trades.log', 'a') as f:
        f.write(log_text + '\n')




def get_filled_price(order):
    """
    Returns the actual filled price from a KuCoin order object.

    Priority:
    1. Use 'average' if available
    2. If not, calculate using 'cost' / 'filled' if filled > 0
    3. Fallback to 'price' if no fill info
    """
    if not order:
        return None

    avg = order.get('average')
    filled = float(order.get('filled', 0))
    cost = float(order.get('cost', 0))
    price = order.get('price')

    if avg:
        return float(avg)
    elif filled > 0 and cost > 0:
        return round(cost / filled, 8)  # Rounded for consistency
    elif price:
        return float(price)
    else:
        return None

MIN_ABS_DISTANCE = 0.005  # Minimum absolute distance from entry
MIN_SL_PCT = 0.10      # Minimum % distance for SL (10%)
MIN_TP_PCT = 0.15       # Minimum % distance for TP (15%)

def safe_place_tp_sl(tp_price, sl_price, entry_price, direction, symbol, max_attempts=3):
    try:
        if not tp_price or not sl_price:
            print(f"❌ Missing TP or SL. TP: {tp_price}, SL: {sl_price}")
            return None

        tp_price = float(tp_price)
        sl_price = float(sl_price)
        entry_price = float(entry_price)

        for attempt in range(1, max_attempts + 1):
            multiplier = 1 + 0.1 * (attempt - 1)

            # Compute TP/SL distances (signed)
            tp_dist = (tp_price - entry_price) * multiplier
            sl_dist = (sl_price - entry_price) * multiplier

            if direction == 'buy':
                tp_adj = entry_price + abs(tp_dist)
                sl_adj = entry_price - abs(sl_dist)
                if tp_adj <= entry_price or sl_adj >= entry_price:
                    print(f"❌ Invalid TP/SL for LONG at attempt {attempt}: TP={tp_adj}, SL={sl_adj}")
                    continue
            else:  # sell
                tp_adj = entry_price - abs(tp_dist)
                sl_adj = entry_price + abs(sl_dist)
                if tp_adj >= entry_price or sl_adj <= entry_price:
                    print(f"❌ Invalid TP/SL for SHORT at attempt {attempt}: TP={tp_adj}, SL={sl_adj}")
                    continue

            tp_pct = ((tp_adj - entry_price) / entry_price) * 100
            sl_pct = ((sl_adj - entry_price) / entry_price) * 100

            print(f"✅ TP/SL validated on attempt {attempt} for {symbol}:")
            print(f"• Entry: {entry_price}")
            print(f"• TP: {tp_adj:.6f} ({tp_pct:.2f}%)")
            print(f"• SL: {sl_adj:.6f} ({sl_pct:.2f}%)")
            return {
                'take_profit': round(tp_adj, 8),
                'stop_loss': round(sl_adj, 8),
                'valid': True
            }

        print(f"❌ Failed to validate TP/SL for {symbol} after {max_attempts} attempts.")
        return None

    except Exception as e:
        print(f"❌ Error in safe_place_tp_sl for {symbol}: {e}")
        return None
