import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../')))

import ccxt
from utils import get_top_volume_pairs

import pandas as pd
import numpy as np
import pandas_ta as ta
from strategies.range.backtestRangeStrategy import backtest_range_trading
from strategies.ma.backtestMaStrategy import backtest_ma_Strategy

EXCHANGE = ccxt.kucoin()
PAIRS = get_top_volume_pairs(EXCHANGE, quote='USDT', top_n=10)

overall_wins=0
overall_losses=0
overall_win_rate=0
overall_trades=0

EXCHANGE = ccxt.kucoin()


# 📌 Fetch OHLCV data
def fetch_data(df):
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

def is_ranging_market(df):
    last = df.iloc[-1]
    return last['adx'] < 25  # Low ADX = Sideways Market

for pair in PAIRS:

    ohlcv = EXCHANGE.fetch_ohlcv(pair, timeframe='5m', limit=5000)
        
    columns = ['timestamp', 'open', 'high', 'low', 'close', 'volume']
    df = fetch_data(pd.DataFrame(ohlcv, columns=columns))

    if is_ranging_market(df):
        print(f"Market Ranging:")
        backtest_range_trading(df, pair)
    else:
        print(f"Market trending:")
        results =  backtest_ma_Strategy(df, pair)


        overall_wins +=  results['long_wins'] + results['short_wins']
        overall_losses +=  results['long_losses'] + results['short_losses']
        overall_win_rate = round((overall_wins / (overall_wins + overall_losses)) * 100, 2) if (overall_wins + overall_losses) > 0 else 0

print(f"Overall Wins: {overall_wins}")
print(f"Overall Losses: {overall_losses}")
print(f"Overall win rate: {overall_win_rate}")