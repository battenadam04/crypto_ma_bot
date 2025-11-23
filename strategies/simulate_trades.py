import sys
import os
from datetime import datetime, timedelta

import pandas as pd
import pandas_ta as ta
import time

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../')))

from utils.utils import (
    check_long_signal, check_short_signal, calculate_trade_levels,add_atr_column, check_range_trade, is_ranging, log_event,
)
from utils.exchangeUtils import init_exchange, get_top_tradable_pairs

exchange = init_exchange()
PAIRS = get_top_tradable_pairs(exchange, quote='USDT', top_n=20)


def fetch_data(pair, timeframe='5m', days=90):
    all_ohlcv = []
    now = datetime.now()
    since = int((now - timedelta(days=days)).timestamp() * 1000)

    limit = 200  # hard limit
    max_tries = 30  #increase this if needed
    loops = 0

    while loops < max_tries:
        ohlcv = exchange.fetch_ohlcv(pair, timeframe=timeframe, since=since, limit=limit)

        if not ohlcv:
            break

        all_ohlcv.extend(ohlcv)

        last_timestamp = ohlcv[-1][0]
        since = last_timestamp + 60_000  # advance 1 minute
        loops += 1

        time.sleep(0.3)  # rate limit buffer

        # Optional: stop early if already have enough data
        if len(all_ohlcv) >= 1000:
            break

    if not all_ohlcv:
        return pd.DataFrame()

    # Remove duplicates (sometimes exchanges return overlapping data)
    seen = set()
    unique_ohlcv = []
    for row in all_ohlcv:
        if row[0] not in seen:
            unique_ohlcv.append(row)
            seen.add(row[0])

    df = pd.DataFrame(unique_ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')

    # Add indicators
    df['ma10'] = df['close'].rolling(10).mean()
    df['ma20'] = df['close'].rolling(20).mean()
    df['ma50'] = df['close'].rolling(50).mean()
    df['rsi'] = df.ta.rsi(length=14)
    df['adx'] = df.ta.adx(length=14)['ADX_14']
    df['support'] = df['low'].rolling(window=50).min()
    df['resistance'] = df['high'].rolling(window=50).max()

    return df

def fetch_higher_timeframe_data(pair, timeframe='15m', days=90):
    all_ohlcv = []
    now = datetime.now()
    since = int((now - timedelta(days=days)).timestamp() * 1000)

    limit = 200
    loops = 0
    while loops < 30:
        ohlcv = exchange.fetch_ohlcv(pair, timeframe=timeframe, since=since, limit=limit)
        if not ohlcv:
            break
        all_ohlcv.extend(ohlcv)
        last_timestamp = ohlcv[-1][0]
        since = last_timestamp + 60_000 * 15  # advance 1h
        loops += 1
        time.sleep(0.3)
        if len(all_ohlcv) >= 1000:
            break

    if not all_ohlcv:
        return pd.DataFrame()

    seen = set()
    unique_ohlcv = []
    for row in all_ohlcv:
        if row[0] not in seen:
            unique_ohlcv.append(row)
            seen.add(row[0])

    df = pd.DataFrame(unique_ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
    df['ma20'] = df['close'].rolling(20).mean()
    df['ma50'] = df['close'].rolling(50).mean()
    return df




def check_trade_outcome(df, start_idx, direction, entry_price, max_lookahead=50, strategy="trend"):
    df = add_atr_column(df, period=7)
    levels = calculate_trade_levels(entry_price, direction, df, start_idx, strategy)
    tp, sl = levels['take_profit'], levels['stop_loss']

    for j in range(1, max_lookahead + 1):
        if start_idx + j >= len(df):
            break
        high, low = df.iloc[start_idx + j][['high', 'low']]
        if direction == 'long':
            if high >= tp: return 'win'
            if low <= sl: return 'loss'
        else:
            if low <= tp: return 'win'
            if high >= sl: return 'loss'

    # Final fallback: resolve based on final close price
    final_close = df.iloc[min(len(df)-1, start_idx + max_lookahead)]['close']
    if direction == 'long':
        return 'win' if final_close > entry_price else 'loss'
    else:
        return 'win' if final_close < entry_price else 'loss'

def simulate_combined_strategy(pair, df_5m,df_1h):
    long_wins = long_losses = long_none = 0
    short_wins = short_losses = short_none = 0
    strategy_used = []

    for i in range(60, len(df_5m) - 10):
        slice_df = df_5m.iloc[:i+1]
        current = df_5m.iloc[i]
        entry_price = float(current['close'])

        # Find nearest 1h candle for current 5m timestamp
        curr_time = df_5m.iloc[i]['timestamp']
        htf_slice = df_1h[df_1h['timestamp'] <= curr_time].iloc[-5:]

        if len(htf_slice) < 5:
            continue  # not enough higher timeframe data

        ma20_slope = htf_slice['ma20'].iloc[-1] - htf_slice['ma20'].iloc[0]

        trend_up = (
            htf_slice['ma20'].iloc[-1] > htf_slice['ma50'].iloc[-1] and
            htf_slice['ma20'].iloc[-1] > htf_slice['ma20'].iloc[-5] and
            ma20_slope > 0
        )

        trend_down = (
            htf_slice['ma20'].iloc[-1] < htf_slice['ma50'].iloc[-1] and
            htf_slice['ma20'].iloc[-1] < htf_slice['ma20'].iloc[-5] and
            ma20_slope < 0
        )
            #and not is_near_resistance(slice_df)
        if check_long_signal(slice_df) and trend_up:
                result = check_trade_outcome(df_5m, i, 'buy', entry_price, 50, 'trend')
                strategy_used.append('ma')
                if result == 'win':
                    long_wins += 1
                elif result == 'loss':
                    long_losses += 1
                else:
                    long_none += 1
        elif check_short_signal(slice_df) and trend_down :
                result = check_trade_outcome(df_5m, i, 'sell', entry_price, 50, 'trend')
                strategy_used.append('ma')
                if result == 'win':
                    short_wins += 1
                elif result == 'loss':
                    short_losses += 1
                else:
                    short_none += 1
        elif is_ranging(slice_df) and not trend_up and not trend_down:
            buy_signal, sell_signal = check_range_trade(slice_df)
            if buy_signal:
                result = check_trade_outcome(df_5m, i, 'buy', entry_price, 50, 'range')
                strategy_used.append('range')
                if result == 'win':
                    long_wins += 1
                elif result == 'loss':
                    long_losses += 1
                else:
                    long_none += 1
            elif sell_signal:
                result = check_trade_outcome(df_5m, i, 'sell', entry_price, 50, 'range')
                strategy_used.append('range')
                if result == 'win':
                    short_wins += 1
                elif result == 'loss':
                    short_losses += 1
                else:
                    short_none += 1



    total_trades = long_wins + long_losses + long_none + short_wins + short_losses + short_none
    total_wins = long_wins + short_wins
    win_rate = round(total_wins / total_trades * 100, 2) if total_trades > 0 else 0
    range_used = strategy_used.count('range')
    ma_used = strategy_used.count('ma')

    log_event(f"\n--- Results for {pair} ---")
    log_event(f"Total Trades: {total_trades}")
    log_event(f"Wins: {total_wins} (Long: {long_wins}, Short: {short_wins})")
    log_event(f"Losses: {long_losses + short_losses} (Long: {long_losses}, Short: {short_losses})")
    log_event(f"Unresolved: {long_none + short_none} (Long: {long_none}, Short: {short_none})")
    log_event(f"Win Rate: {win_rate}%")
    log_event(f"MA Usage: {ma_used}, Range Usage: {range_used}")

    return {
                'win_rate': win_rate,
                'total_trades': total_trades,
                'ma_used': ma_used,
                'range_used': range_used
            }

def run_backtest():
    good_pairs = []

    for pair in PAIRS:
        try:
            symbol = pair[0]
            df = fetch_data(symbol, '5m', days=90)
            df_1h = fetch_higher_timeframe_data(symbol, '15m', days=90)
            #print(f"CHECKING BACKTESTDF:{pair,len(df)}" )
            if len(df) > 300:
                result = simulate_combined_strategy(pair, df, df_1h)
                print(f"CHECKING:{result}" )
                log_event(f"CHECKING BACKTEST: {result}")
                if result['win_rate'] >= 55:
                    good_pairs.append(pair[0])
        except Exception as e:
                print(f"❌ Error backtesting {pair}: {e}")

    return good_pairs

if __name__ == "__main__":
    results = run_backtest()
    print("Backtest completed, good pairs:", results)