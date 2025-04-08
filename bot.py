import ccxt
import pandas as pd
import requests
import time
from datetime import datetime
from config import CRYPTO_PAIRS
from config import TELEGRAM_TOKEN, TELEGRAM_CHAT_ID
from utils import calculate_mas, check_long_signal, check_short_signal, save_chart
from utils import calculate_trade_levels
from utils import get_top_volume_pairs
from utils import init_kucoin_futures, place_futures_order
from utils import should_trade
from utils import is_early_breakout


kucoin_futures = init_kucoin_futures()

EXCHANGE = ccxt.kucoin()
TIMEFRAME = '1m'
PAIRS = get_top_volume_pairs(EXCHANGE, quote='USDT', top_n=10)


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
        response = requests.post(url, data={'chat_id': TELEGRAM_CHAT_ID, 'text': text})
        print("Telegram text response:", response.status_code, response.text)

        if image_path:
            url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPhoto"
            with open(image_path, 'rb') as img:
                response = requests.post(url, files={'photo': img}, data={'chat_id': TELEGRAM_CHAT_ID})
                print("Telegram text response:", response.status_code, response.text)
                log_event(f"Posted to Telegram")
    except Exception as e:
        log_event(f"⚠️ Telegram error: {e}")

def log_event(text):
    log_text = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {text}"
    print(log_text)
    with open('logs/trades.log', 'a') as f:
        f.write(log_text + '\n')

def process_pair(symbol):
    log_event(f"🔍 Checking {symbol} on {TIMEFRAME} timeframe...")

    # Fetch lower (5m) and higher (1h) data
    lower_df = fetch_data(symbol, TIMEFRAME)
    higher_df = fetch_data(symbol, '15m')

    if lower_df is None or higher_df is None or len(lower_df) < 51 or len(higher_df) < 51:
        log_event(f"⚠️ Skipping {symbol} — insufficient data.")
        return

    # Calculate MAs on both
    lower_df = calculate_mas(lower_df)
    higher_df = calculate_mas(higher_df)

    # Check trend alignment on higher timeframe
    trend_up = higher_df.iloc[-1]['ma20'] > higher_df.iloc[-1]['ma50']
    trend_down = higher_df.iloc[-1]['ma20'] < higher_df.iloc[-1]['ma50']

    # Only consider signals if higher timeframe agrees
    if check_long_signal(lower_df) and trend_up and should_trade(lower_df):
        entry_price = lower_df.iloc[-1]['close']
        levels = calculate_trade_levels(entry_price, direction='long')
        path = save_chart(lower_df, symbol)

        trade_result = place_futures_order(
            exchange=kucoin_futures,
            symbol=symbol,
            side='buy',  # or 'sell' for short
            usdt_amount=5,
            tp_price=levels['take_profit'],
            sl_price=levels['stop_loss'],
            leverage=10
        )


        # Add trade info to the alert message
        message = (
            f'📈 LONG SIGNAL for {symbol} ({TIMEFRAME})\n'
            f'Confirmed by 1h uptrend\n\n'
            f'💰 Entry (limit): {levels["entry"]}\n'
            f'🎯 Take Profit: {levels["take_profit"]}\n'
            f'🛑 Stop Loss: {levels["stop_loss"]}\n\n'
            f'⚙️ Futures Trade Status: {trade_result["status"]}'
        )
        send_telegram(message, image_path=path)
        log_event("🚀 LONG signal triggered: " + message)

    elif check_short_signal(lower_df) and trend_down and should_trade(lower_df):
        entry_price = lower_df.iloc[-1]['close']
        levels = calculate_trade_levels(entry_price, direction='short')
        path = save_chart(lower_df, symbol)

        trade_result = place_futures_order(
            exchange=kucoin_futures,
            symbol=symbol,
            side='sell',  # or 'sell' for short
            usdt_amount=5,
            tp_price=levels['take_profit'],
            sl_price=levels['stop_loss'],
            leverage=10
        )

        message = (
            f'📉 SHORT SIGNAL for {symbol} ({TIMEFRAME})\n'
            f'Confirmed by 1h downtrend\n\n'
            f'💰 Entry (limit): {levels["entry"]}\n'
            f'🎯 Take Profit: {levels["take_profit"]}\n'
            f'🛑 Stop Loss: {levels["stop_loss"]}\n\n'
         #    f'⚙️ Futures Trade Status: {trade_result["status"]}'
        )
        send_telegram(message, image_path=path)
        log_event("🔻 SHORT signal triggered: " + message)

    else:
        log_event(f"✅ No confirmed signal for {symbol} this cycle.")

def main():
    for pair in PAIRS:
        log_event(f"checking  {pair}.")
        process_pair(pair)

if __name__ == '__main__':
    while True:
        main()
        log_event("🕒 Waiting 1 minutes until next cycle...\n")
        time.sleep(1 * 60)
