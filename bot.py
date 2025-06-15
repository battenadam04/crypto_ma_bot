import ccxt
import pandas as pd
import pandas_ta as ta
import requests
import time
import os
import json
from datetime import datetime,timedelta, timezone
from concurrent.futures import ThreadPoolExecutor
import threading


from config import TELEGRAM_TOKEN, TELEGRAM_CHAT_ID
from strategies.simulate_trades import run_backtest
from utils.utils import (
    add_atr_column, calculate_mas, check_long_signal, check_short_signal,
    calculate_trade_levels,is_ranging, check_range_trade, log_event
)

from utils.kuCoinUtils import (
    get_top_futures_tradable_pairs, init_kucoin_futures,
    place_futures_order,can_place_order
)


BACKTEST_STATE_FILE = "last_backtest.json"

# Global flag
can_trade_event = threading.Event()
can_trade_event.set()  # Initially allow trading

kucoin_futures = init_kucoin_futures()
EXCHANGE = ccxt.kucoin()
TIMEFRAME = '1m'
MAX_OPEN_TRADES = 3
MAX_LOSSES = 3
PAIRS = get_top_futures_tradable_pairs(kucoin_futures, quote='USDT', top_n=8)
higher_timeframe_cache = {}

filtered_pairs = []
last_backtest_time = datetime.min  # very old time to force backtest on first run



def fetch_data(symbol, timeframe=TIMEFRAME, limit=350):
    try:

        hours_back = 6 if timeframe == '1m' else 48
        since_dt = datetime.now(timezone.utc) - timedelta(hours=hours_back)
        since_ms = int(since_dt.timestamp() * 1000)  # ✅ convert to ms
        ohlcv = kucoin_futures.fetch_ohlcv(symbol, timeframe=timeframe, since=since_ms, limit=limit)
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        print(f"⏱️ Fetching data for {symbol} since {since_dt.isoformat()} ({since_ms})")
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




def handle_trade(symbol, direction, df, trend_confirmed, strategy_type="trend"):
    try:
        entry_price = df.iloc[-1]['close']
        df = add_atr_column(df)
        levels = calculate_trade_levels(entry_price, direction, df, len(df)-1, strategy_type)
        side = 'buy' if direction == 'long' else 'sell'
        print(f"💰 starting kucoin trade.")
        trade_result = place_futures_order(
                exchange=kucoin_futures,
                symbol=symbol,
                side=side,
                usdt_amount=1,
                tp_price=levels['take_profit'],
                sl_price=levels['stop_loss'],
                leverage=10
            )
        print(f"🔍 KuCoin trade results:\n{trade_result}")
        status = trade_result.get('status', 'unknown')
        error = trade_result.get('message', 'unknown')
        message = (
                f"{'📈 LONG' if direction == 'long' else '📉 SHORT'} SIGNAL for {symbol} ({TIMEFRAME})\n"
                f"Confirmed by 15m {'up' if direction == 'long' else 'down'}trend\n\n"
                f" Entry: {levels['entry']}\n"
                f"🎯 TP: {levels['take_profit']}\n"
                f"🛑 SL: {levels['stop_loss']}\n"
                f"⚙️ Trade Status: {status, error}"
            )
        send_telegram(message)
        #send_telegram(message, image_path=path)
        log_event(f"Trade: {message}")
    except Exception as e:
        log_event(f"❌ Error in handle_trade for {symbol}: {e}")

def process_pair(symbol):
    # Wait for global trade permission
    can_trade_event.wait()
    if can_place_order(symbol, can_trade_event):
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

        ma20_slope = higher_df['ma20'].iloc[-1] - higher_df['ma20'].iloc[-4]

        trend_up = (
            higher_df['ma20'].iloc[-1] > higher_df['ma50'].iloc[-1] and
            higher_df['ma20'].iloc[-1] > higher_df['ma20'].iloc[-5] and
            ma20_slope > 0  # upward slope confirmation
        )

        trend_down = (
            higher_df['ma20'].iloc[-1] < higher_df['ma50'].iloc[-1] and
            higher_df['ma20'].iloc[-1] < higher_df['ma20'].iloc[-5] and
            ma20_slope < 0  # downward slope confirmation
        )

        lower_df['rsi'] = lower_df.ta.rsi(length=14)
        lower_df['adx'] = lower_df.ta.adx(length=14)['ADX_14']
        lower_df['support'] = lower_df['low'].rolling(window=50).min()
        lower_df['resistance'] = lower_df['high'].rolling(window=50).max()

            #and trend_down - add back to each IF
            #and not is_near_resistance(higher_df)
            #check_long_signal(lower_df) and trend_up
        if check_long_signal(lower_df) and trend_up:
            handle_trade(symbol, 'long', lower_df, trend_up,strategy_type="trend")
        elif check_short_signal(lower_df) and trend_down:
            handle_trade(symbol, 'short', lower_df, trend_down, strategy_type="trend")
        elif  is_ranging(lower_df):
            buy_signal, sell_signal = check_range_trade(lower_df)
            if buy_signal:
                handle_trade(symbol, 'long', lower_df, True, strategy_type="range")
            elif sell_signal:
                handle_trade(symbol, 'short', lower_df, True, strategy_type="range")

     
        else:
            log_event(f"✅ No confirmed signal for {symbol} this cycle.")
    else:
        print(f"Max open order already exists. Skipping new order.")


def main():
    global filtered_pairs, last_backtest_time
    now = datetime.now(timezone.utc)

    # Run backtest once every 24 hours or if filtered_pairs empty (first run)
    if not filtered_pairs or (now - last_backtest_time) > timedelta(days=1):
        log_event("⏳ Running daily backtest...")
        #filtered_pairs = run_backtest()
        last_backtest_time = now
        #save_last_backtest_time(now)
        #log_event(f"✅ Backtest complete. {len(filtered_pairs)} pairs selected.")
        # test_pairs = [
        #     'NEAR/USDT:USDT',
        #     'PEPE/USDT:USDT',
        #     'TRX/USDT:USDT'
        # ]

        # from running backtest manually and updating here as server blocking api coingecko
        generated_pairs = ['XRP/USDT:USDT', 'ARB/USDT:USDT', 'WLD/USDT:USDT']

    for pair in generated_pairs:
        process_pair(pair)


if __name__ == '__main__':
    while True:
        main()
        log_event("🕒 Waiting 1 minute until next cycle...\n")
        time.sleep(60)