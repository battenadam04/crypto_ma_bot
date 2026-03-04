import ccxt
import config
import json
import os
import pandas as pd
import pandas_ta as ta
import time
from datetime import datetime,timedelta, timezone
from concurrent.futures import ThreadPoolExecutor
import threading
import schedule



from config import TRADING_SIGNALS_ONLY, TRADE_CAPITAL, MIN_ADX_TREND
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


BACKTEST_STATE_FILE = "last_backtest.json"  # relative to project root (bot dir)

# Default pairs when CRYPTO_PAIRS env is empty and backtest has not run (avoids UnboundLocalError in else branch)
DEFAULT_PAIRS = [
    'BTC/USDT', 'ETH/USDT', 'XRP/USDT', 'BNB/USDT', 'SOL/USDT', 'TRX/USDT',
    'DOGE/USDT', 'ADA/USDT', 'LINK/USDT', 'XLM/USDT', 'HBAR/USDT', 'LTC/USDT',
    'AVAX/USDT', 'SHIB/USDT', 'SUI/USDT', 'UNI/USDT'
]

# Global flag
can_trade_event = threading.Event()
can_trade_event.set()  # Initially allow trading

exchange = init_exchange()
TIMEFRAME = '5m'
MAX_OPEN_TRADES = 3
MAX_LOSSES = 3

# Higher-timeframe cache: keep only last 60 rows per symbol (enough for MA50); cap total entries to avoid unbounded growth
HTF_CACHE_TTL_SEC = 900
HTF_CACHE_MAX_ROWS = 60   # enough for ma20, ma50, iloc[-5]
HTF_CACHE_MAX_SYMBOLS = 32
higher_timeframe_cache = {}
_balance_job_scheduled = False  # avoid adding duplicate schedule jobs every 24h

filtered_pairs = []
last_backtest_time = datetime.min  # very old time to force backtest on first run



def fetch_data(symbol, timeframe=TIMEFRAME, limit=350):
    """Fetch OHLCV; limit size to avoid large allocations."""
    try:
        hours_back = 6 if timeframe == '5m' else 48
        since_dt = datetime.now(timezone.utc) - timedelta(hours=hours_back)
        since_ms = int(since_dt.timestamp() * 1000)
        ohlcv = exchange.fetch_ohlcv(symbol, timeframe=timeframe, since=since_ms, limit=min(limit, 500))
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
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
                capital=TRADE_CAPITAL,
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

def get_backtest_win_rates():
    """Load per-pair win rates from last backtest so we can prioritize which signal to take first."""
    state_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), BACKTEST_STATE_FILE)
    if not os.path.isfile(state_path):
        return {}
    try:
        with open(state_path, 'r') as f:
            data = json.load(f)
        results = data.get('results', {})
        return {sym: float(r.get('win_rate', 0)) for sym, r in results.items() if isinstance(r, dict)}
    except Exception:
        return {}


def process_pair(symbol):
    """
    Check one pair for a signal. Returns a signal dict (symbol, direction, strategy_type, lower_df) or None.
    Does not place trades; caller collects signals and takes them in backtest-priority order.
    """
    if not TRADING_SIGNALS_ONLY:
        allowed, reason = can_place_order(symbol)
        if not allowed:
            log_event(f"⛔ Skipping {symbol}: {reason}")
            return None

    log_event(f"🔍 Checking {symbol} on {TIMEFRAME} timeframe...")
    lower_df = fetch_data(symbol, TIMEFRAME)
    if lower_df is None or len(lower_df) < 51:
        log_event(f"⚠️ Skipping {symbol} — insufficient lower timeframe data.")
        return None
    lower_df = calculate_mas(lower_df)

    now = time.time()
    if symbol not in higher_timeframe_cache or now - higher_timeframe_cache[symbol]['timestamp'] > HTF_CACHE_TTL_SEC:
        higher_df = fetch_data(symbol, '15m', limit=100)
        if higher_df is None or len(higher_df) < 51:
            log_event(f"⚠️ Skipping {symbol} — insufficient higher timeframe data.")
            return None
        higher_df = calculate_mas(higher_df)
        higher_df = higher_df.tail(HTF_CACHE_MAX_ROWS).copy()
        if len(higher_timeframe_cache) >= HTF_CACHE_MAX_SYMBOLS:
            oldest = min(higher_timeframe_cache, key=lambda s: higher_timeframe_cache[s]['timestamp'])
            del higher_timeframe_cache[oldest]
        higher_timeframe_cache[symbol] = {'timestamp': now, 'data': higher_df}
    else:
        higher_df = higher_timeframe_cache[symbol]['data']

    ma20_slope = higher_df['ma20'].iloc[-1] - higher_df['ma20'].iloc[-4]
    trend_up = (
        higher_df['ma20'].iloc[-1] > higher_df['ma50'].iloc[-1] and
        higher_df['ma20'].iloc[-1] > higher_df['ma20'].iloc[-5] and
        ma20_slope > 0
    )
    trend_down = (
        higher_df['ma20'].iloc[-1] < higher_df['ma50'].iloc[-1] and
        higher_df['ma20'].iloc[-1] < higher_df['ma20'].iloc[-5] and
        ma20_slope < 0
    )

    lower_df['rsi'] = lower_df.ta.rsi(length=14)
    lower_df['adx'] = lower_df.ta.adx(length=14)['ADX_14']
    lower_df['support'] = lower_df['low'].rolling(window=50).min()
    lower_df['resistance'] = lower_df['high'].rolling(window=50).max()

    adx_ok = (MIN_ADX_TREND <= 0 or
              (pd.notna(lower_df['adx'].iloc[-1]) and lower_df['adx'].iloc[-1] >= MIN_ADX_TREND))

    if adx_ok and check_long_signal(lower_df) and trend_up:
        return {'symbol': symbol, 'direction': 'long', 'strategy_type': 'trend', 'df': lower_df}
    if adx_ok and check_short_signal(lower_df) and trend_down:
        return {'symbol': symbol, 'direction': 'short', 'strategy_type': 'trend', 'df': lower_df}
    if is_ranging(lower_df) and not trend_up and not trend_down:
        buy_signal, sell_signal = check_range_trade(lower_df)
        if buy_signal:
            return {'symbol': symbol, 'direction': 'long', 'strategy_type': 'range', 'df': lower_df}
        if sell_signal:
            return {'symbol': symbol, 'direction': 'short', 'strategy_type': 'range', 'df': lower_df}

    log_event(f"✅ No confirmed signal for {symbol} this cycle.")
    return None


def get_trading_pairs():
    """Single source of truth: CRYPTO_PAIRS from config, or backtest file, or default list."""
    from config import CRYPTO_PAIRS
    if CRYPTO_PAIRS and any(p.strip() for p in CRYPTO_PAIRS):
        return [p.strip() for p in CRYPTO_PAIRS if p.strip()]
    try:
        state_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), BACKTEST_STATE_FILE)
        if os.path.isfile(state_path):
            with open(state_path, 'r') as f:
                data = json.load(f)
            pairs = data.get('pairs', [])
            if pairs:
                return pairs
    except Exception:
        pass
    return DEFAULT_PAIRS.copy()


def main():
    global filtered_pairs, last_backtest_time
    now = datetime.now(timezone.utc)

    # Pairs to use this cycle: always defined so the loop never raises UnboundLocalError
    generated_pairs = get_trading_pairs()

    # Run backtest once every 24 hours or if filtered_pairs empty (first run)
    if not filtered_pairs or ((now - last_backtest_time) > timedelta(days=1) and check_daily_loss_limit()):
        log_event("⏳ Running daily backtest...")
        filtered_pairs = run_backtest()
        last_backtest_time = now
        global _balance_job_scheduled
        if not _balance_job_scheduled:
            schedule.every().day.at("21:00").do(fetch_balance_and_notify)
            _balance_job_scheduled = True
        log_event(f"✅ Backtest complete. {len(filtered_pairs)} pairs selected.")
        if filtered_pairs:
            generated_pairs = filtered_pairs
    else:
        log_event("🕒 Skipping pair processing due to loss of balance or within 24h window.\n")

    # Collect all signals this cycle, then take trades in backtest-priority order
    # so live behavior matches backtest: we prefer the pair with the highest backtest win rate
    signals = []
    for pair in generated_pairs:
        sig = process_pair(pair)
        if sig is not None:
            signals.append(sig)

    win_rates = get_backtest_win_rates()
    # Sort by backtest win rate descending (take best pairs first); if no backtest data, keep list order
    signals.sort(key=lambda s: win_rates.get(s['symbol'], 0.0), reverse=True)
    if signals and win_rates:
        log_event(f"Signals this cycle: {[s['symbol'] for s in signals]} (ordered by backtest win rate)")

    for sig in signals:
        allowed, reason = can_place_order(sig['symbol']) if not TRADING_SIGNALS_ONLY else (True, "signals only")
        if not allowed:
            log_event(f"⛔ Skipping trade {sig['symbol']}: {reason}")
            continue
        handle_trade(sig['symbol'], sig['direction'], sig['df'], strategy_type=sig['strategy_type'])

    # Prune HTF cache to current set only so we don't keep data for removed pairs
    if len(higher_timeframe_cache) > len(generated_pairs) + 5:
        allowed = set(generated_pairs)
        for sym in list(higher_timeframe_cache):
            if sym not in allowed:
                del higher_timeframe_cache[sym]

if __name__ == '__main__':
    # Start Telegram polling in a background thread (single worker to limit memory)
    executor = ThreadPoolExecutor(max_workers=1)
    executor.submit(poll_telegram)

    while True:
        # Run any scheduled jobs (e.g. daily balance at 21:00)
        try:
            schedule.run_pending()
        except Exception as e:
            log_event(f"Schedule run_pending: {e}")

        # 🔒 MASTER GATE (Telegram ON/OFF)
        if not config.TRADING_ENABLED:
            log_event("🚫 Trading disabled. Sleeping 60 seconds...")
            time.sleep(60)
            continue

        # ✅ Trading enabled
        main()
        log_event("🕒 Waiting 5 minutes until next cycle...\n")
        time.sleep(300)