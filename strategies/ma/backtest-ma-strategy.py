import ccxt
import pandas as pd
from utils import calculate_mas, check_long_signal, check_short_signal
from utils import get_top_volume_pairs

EXCHANGE = ccxt.kucoin()
PAIRS = get_top_volume_pairs(EXCHANGE, quote='USDT', top_n=10)

def fetch_data(symbol, tf='5m', limit=3000):
    exchange = ccxt.kucoin()
    ohlcv = exchange.fetch_ohlcv(symbol, timeframe=tf, limit=limit)
    df = pd.DataFrame(ohlcv, columns=['timestamp','open','high','low','close','volume'])
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
    
    return calculate_mas(df)

def simulate_trades(df, tp_pct=1.4, sl_pct=1.0):
    long_wins = 0
    long_losses = 0
    short_wins = 0
    short_losses = 0

    for i in range(51, len(df) - 1):
        slice_df = df.iloc[:i+1]
        current = df.iloc[i]
        next_candle = df.iloc[i+1]
        entry = current['close']
        high = next_candle['high']
        low = next_candle['low']

        # LONG Logic
        if check_long_signal(slice_df):
            tp = entry * (1 + tp_pct / 100)
            sl = entry * (1 - sl_pct / 100)

            if high >= tp:
                long_wins += 1
            elif low <= sl:
                long_losses += 1

        # SHORT Logic
        elif check_short_signal(slice_df):
            tp = entry * (1 - tp_pct / 100)
            sl = entry * (1 + sl_pct / 100)

            if low <= tp:
                short_wins += 1
            elif high >= sl:
                short_losses += 1

    long_total = long_wins + long_losses
    short_total = short_wins + short_losses
    all_trades = long_total + short_total


    print(f'check: {long_wins} : {long_losses}')  # Check the last 20 candles

    return {
        'total_trades': all_trades,
        'long_trades': long_total,
        'short_trades': short_total,
        'long_wins': long_wins,
        'long_losses': long_losses,
        'short_wins': short_wins,
        'short_losses': short_losses,
        'long_win_rate': round((long_wins / long_total) * 100, 2) if long_total > 0 else 0,
        'short_win_rate': round((short_wins / short_total) * 100, 2) if short_total > 0 else 0,
        'overall_win_rate': round(((long_wins + short_wins) / all_trades) * 100, 2) if all_trades > 0 else 0
    }

for pair in PAIRS:
    data = fetch_data(pair)
    results = simulate_trades(data)

    print(f"Backtest Results for {pair}:")
    print(f"Total Trades: {results['total_trades']}")
    print(f"Wins: {results['long_wins'] + results['short_wins']}")
    print(f"Losses: {results['long_losses'] + results['short_losses']}")
    print(f"Win Rate: {results['long_win_rate'] + results['short_win_rate']}%")