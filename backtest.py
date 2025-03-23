from utils import calculate_mas, check_long_signal, check_short_signal
import ccxt
import pandas as pd

def fetch_data(symbol, tf='1h', limit=200):
    ex = ccxt.binance()
    df = ex.fetch_ohlcv(symbol, tf, limit=limit)
    df = pd.DataFrame(df, columns=['timestamp','open','high','low','close','volume'])
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
    return df

def backtest(df):
    df = calculate_mas(df)
    signals = []
    for i in range(1, len(df)):
        subset = df.iloc[:i+1]
        if check_long_signal(subset):
            signals.append((df.iloc[i]['timestamp'], 'LONG', df.iloc[i]['close']))
        elif check_short_signal(subset):
            signals.append((df.iloc[i]['timestamp'], 'SHORT', df.iloc[i]['close']))
    return signals

if __name__ == '__main__':
    data = fetch_data('BTC/USDT', '1h', 300)
    signals = backtest(data)
    for sig in signals:
        print(sig)
