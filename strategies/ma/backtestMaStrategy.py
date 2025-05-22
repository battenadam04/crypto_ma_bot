import sys
import os
import ccxt
import pandas as pd
from ta.trend import SMAIndicator
from datetime import datetime, timedelta

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))

from utils import check_long_signal, check_short_signal
from utils import get_top_volume_pairs, calculate_mas

EXCHANGE = ccxt.kucoin()
PAIRS = get_top_volume_pairs(EXCHANGE, quote='USDT', top_n=10)

def fetch_ohlcv(symbol, timeframe='1m', limit=150):
    since = EXCHANGE.parse8601((datetime.utcnow() - timedelta(hours=52)).strftime('%Y-%m-%dT%H:%M:%SZ'))
    ohlcv = EXCHANGE.fetch_ohlcv(symbol, timeframe=timeframe, since=since, limit=limit)
    df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
    return calculate_mas(df)

def backtest_ma_strategy(df, pair, tp_pct=1.4, sl_pct=1.0):
    long_wins = long_losses = short_wins = short_losses = 0
    for i in range(51, len(df) - 1):
        slice_df = df.iloc[:i+1]
        current = df.iloc[i]
        next_candle = df.iloc[i+1]
        entry = current['close']
        high = next_candle['high']
        low = next_candle['low']

        # print("Testing one candle:")
        # test_df = df.iloc[:60]
        # print("LONG:", check_long_signal(test_df))
        # print("SHORT:", check_short_signal(test_df))

        if check_long_signal(slice_df):
            print(f"[{pair}] LONG signal at index {i} | Price: {entry}")
            tp = entry * (1 + tp_pct / 100)
            sl = entry * (1 - sl_pct / 100)
            if high >= tp:
                long_wins += 1
            elif low <= sl:
                long_losses += 1

        elif check_short_signal(slice_df):
            print(f"[{pair}] SHORT signal at index {i} | Price: {entry}")
            tp = entry * (1 - tp_pct / 100)
            sl = entry * (1 + sl_pct / 100)
            if low <= tp:
                short_wins += 1
            elif high >= sl:
                short_losses += 1

    long_total = long_wins + long_losses
    short_total = short_wins + short_losses
    all_trades = long_total + short_total

    print(f"Backtest Results for {pair}:")
    print(f"Total Trades: {all_trades}")
    print(f"Wins: {long_wins + short_wins}")
    print(f"Losses: {long_losses + short_losses}")
    print(f"Long Win Rate: {round((long_wins / long_total) * 100, 2) if long_total > 0 else 0}%")
    print(f"Short Win Rate: {round((short_wins / short_total) * 100, 2) if short_total > 0 else 0}%")
    print(f"Overall Win Rate: {round(((long_wins + short_wins) / all_trades) * 100, 2) if all_trades > 0 else 0}%\n")

def run_backtest():
    for pair in PAIRS:
        try:
            df = fetch_ohlcv(pair)
            if len(df) > 60:
                backtest_ma_strategy(df, pair)
        except Exception as e:
            print(f"Error fetching data for {pair}: {e}")

if __name__ == '__main__':
    run_backtest()
