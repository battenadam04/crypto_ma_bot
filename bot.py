import ccxt
import pandas as pd
import requests
import time
import os
from datetime import datetime,timedelta
from concurrent.futures import ThreadPoolExecutor

from config import TELEGRAM_TOKEN, TELEGRAM_CHAT_ID
from utils.utils import (
    calculate_mas, check_long_signal, check_short_signal,
    calculate_trade_levels,is_consolidating, check_range_short, check_range_long
)

from utils.kuCoinUtils import (
    get_top_futures_tradable_pairs, init_kucoin_futures,
    place_futures_order,can_place_order
)


kucoin_futures = init_kucoin_futures()
EXCHANGE = ccxt.kucoin()
TIMEFRAME = '1m'
MAX_OPEN_TRADES = 3
MAX_LOSSES = 3
PAIRS = get_top_futures_tradable_pairs(kucoin_futures, quote='USDT', top_n=8)
higher_timeframe_cache = {}


def fetch_data(symbol, timeframe=TIMEFRAME, limit=350):
    try:

        hours_back = 6 if timeframe == '1m' else 48
        since_dt = datetime.now() - timedelta(hours=hours_back)
        since_ms = int(since_dt.timestamp() * 1000)  # ✅ convert to ms
        ohlcv = kucoin_futures.fetch_ohlcv(symbol, timeframe=timeframe, since=since_ms, limit=limit)
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
    os.makedirs('logs', exist_ok=True)  # Ensure 'logs/' directory exists
    log_text = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {text}"
    print(log_text)
    with open('logs/trades.log', 'a') as f:
        f.write(log_text + '\n')


def handle_trade(symbol, direction, df, trend_confirmed):
    # if not trend_confirmed or not should_trade(df):
    #     return

    entry_price = df.iloc[-1]['close']
    levels = calculate_trade_levels(entry_price, direction)
     ## path = save_chart(df, symbol)
    side = 'buy' if direction == 'long' else 'sell'

    print(f"💰 starting kucoin trade.")
    trade_result = place_futures_order(
            exchange=kucoin_futures,
            symbol=symbol,
            side=side,
            usdt_amount=3,
            tp_price=levels['take_profit'],
            sl_price=levels['stop_loss'],
            leverage=10
        )
    print(f"🔍 KuCoin trade results:\n{trade_result}")
    status = trade_result.get('status', 'unknown')
    message = (
            f"{'📈 LONG' if direction == 'long' else '📉 SHORT'} SIGNAL for {symbol} ({TIMEFRAME})\n"
            f"Confirmed by 15m {'up' if direction == 'long' else 'down'}trend\n\n"
            f" Entry: {levels['entry']}\n"
            f"🎯 TP: {levels['take_profit']}\n"
            f"🛑 SL: {levels['stop_loss']}\n"
            f"⚙️ Trade Status: {status}"
        )
    send_telegram(message)
     #send_telegram(message, image_path=path)
    log_event(f"Trade: {message}")


def process_pair(symbol):
    if can_place_order(symbol):
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

            #and trend_down - add back to each IF
        if check_long_signal(lower_df) and trend_up:
            handle_trade(symbol, 'long', lower_df, trend_up)
        elif check_short_signal(lower_df) and trend_down :
            handle_trade(symbol, 'short', lower_df, trend_down)
        elif not trend_up and not trend_down:
            if is_consolidating(lower_df):
                if check_range_long(lower_df):
                    handle_trade(symbol, 'long', lower_df, True)
                elif check_range_short(lower_df):
                    handle_trade(symbol, 'short', lower_df, True)
        else:
            log_event(f"✅ No confirmed signal for {symbol} this cycle.")
    else:
        print(f"Max open order already exists. Skipping new order.")


def main():
    with ThreadPoolExecutor(max_workers=5) as executor:
        executor.map(process_pair, PAIRS)


if __name__ == '__main__':
    while True:
        main()
        log_event("🕒 Waiting 1 minute until next cycle...\n")
        time.sleep(60)
