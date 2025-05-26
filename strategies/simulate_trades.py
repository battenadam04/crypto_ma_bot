import sys
import os
from datetime import datetime, timedelta
import ccxt
import pandas as pd
import pandas_ta as ta
import time

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../')))

from utils.utils import (
    check_long_signal, check_short_signal, calculate_trade_levels,
    is_near_resistance,is_ranging, calculate_mas, is_consolidating,
    check_range_trade
)
from utils.kuCoinUtils import init_kucoin_futures, get_top_futures_tradable_pairs

kucoin_futures = init_kucoin_futures()
PAIRS = get_top_futures_tradable_pairs(kucoin_futures, quote='USDT', top_n=8)

import time

def fetch_data(pair, timeframe='1m', days=7):
    all_ohlcv = []
    now = datetime.utcnow()
    since = int((now - timedelta(days=days)).timestamp() * 1000)

    limit = 200  # KuCoin hard limit
    max_tries = 30  # You can increase this if needed
    loops = 0

    while loops < max_tries:
        ohlcv = kucoin_futures.fetch_ohlcv(pair, timeframe=timeframe, since=since, limit=limit)

        if not ohlcv:
            break

        all_ohlcv.extend(ohlcv)
        #print(f"Loop {loops + 1}: fetched {len(ohlcv)} candles")

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

    #print(f"✅ Total candles fetched for {pair}: {len(df)}")
    return df





def check_trade_outcome(df, start_idx, direction, entry_price, max_lookahead=100):
    levels = calculate_trade_levels(entry_price, direction, df)
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
    return 'none'

def simulate_combined_strategy(pair, df):
    long_wins = long_losses = long_none = 0
    short_wins = short_losses = short_none = 0
    strategy_used = []

    for i in range(60, len(df) - 10):
        slice_df = df.iloc[:i+1]
        current = df.iloc[i]
        entry_price = float(current['close'])

        # Higher timeframe (~15m from 1m candles)
        higher_df = df.iloc[max(0, i - 60):i + 1]
        trend_up = higher_df['ma20'].iloc[-1] > higher_df['ma50'].iloc[-1]
        trend_down = higher_df['ma20'].iloc[-1] < higher_df['ma50'].iloc[-1]

        if is_ranging(slice_df):
            buy_signal, sell_signal = check_range_trade(slice_df)
            if buy_signal:
                print(f"{pair} [i={i}] → Range BUY @ {entry_price}")
                result = check_trade_outcome(df, i, 'long', entry_price)
                strategy_used.append('range')
                if result == 'win':
                    long_wins += 1
                elif result == 'loss':
                    long_losses += 1
                else:
                    long_none += 1
            elif sell_signal:
                print(f"{pair} [i={i}] → Range SELL @ {entry_price}")
                result = check_trade_outcome(df, i, 'short', entry_price)
                strategy_used.append('range')
                if result == 'win':
                    short_wins += 1
                elif result == 'loss':
                    short_losses += 1
                else:
                    short_none += 1

        else:
            if check_long_signal(slice_df) and trend_up and not is_near_resistance(higher_df):
                print(f"{pair} [i={i}] → MA LONG @ {entry_price}")
                result = check_trade_outcome(df, i, 'long', entry_price)
                strategy_used.append('ma')
                if result == 'win':
                    long_wins += 1
                elif result == 'loss':
                    long_losses += 1
                else:
                    long_none += 1
            elif check_short_signal(slice_df) and trend_down:
                print(f"{pair} [i={i}] → MA SHORT @ {entry_price}")
                result = check_trade_outcome(df, i, 'short', entry_price)
                strategy_used.append('ma')
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

    print(f"\n--- Results for {pair} ---")
    print(f"Total Trades: {total_trades}")
    print(f"Wins: {total_wins} (Long: {long_wins}, Short: {short_wins})")
    print(f"Losses: {long_losses + short_losses} (Long: {long_losses}, Short: {short_losses})")
    print(f"Unresolved: {long_none + short_none} (Long: {long_none}, Short: {short_none})")
    print(f"Win Rate: {win_rate}%")
    print(f"MA Usage: {ma_used}, Range Usage: {range_used}")

def run_backtest():
    for pair in PAIRS:
        try:
            df = fetch_data(pair, '1m', days=7)
            print(f"df: {len(df)}")
            if len(df) > 300:
                simulate_combined_strategy(pair, df)
        except Exception as e:
            print(f"❌ Error backtesting {pair}: {e}")

if __name__ == '__main__':
    run_backtest()
