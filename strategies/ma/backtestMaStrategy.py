import sys
import os
import ccxt
import pandas as pd
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

def check_trade_outcome(df, start_idx, direction, entry_price, tp_pct, sl_pct, max_lookahead=10):
    tp = entry_price * (1 + tp_pct / 100) if direction == 'long' else entry_price * (1 - tp_pct / 100)
    sl = entry_price * (1 - sl_pct / 100) if direction == 'long' else entry_price * (1 + sl_pct / 100)

    for j in range(1, max_lookahead + 1):
        if start_idx + j >= len(df):
            break
        candle = df.iloc[start_idx + j]
        high, low = candle['high'], candle['low']

        if direction == 'long':
            if high >= tp:
                return 'win'
            if low <= sl:
                return 'loss'
        else:
            if low <= tp:
                return 'win'
            if high >= sl:
                return 'loss'
    return 'none'  # No outcome hit in the lookahead window

def backtest_ma_strategy(df, pair, tp_pct=1.4, sl_pct=1.0):
    long_wins = long_losses = short_wins = short_losses = 0

    for i in range(51, len(df) - 10):  # ensure enough candles left for lookahead
        slice_df = df.iloc[:i+1]
        current = df.iloc[i]
        entry = current['close']

        if check_long_signal(slice_df):
            result = check_trade_outcome(df, i, 'long', entry, tp_pct, sl_pct)
            print(f"\nCHECKING LONG VALUE {result}:")
            if result == 'win':
                long_wins += 1
            elif result == 'loss':
                long_losses += 1

        elif check_short_signal(slice_df):
            result = check_trade_outcome(df, i, 'short', entry, tp_pct, sl_pct)
            if result == 'win':
                short_wins += 1
            elif result == 'loss':
                short_losses += 1

    long_total = long_wins + long_losses
    short_total = short_wins + short_losses
    all_trades = long_total + short_total

    print(f"\nBacktest Results for {pair}:")
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
