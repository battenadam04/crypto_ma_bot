import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))

import ccxt
from utils import get_top_volume_pairs



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
        else:  # short
            if low <= tp:
                return 'win'
            if high >= sl:
                return 'loss'

    return 'none'  # Neither TP nor SL hit

# 📌 Calculate Stop Loss & Take Profit
def calculate_sl_tp(entry_price, support, resistance, risk_reward=2):
    sl = entry_price - (entry_price - support) * 0.5  # SL at mid-support
    tp = entry_price + (resistance - entry_price) * risk_reward  # TP based on R:R
    return sl, tp

# 📌 Backtest Range Trading Strategy
def backtest_range_trading(df, pair, timeframe='5m', days=30):
    
    long_wins, long_losses, short_wins, short_losses = 0, 0, 0, 0
    balance = 500  # Simulated balance

    for i in range(51, len(df) - 1):  # Start after 50 candles (support/resistance window)
        slice_df = df.iloc[:i+1]
        current = df.iloc[i]
        next_candle = df.iloc[i+1]
        entry = current['close']

        buy_signal, sell_signal = check_trade_outcome(slice_df)

        # Long trade
        if buy_signal:
            sl, tp = calculate_sl_tp(entry, current['support'], current['resistance'])

            hit_sl = next_candle['low'] <= sl
            hit_tp = next_candle['high'] >= tp

            if hit_sl and hit_tp:
                # Assume SL hit first (worst-case)
                long_losses += 1
                balance -= balance * 0.01
            elif hit_tp:
                long_wins += 1
                balance += balance * 0.02
            elif hit_sl:
                long_losses += 1
                balance -= balance * 0.01

        # Short trade
        elif sell_signal:
            sl, tp = calculate_sl_tp(entry, current['resistance'], current['support'])

            hit_sl = next_candle['high'] >= sl
            hit_tp = next_candle['low'] <= tp

            if hit_sl and hit_tp:
                # Assume SL hit first
                short_losses += 1
                balance -= balance * 0.01
            elif hit_tp:
                short_wins += 1
                balance += balance * 0.02
            elif hit_sl:
                short_losses += 1
                balance -= balance * 0.01


    # 📌 Print Backtest Results
    print(f"Results for {pair}:")
    print(f"🏆 Long Wins: {long_wins}, ❌ Long Losses: {long_losses}")
    print(f"🏆 Short Wins: {short_wins}, ❌ Short Losses: {short_losses}")
    print(f"📊 Final Balance: £{balance:.2f}")