import sys
import os
import ccxt

from utils import is_consolidating, check_range_long, check_range_short, get_top_futures_tradable_pairs, init_kucoin_futures

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))

from utils import check_long_signal, check_short_signal
from utils import get_top_volume_pairs, calculate_mas



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
    return 'none'  # No TP/SL hit within the lookahead window

def get_trend_flags(df):
    latest = df.iloc[-1]
    trend_up = latest['ma20'] > latest['ma50']
    trend_down = latest['ma20'] < latest['ma50']
    return trend_up, trend_down

def backtest_combined_strategy(df, pair, tp_pct=1.4, sl_pct=1.0):
    long_wins = long_losses = short_wins = short_losses = 0

    for i in range(51, len(df) - 10):
        slice_df = df.iloc[:i+1]
        current = df.iloc[i]
        entry = current['close']

        trend_up, trend_down = get_trend_flags(slice_df)

        if check_long_signal(slice_df) and trend_up:
            result = check_trade_outcome(df, i, 'long', entry, tp_pct, sl_pct)
        elif check_short_signal(slice_df) and trend_down:
            result = check_trade_outcome(df, i, 'short', entry, tp_pct, sl_pct)
        elif not trend_up and not trend_down:
            if is_consolidating(slice_df):
                if check_range_long(slice_df):
                    result = check_trade_outcome(df, i, 'long', entry, tp_pct, sl_pct)
                elif check_range_short(slice_df):
                    result = check_trade_outcome(df, i, 'short', entry, tp_pct, sl_pct)
                else:
                    result = 'none'
            else:
                result = 'none'
        else:
            result = 'none'

        if result == 'win':
            if 'long' in locals() and check_long_signal(slice_df):
                long_wins += 1
            else:
                short_wins += 1
        elif result == 'loss':
            if 'long' in locals() and check_long_signal(slice_df):
                long_losses += 1
            else:
                short_losses += 1

    # Summary output (same as before)
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
