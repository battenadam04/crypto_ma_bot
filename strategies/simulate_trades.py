
import sys
import os
from datetime import datetime, timedelta
import ccxt
import pandas as pd
import numpy as np
import pandas_ta as ta

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../')))

from strategies.combined.backtestCombinedStrategy import backtest_combined_strategy
from utils import init_kucoin_futures, get_top_futures_tradable_pairs, check_long_signal, check_short_signal
from strategies.range.range_utils import check_range_trade, calculate_sl_tp



kucoin_futures = init_kucoin_futures()
c = ccxt.kucoin()
PAIRS = get_top_futures_tradable_pairs(kucoin_futures, quote='USDT', top_n=8)


def check_trade_outcome(df, start_idx, direction, entry_price, tp_pct, sl_pct, max_lookahead=100):
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
        else:  # short
            if low <= tp:
                return 'win'
            if high >= sl:
                return 'loss'

    return 'none'  # Neither TP nor SL hit

def fetch_data(pair, timeframe='1m', days=7):
    since = kucoin_futures.parse8601((datetime.now() - timedelta(days=days)).strftime('%Y-%m-%dT%H:%M:%SZ'))
    ohlcv = kucoin_futures.fetch_ohlcv(pair, timeframe=timeframe, since=since)
    df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')

    df['ma10'] = df['close'].rolling(10).mean()
    df['ma20'] = df['close'].rolling(20).mean()
    df['ma50'] = df['close'].rolling(50).mean()
    df['rsi'] = df.ta.rsi(length=14)
    df['adx'] = df.ta.adx(length=14)['ADX_14']
    df['support'] = df['low'].rolling(window=50).min()
    df['resistance'] = df['high'].rolling(window=50).max()

    return df

def is_ranging(df):
    return df.iloc[-1]['adx'] < 25

def check_range_trade(df):
    last = df.iloc[-1]

    buy_signal = (
        last['close'] <= last['support'] * 1.01  # Near support (1% buffer)
        and last['rsi'] < 30  # Oversold
    )

    sell_signal = (
        last['close'] >= last['resistance'] * 0.99  # Near resistance (1% buffer)
        and last['rsi'] > 70  # Overbought
    )
    
    return buy_signal, sell_signal

def simulate_combined_strategy(pair, df):
    long_wins = long_losses = short_wins = short_losses = 0
    strategy_used = []

    for i in range(51, len(df) - 10):
        slice_df = df.iloc[:i+1]
        current = df.iloc[i]
        entry = current['close']

        if is_ranging(slice_df):
            buy_signal, sell_signal = check_range_trade(slice_df)
            if buy_signal:
                sl, tp = calculate_sl_tp(entry, current['support'], current['resistance'])
                result = check_trade_outcome(df, i, 'long', entry, tp_pct=(tp-entry)/entry*100, sl_pct=(entry-sl)/entry*100)
                if result == 'win':
                    long_wins += 1
                elif result == 'loss':
                    long_losses += 1
                strategy_used.append('range')
            elif sell_signal:
                sl, tp = calculate_sl_tp(entry, current['resistance'], current['support'])
                result = check_trade_outcome(df, i, 'short', entry, tp_pct=(entry-tp)/entry*100, sl_pct=(sl-entry)/entry*100)
                if result == 'win':
                    short_wins += 1
                elif result == 'loss':
                    short_losses += 1
                strategy_used.append('range')
        else:
            if check_long_signal(slice_df):
                result = check_trade_outcome(df, i, 'long', entry, tp_pct=1.4, sl_pct=1.0)
                if result == 'win':
                    long_wins += 1
                elif result == 'loss':
                    long_losses += 1
                strategy_used.append('ma')
            elif check_short_signal(slice_df):
                result = check_trade_outcome(df, i, 'short', entry, tp_pct=1.4, sl_pct=1.0)
                if result == 'win':
                    short_wins += 1
                elif result == 'loss':
                    short_losses += 1
                strategy_used.append('ma')

    total_trades = long_wins + long_losses + short_wins + short_losses
    win_rate = round((long_wins + short_wins) / total_trades * 100, 2) if total_trades > 0 else 0
    range_used = strategy_used.count('range')
    ma_used = strategy_used.count('ma')

    print(f"\n--- Results for {pair} ---")
    print(f"Trades: {total_trades}, Win Rate: {win_rate}%")
    print(f"MA Wins: {long_wins + short_wins}, MA Losses: {long_losses + short_losses}")
    print(f"MA Usage: {ma_used}, Range Usage: {range_used}")

def run_backtest():
    for pair in PAIRS:
        try:
            df = fetch_data(pair, timeframe='1m', days=7)
            if len(df) > 100:
                simulate_combined_strategy(pair, df)
        except Exception as e:
            print(f"Error with {pair}: {e}")

if __name__ == '__main__':
    run_backtest()
