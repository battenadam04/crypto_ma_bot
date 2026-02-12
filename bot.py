import ccxt
import config
import pandas as pd
import pandas_ta as ta
import time
from datetime import datetime,timedelta, timezone
from concurrent.futures import ThreadPoolExecutor
import threading
import schedule



from config import TRADING_SIGNALS_ONLY
from strategies.simulate_trades import run_backtest
from utils.dailyChecksUtils import check_daily_loss_limit
from utils.telegramUtils import poll_telegram, send_telegram
from utils.utils import (
    add_atr_column, calculate_mas, check_long_signal, check_short_signal,is_ranging, check_range_trade, log_event
)

from utils.exchangeUtils import (
    fetch_balance_and_notify, init_exchange,
    place_futures_order,can_place_order
)


BACKTEST_STATE_FILE = "last_backtest.json"

# Global flag
can_trade_event = threading.Event()
can_trade_event.set()  # Initially allow trading

exchange = init_exchange()
TIMEFRAME = '5m'
MAX_OPEN_TRADES = 3
MAX_LOSSES = 3
higher_timeframe_cache = {}

filtered_pairs = []
last_backtest_time = datetime.min  # very old time to force backtest on first run



def fetch_data(symbol, timeframe=TIMEFRAME, limit=350):
    try:

        hours_back = 6 if timeframe == '5m' else 48
        since_dt = datetime.now(timezone.utc) - timedelta(hours=hours_back)
        since_ms = int(since_dt.timestamp() * 1000)  # ✅ convert to ms
        ohlcv = exchange.fetch_ohlcv(symbol, timeframe=timeframe, since=since_ms, limit=limit)
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        print(f"⏱️ Fetching data for {symbol} since {since_dt.isoformat()} ({since_ms})")
        return df
    except Exception as e:
        log_event(f"❌ Error fetching data for {symbol}: {str(e)}")
        return None



def handle_trade(symbol, direction, df, strategy_type="trend"):
    try:    
        df = add_atr_column(df)
        side = 'buy' if direction == 'long' else 'sell'
        log_event(f"💰 Starting trade: {strategy_type} for {direction}")
        trade_result = place_futures_order(
                exchange=exchange,
                df=df,
                symbol=symbol,
                side=side,
                capital=50,
                leverage=10,
                strategy_type=strategy_type
            )
        log_event(f"🔍 Trade results:\n{trade_result}")
        status = trade_result.get('status', 'unknown')
        error = trade_result.get('message', 'none')
        filledEntry = trade_result.get('filled_entry', 'none')
        tp_order = trade_result.get('tp_order')
        sl_order = trade_result.get('sl_order')

        tp = tp_order.get('id') if isinstance(tp_order, dict) else tp_order if tp_order is not None else 'N/A'
        sl = sl_order.get('id') if isinstance(sl_order, dict) else sl_order if sl_order is not None else 'N/A'

        message = (
                f"{'📈 LONG' if direction == 'long' else '📉 SHORT'} SIGNAL for {symbol} ({TIMEFRAME})\n"
                f"Confirmed by 15m {'up' if direction == 'long' else 'down'}{strategy_type}\n\n"
                f" Filled Entry: {filledEntry}\n"
                f"🎯 TP: {tp}\n"
                f"🛑 SL: {sl}\n"
                f"⚙️ Trade Status: {status}"
                f"⚙️ Trade Error: {error}"
            )
        send_telegram(message)
        log_event(f"Trade: {message}")
    except Exception as e:
        log_event(f"❌ Error in handle_trade for {symbol}: {e}")

def process_pair(symbol):
    allowed, reason = can_place_order(symbol)
    if allowed or TRADING_SIGNALS_ONLY:
        if not allowed:
            log_event(f"⚠️ Trading anyway (signals only): {reason}")
        else:
            log_event(f"✅ {symbol} passed trade checks.")

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

        if check_long_signal(lower_df) and trend_up:
            handle_trade(symbol, 'long', lower_df,strategy_type="trend")
        elif check_short_signal(lower_df) and trend_down:
            handle_trade(symbol, 'short', lower_df, strategy_type="trend")
        elif  is_ranging(lower_df) and not trend_up and not trend_down:
            buy_signal, sell_signal = check_range_trade(lower_df)
            if buy_signal:
                handle_trade(symbol, 'long', lower_df, strategy_type="range")
            elif sell_signal:
                handle_trade(symbol, 'short', lower_df, strategy_type="range")

     
        else:
            log_event(f"✅ No confirmed signal for {symbol} this cycle.")
    else:
        log_event(f"⛔ Skipping {symbol}: {reason}")


def main():
    global filtered_pairs, last_backtest_time
    now = datetime.now(timezone.utc)


    # Run backtest once every 24 hours or if filtered_pairs empty (first run)
    if not filtered_pairs or (now - last_backtest_time) > timedelta(days=1) and check_daily_loss_limit():
        log_event("⏳ Running daily backtest...")
        #filtered_pairs = run_backtest()
        last_backtest_time = now
        #save_last_backtest_time(now)
        #log_event(f"✅ Backtest complete. {len(filtered_pairs)} pairs selected.")

        # from running backtest manually and updating here as server blocking api coingecko
        generated_pairs = ['BTC/USDT', 'ETH/USDT', 'BNB/USDT', 'XRP/USDT', 'TRX/USDT', 'DOGE/USDT', 'ADA/USDT', 'BCH/USDT', 'WBTC/USDT', 'LINK/USDT', 'XLM/USDT', 'ZEC/USDT', 'LTC/USDT', 'SUI/USDT', 'AVAX/USDT', 'HBAR/USDT', 'SHIB/USDT', 'TON/USDT', 'UNI/USDT']

        schedule.every().day.at("21:00").do(fetch_balance_and_notify)
    else:
        log_event("🕒 Skipping pair processing due to loss of balance  ...\n")
    for pair in generated_pairs:
        process_pair(pair)

if __name__ == '__main__':
    # Start Telegram polling in a background thread
    executor = ThreadPoolExecutor(max_workers=2)  # 1 for Telegram, 1 for other tasks
    executor.submit(poll_telegram)

    while True:
        # 🔒 MASTER GATE (Telegram ON/OFF)
        if not config.TRADING_ENABLED:
            log_event("🚫 Trading disabled. Sleeping 60 seconds...")
            time.sleep(60)  # reduce CPU/log load when idle (Telegram thread handles /on)
            continue

        # ✅ Trading enabled
        main()
        log_event("🕒 Waiting 5 minutes until next cycle...\n")
        time.sleep(300)