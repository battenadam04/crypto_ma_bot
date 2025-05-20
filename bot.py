import ccxt
import pandas as pd
import requests
import time
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor

from config import CRYPTO_PAIRS, TELEGRAM_TOKEN, TELEGRAM_CHAT_ID
from utils import (
    calculate_mas, check_long_signal, check_short_signal, save_chart,
    calculate_trade_levels, get_top_volume_pairs, init_kucoin_futures,
    place_futures_order, should_trade
)

kucoin_futures = init_kucoin_futures()
EXCHANGE = ccxt.kucoin()
TIMEFRAME = '1m'
PAIRS = get_top_volume_pairs(EXCHANGE, quote='USDT', top_n=20)
higher_timeframe_cache = {}


def fetch_data(symbol, timeframe=TIMEFRAME, limit=100):
    try:
        ohlcv = EXCHANGE.fetch_ohlcv(symbol, timeframe, limit=limit)
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        return df
    except Exception as e:
        log_event(f"❌ Error fetching data for {symbol}: {str(e)}")
        return None


def send_telegram(text, image_path=None):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        log_event(f"Posting to Telegram")
        requests.post(url, data={'chat_id': TELEGRAM_CHAT_ID, 'text': text})

        if image_path:
            url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPhoto"
            with open(image_path, 'rb') as img:
                requests.post(url, files={'photo': img}, data={'chat_id': TELEGRAM_CHAT_ID})
            log_event(f"Posted to Telegram")
    except Exception as e:
        log_event(f"⚠️ Telegram error: {e}")


def log_event(text):
    log_text = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {text}"
    print(log_text)
    with open('logs/trades.log', 'a') as f:
        f.write(log_text + '\n')


def handle_trade(symbol, direction, df, trend_confirmed):
    if not trend_confirmed or not should_trade(df):
        return

    entry_price = df.iloc[-1]['close']
    levels = calculate_trade_levels(entry_price, direction)
    path = save_chart(df, symbol)
    side = 'buy' if direction == 'long' else 'sell'

    trade_result = place_futures_order(
        exchange=kucoin_futures,
        symbol=symbol,
        side=side,
        usdt_amount=5,
        tp_price=levels['take_profit'],
        sl_price=levels['stop_loss'],
        leverage=10
    )

    status = trade_result.get('status', 'unknown')
    message = (
        f"{'📈 LONG' if direction == 'long' else '📉 SHORT'} SIGNAL for {symbol} ({TIMEFRAME})\n"
        f"Confirmed by 15m {'up' if direction == 'long' else 'down'}trend\n\n"
        f"💰 Entry: {levels['entry']}\n"
        f"🎯 TP: {levels['take_profit']}\n"
        f"🛑 SL: {levels['stop_loss']}\n"
        f"⚙️ Trade Status: {status}"
    )
    send_telegram(message, image_path=path)
    log_event(f"Trade: {message}")


def process_pair(symbol):
    log_event(f"🔍 Checking {symbol} on {TIMEFRAME} timeframe...")
    lower_df = fetch_data(symbol, TIMEFRAME)
    if lower_df is None or len(lower_df) < 51:
        log_event(f"⚠️ Skipping {symbol} — insufficient lower timeframe data.")
        return
    lower_df = calculate_mas(lower_df)

    now = time.time()
    if symbol not in higher_timeframe_cache or now - higher_timeframe_cache[symbol]['timestamp'] > 900:
        higher_df = fetch_data(symbol, '15m')
        if higher_df is None or len(higher_df) < 51:
            log_event(f"⚠️ Skipping {symbol} — insufficient higher timeframe data.")
            return
        higher_df = calculate_mas(higher_df)
        higher_timeframe_cache[symbol] = {'timestamp': now, 'data': higher_df}
    else:
        higher_df = higher_timeframe_cache[symbol]['data']

    trend_up = higher_df.iloc[-1]['ma20'] > higher_df.iloc[-1]['ma50']
    trend_down = higher_df.iloc[-1]['ma20'] < higher_df.iloc[-1]['ma50']

    if check_long_signal(lower_df):
        handle_trade(symbol, 'long', lower_df, trend_up)
    elif check_short_signal(lower_df):
        handle_trade(symbol, 'short', lower_df, trend_down)
    else:
        log_event(f"✅ No confirmed signal for {symbol} this cycle.")


def main():
    with ThreadPoolExecutor(max_workers=5) as executor:
        executor.map(process_pair, PAIRS)


if __name__ == '__main__':
    while True:
        main()
        log_event("🕒 Waiting 1 minute until next cycle...\n")
        time.sleep(60)
