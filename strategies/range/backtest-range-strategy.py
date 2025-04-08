import ccxt
import pandas as pd
import numpy as np
import pandas_ta as ta 
from utils import get_top_volume_pairs


EXCHANGE = ccxt.kucoin()
PAIRS = get_top_volume_pairs(EXCHANGE, quote='USDT', top_n=10)

# 📌 Fetch OHLCV data
def fetch_data(symbol, tf='15m', days=7):
    exchange = ccxt.kucoin()  # or ccxt.kucoinfutures()
    
    limit = 96 * days  # 96 candles per day for 15m timeframe
    ohlcv = exchange.fetch_ohlcv(symbol, timeframe=tf, limit=limit)
    
    columns = ['timestamp', 'open', 'high', 'low', 'close', 'volume']
    df = pd.DataFrame(ohlcv, columns=columns)
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')

    # ✅ Compute Moving Averages
    df['ma10'] = df['close'].rolling(10).mean()
    df['ma20'] = df['close'].rolling(20).mean()
    df['ma50'] = df['close'].rolling(50).mean()
    
    # ✅ Compute RSI & ADX using pandas_ta
    df['rsi'] = df.ta.rsi(length=14)
    df['adx'] = df.ta.adx(length=14)['ADX_14']  # pandas_ta returns a DataFrame

    # ✅ Detect Support & Resistance
    df['support'] = df['low'].rolling(window=50).min()
    df['resistance'] = df['high'].rolling(window=50).max()

    return df

# 📌 Check if Market is Ranging
def is_ranging_market(df):
    last = df.iloc[-1]
    return last['adx'] < 25  # Low ADX = Sideways Market

# 📌 Check Range Trade Signals (Long/Short)
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

# 📌 Calculate Stop Loss & Take Profit
def calculate_sl_tp(entry_price, support, resistance, risk_reward=2):
    sl = entry_price - (entry_price - support) * 0.5  # SL at mid-support
    tp = entry_price + (resistance - entry_price) * risk_reward  # TP based on R:R
    return sl, tp

# 📌 Backtest Range Trading Strategy
def backtest_range_trading(symbol, timeframe='15m', days=7):
    df = fetch_data(symbol, timeframe, days)
    
    long_wins, long_losses, short_wins, short_losses = 0, 0, 0, 0
    balance = 1000  # Simulated balance

    for i in range(51, len(df) - 1):  # Start after 50 candles (support/resistance window)
        slice_df = df.iloc[:i+1]
        current = df.iloc[i]
        next_candle = df.iloc[i+1]
        entry = current['close']

        if not is_ranging_market(slice_df):
            continue  # Skip if market is trending

        buy_signal, sell_signal = check_range_trade(slice_df)

        if buy_signal:
            sl, tp = calculate_sl_tp(entry, current['support'], current['resistance'])
            if next_candle['low'] <= sl:
                long_losses += 1
                balance -= balance * 0.01  # Simulated loss
            elif next_candle['high'] >= tp:
                long_wins += 1
                balance += balance * 0.02  # Simulated win

        elif sell_signal:
            sl, tp = calculate_sl_tp(entry, current['resistance'], current['support'])
            if next_candle['high'] >= sl:
                short_losses += 1
                balance -= balance * 0.01
            elif next_candle['low'] <= tp:
                short_wins += 1
                balance += balance * 0.02

    # 📌 Print Backtest Results
    print(f"Results for {symbol}:")
    print(f"🏆 Long Wins: {long_wins}, ❌ Long Losses: {long_losses}")
    print(f"🏆 Short Wins: {short_wins}, ❌ Short Losses: {short_losses}")
    print(f"📊 Final Balance: £{balance:.2f}")

# 📌 Run Backtest on Multiple Pairs
for pair in PAIRS:
    backtest_range_trading(pair)
