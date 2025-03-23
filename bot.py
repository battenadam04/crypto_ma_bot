import ccxt
import pandas as pd
import requests
import time
from config import TELEGRAM_TOKEN, TELEGRAM_CHAT_ID
from utils import calculate_mas, check_long_signal, check_short_signal, save_chart

EXCHANGE = ccxt.binance()
SYMBOL = 'BTC/USDT'
TIMEFRAME = '1h'

def fetch_data(symbol, timeframe='1h', limit=100):
    ohlcv = EXCHANGE.fetch_ohlcv(symbol, timeframe, limit=limit)
    df = pd.DataFrame(ohlcv, columns=['timestamp','open','high','low','close','volume'])
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
    return df

def send_telegram(text, image_path=None):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    requests.post(url, data={'chat_id': TELEGRAM_CHAT_ID, 'text': text})
    
    if image_path:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPhoto"
        with open(image_path, 'rb') as img:
            requests.post(url, files={'photo': img}, data={'chat_id': TELEGRAM_CHAT_ID})

def log_trade(text):
    with open('logs/trades.log', 'a') as f:
        f.write(f"{pd.Timestamp.now()} | {text}\n")

def main():
    df = fetch_data(SYMBOL, TIMEFRAME)
    df = calculate_mas(df)

    if check_long_signal(df):
        path = save_chart(df, SYMBOL)
        message = f'📈 LONG signal on {SYMBOL} ({TIMEFRAME})\nMA10 crossed above MA20\nMA20 > MA50'
        send_telegram(message, image_path=path)
        log_trade("LONG: " + message)

    elif check_short_signal(df):
        path = save_chart(df, SYMBOL)
        message = f'📉 SHORT signal on {SYMBOL} ({TIMEFRAME})\nMA10 crossed below MA20\nMA20 < MA50'
        send_telegram(message, image_path=path)
        log_trade("SHORT: " + message)

if __name__ == '__main__':
    while True:
        main()
        time.sleep(60 * 60)  # 1 hour loop
