import config
import json
import os
import pandas as pd
import time
from datetime import datetime, timedelta, timezone
from concurrent.futures import ThreadPoolExecutor
import threading
import schedule



from config import (
    TRADING_SIGNALS_ONLY, TRADE_CAPITAL, MIN_ADX_TREND,
    DEFAULT_LEVERAGE, MAIN_LOOP_INTERVAL_SEC,
    RSI_OVERSOLD, RSI_OVERBOUGHT, RANGE_ADX_THRESHOLD,
    LIMIT_ENTRY_OFFSET_PCT, LIMIT_IDEA_FALLBACK_PCT,
)
from utils.telegramUtils import poll_telegram, send_telegram
from utils.utils import (
    add_atr_column, calculate_mas, check_long_signal, check_short_signal,is_ranging, check_range_trade, log_event
)

from utils.exchangeUtils import (
    fetch_balance_and_notify, get_exchange,
    place_futures_order, can_place_order
)
from utils.signalTracker import record_signal, send_eod_report


BACKTEST_STATE_FILE = "last_backtest.json"  # relative to project root (bot dir)

_last_night_quiet_log_ts = 0.0

_DEFAULT_PAIRS_PHEMEX = [
    'BTC/USDT:USDT', 'ETH/USDT:USDT', 'XRP/USDT:USDT', 'SOL/USDT:USDT',
    'DOGE/USDT:USDT', 'ADA/USDT:USDT', 'LINK/USDT:USDT', 'AVAX/USDT:USDT',
    'LTC/USDT:USDT', 'UNI/USDT:USDT', 'DOT/USDT:USDT', 'ATOM/USDT:USDT',
]
_DEFAULT_PAIRS_BINANCE_MARGIN = [
    'BTC/USDT', 'ETH/USDT', 'XRP/USDT', 'SOL/USDT',
    'DOGE/USDT', 'ADA/USDT', 'LINK/USDT', 'AVAX/USDT',
    'LTC/USDT', 'UNI/USDT', 'DOT/USDT', 'ATOM/USDT',
]


def _default_live_pairs():
    """Symbol shape must match EXCHANGE (Phemex perps vs Binance margin spot)."""
    if os.getenv("EXCHANGE", "phemex").strip().lower() == "binance_margin":
        return _DEFAULT_PAIRS_BINANCE_MARGIN.copy()
    return _DEFAULT_PAIRS_PHEMEX.copy()


# Default pairs when CRYPTO_PAIRS env is empty and backtest has not run
DEFAULT_PAIRS = _default_live_pairs()

# Global flag
can_trade_event = threading.Event()
can_trade_event.set()  # Initially allow trading

exchange = get_exchange()

# Higher-timeframe cache: keep only last 60 rows per symbol (enough for MA50); cap total entries to avoid unbounded growth
HTF_CACHE_TTL_SEC = 900
HTF_CACHE_MAX_ROWS = 60   # enough for ma20, ma50, iloc[-5]
HTF_CACHE_MAX_SYMBOLS = 32
higher_timeframe_cache = {}
_balance_job_scheduled = False  # avoid duplicate schedule jobs


def _hours_back_for_timeframe(timeframe: str) -> int:
    """Heuristic to bound historical fetch size per timeframe."""
    tf = (timeframe or "").strip().lower()
    # 15m needs ~51+ bars for ma50 / trend checks; 6h only yields ~24 candles.
    if tf in {"1m", "3m", "5m"}:
        return 6
    if tf in {"15m", "30m", "1h"}:
        return 48
    return 168


def fetch_data(symbol, timeframe=None, limit=350):
    """Fetch OHLCV; limit size to avoid large allocations."""
    try:
        timeframe = timeframe or config.TIMEFRAME
        hours_back = _hours_back_for_timeframe(timeframe)
        since_dt = datetime.now(timezone.utc) - timedelta(hours=hours_back)
        since_ms = int(since_dt.timestamp() * 1000)
        ohlcv = exchange.fetch_ohlcv(symbol, timeframe=timeframe, since=since_ms, limit=min(limit, 500))
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        return df
    except Exception as e:
        log_event(f"❌ Error fetching data for {symbol}: {str(e)}")
        return None



def handle_trade(symbol, direction, df, strategy_type="trend", signal_source="SIG"):
    try:    
        df = add_atr_column(df)
        side = 'buy' if direction == 'long' else 'sell'
        log_event(
            f"{'📣 Signal' if config.TRADING_SIGNALS_ONLY else '💰 Starting live trade'}: "
            f"{strategy_type} {direction} for {symbol}"
        )
        trade_result = place_futures_order(
                exchange=exchange,
                df=df,
                symbol=symbol,
                side=side,
                capital=TRADE_CAPITAL,
                leverage=DEFAULT_LEVERAGE,
                strategy_type=strategy_type
            )
        log_event(f"🔍 Trade results:\n{trade_result}")
        if trade_result is None or not isinstance(trade_result, dict):
            log_event(f"❌ place_futures_order returned invalid result for {symbol}: {trade_result!r}")
            return
        status = trade_result.get('status', 'unknown')
        error = trade_result.get('message', 'none')
        filledEntry = trade_result.get('filled_entry', 'none')
        tp_order = trade_result.get('tp_order')
        sl_order = trade_result.get('sl_order')

        tp = tp_order.get('id') if isinstance(tp_order, dict) else tp_order if tp_order is not None else 'N/A'
        sl = sl_order.get('id') if isinstance(sl_order, dict) else sl_order if sl_order is not None else 'N/A'

        # Build an optional limit-entry idea near local support/resistance.
        limit_hint = build_limit_order_hint(df, direction, strategy_type)

        if config.TRADING_SIGNALS_ONLY:
            message = (
                f"{'📈 LONG' if direction == 'long' else '📉 SHORT'} SIGNAL for {symbol} ({config.TIMEFRAME})\n"
                f"Confirmed by 15m {'up' if direction == 'long' else 'down'} {strategy_type}\n\n"
                f"🧭 Src: {signal_source}\n"
                f"ℹ️ Signals only — the bot does not place orders.\n"
                f"💲 Reference price: {filledEntry}\n"
                f"🎯 TP (indicative): {tp}\n"
                f"🛑 SL (indicative): {sl}\n"
            )
            if status != "success":
                message += f"⚙️ Status: {status}\n⚙️ Detail: {error}\n"
            message += limit_hint
        else:
            message = (
                f"{'📈 LONG' if direction == 'long' else '📉 SHORT'} SIGNAL for {symbol} ({config.TIMEFRAME})\n"
                f"Confirmed by 15m {'up' if direction == 'long' else 'down'} {strategy_type}\n\n"
                f"🧭 Src: {signal_source}\n"
                f"💲 Filled Entry: {filledEntry}\n"
                f"🎯 TP: {tp}\n"
                f"🛑 SL: {sl}\n"
                f"⚙️ Trade Status: {status}\n"
                f"⚙️ Trade Error: {error}\n"
                f"{limit_hint}"
            )
        send_telegram(message)
        log_event(f"{'Signal' if config.TRADING_SIGNALS_ONLY else 'Trade'}: {message}")

        if status == 'success':
            record_signal(symbol, direction, strategy_type, filledEntry, tp, sl)
    except Exception as e:
        log_event(f"❌ Error in handle_trade for {symbol}: {e}")


def _fmt_price(value):
    if value is None:
        return "N/A"
    if value < 0.01:
        return f"{value:.8f}"
    if value < 1:
        return f"{value:.6f}"
    if value < 100:
        return f"{value:.4f}"
    return f"{value:.2f}"


def build_limit_order_hint(df, direction, strategy_type):
    """
    Return a short text block suggesting a limit entry near support/resistance.
    - Range setups: emphasize bounce/rejection entry.
    - Trend setups: suggest a small pullback entry to improve fill quality.
    """
    if df is None or len(df) == 0:
        return "📝 Limit idea: not available (no candle data)"

    last = df.iloc[-1]
    close = float(last['close'])
    support = float(last['support']) if pd.notna(last.get('support')) else close
    resistance = float(last['resistance']) if pd.notna(last.get('resistance')) else close

    if direction == 'long':
        base_level = support if strategy_type == "range" else min(close, support * 1.003)
        limit_price = base_level * (1 + LIMIT_ENTRY_OFFSET_PCT)
        dist_pct = ((close - limit_price) / close) * 100
        return (
            f"📝 Limit idea: place a BUY LIMIT near support\n"
            f"  • Support: {_fmt_price(support)}\n"
            f"  • Suggested limit: {_fmt_price(limit_price)} (~{dist_pct:.2f}% below current)"
        )

    base_level = resistance if strategy_type == "range" else max(close, resistance * 0.997)
    limit_price = base_level * (1 - LIMIT_ENTRY_OFFSET_PCT)
    dist_pct = ((limit_price - close) / close) * 100
    return (
        f"📝 Limit idea: place a SELL LIMIT near resistance\n"
        f"  • Resistance: {_fmt_price(resistance)}\n"
        f"  • Suggested limit: {_fmt_price(limit_price)} (~{dist_pct:.2f}% above current)"
    )


def _limit_idea_fallback_signal(lower_df, trend_up, trend_down):
    """
    Fallback: if no normal signal, allow a range-biased limit idea near key levels.
    """
    if lower_df is None or len(lower_df) < 51:
        return None
    if trend_up or trend_down:
        return None
    if not is_ranging(lower_df):
        return None

    last = lower_df.iloc[-1]
    close = float(last['close'])
    support = float(last['support']) if pd.notna(last.get('support')) else close
    resistance = float(last['resistance']) if pd.notna(last.get('resistance')) else close

    near_support = close <= support * (1 + LIMIT_IDEA_FALLBACK_PCT)
    near_resistance = close >= resistance * (1 - LIMIT_IDEA_FALLBACK_PCT)

    if near_support:
        return {'direction': 'long', 'strategy_type': 'range'}
    if near_resistance:
        return {'direction': 'short', 'strategy_type': 'range'}
    return None

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

    log_event(f"🔍 Checking {symbol} on {config.TIMEFRAME} timeframe...")
    lower_df = fetch_data(symbol, config.TIMEFRAME)
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
        return {'symbol': symbol, 'direction': 'long', 'strategy_type': 'trend', 'signal_source': 'SIG', 'df': lower_df}
    if adx_ok and check_short_signal(lower_df) and trend_down:
        return {'symbol': symbol, 'direction': 'short', 'strategy_type': 'trend', 'signal_source': 'SIG', 'df': lower_df}
    if is_ranging(lower_df) and not trend_up and not trend_down:
        buy_signal, sell_signal = check_range_trade(lower_df)
        if buy_signal:
            return {'symbol': symbol, 'direction': 'long', 'strategy_type': 'range', 'signal_source': 'SIG', 'df': lower_df}
        if sell_signal:
            return {'symbol': symbol, 'direction': 'short', 'strategy_type': 'range', 'signal_source': 'SIG', 'df': lower_df}

    fallback = _limit_idea_fallback_signal(lower_df, trend_up, trend_down)
    if fallback:
        log_event(f"🧠 Limit-idea fallback triggered for {symbol} ({fallback['direction']})")
        return {'symbol': symbol, 'direction': fallback['direction'], 'strategy_type': fallback['strategy_type'], 'signal_source': 'LIM', 'df': lower_df}

    log_event(f"✅ No confirmed signal for {symbol} this cycle.")
    return None


def get_trading_pairs():
    """
    Live scanning universe (no auto-backtest in the bot — run `strategies/simulate_trades.py` manually).

    Order: last_backtest.json `pairs` (filtered by `win_rate_threshold` vs `results` when win_rate exists),
    then CRYPTO_PAIRS env, then DEFAULT_PAIRS.
    """
    state_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), BACKTEST_STATE_FILE)
    try:
        if os.path.isfile(state_path):
            with open(state_path, 'r') as f:
                data = json.load(f)
            raw = data.get('pairs') or []
            threshold = float(data.get('win_rate_threshold', 40))
            results = data.get('results') or {}
            qualified = []
            for p in raw:
                if not isinstance(p, str) or not p.strip():
                    continue
                sym = p.strip()
                r = results.get(sym)
                if isinstance(r, dict) and r.get('win_rate') is not None:
                    if float(r['win_rate']) < threshold:
                        continue
                qualified.append(sym)
            if qualified:
                return qualified
    except Exception:
        pass

    from config import CRYPTO_PAIRS
    if CRYPTO_PAIRS and any(p.strip() for p in CRYPTO_PAIRS):
        return [p.strip() for p in CRYPTO_PAIRS if p.strip()]
    return DEFAULT_PAIRS.copy()


def main():
    generated_pairs = get_trading_pairs()
    if not generated_pairs:
        log_event(
            "⚠️ No pairs to scan — run `python strategies/simulate_trades.py` to refresh last_backtest.json, "
            "or set CRYPTO_PAIRS in .env."
        )
        return

    log_event(
        f"📋 Scanning {len(generated_pairs)} pair(s) "
        f"(from last_backtest.json when present, else CRYPTO_PAIRS / defaults)."
    )

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
        handle_trade(
            sig['symbol'],
            sig['direction'],
            sig['df'],
            strategy_type=sig['strategy_type'],
            signal_source=sig.get('signal_source', 'SIG'),
        )

    # Prune HTF cache to current set only so we don't keep data for removed pairs
    if len(higher_timeframe_cache) > len(generated_pairs) + 5:
        allowed = set(generated_pairs)
        for sym in list(higher_timeframe_cache):
            if sym not in allowed:
                del higher_timeframe_cache[sym]

if __name__ == '__main__':
    log_event(
        f"🤖 Bot starting. Instance={config.BOT_INSTANCE_ID} Host={config.BOT_HOSTNAME} "
        f"PID={config.BOT_PID} Started={config.BOT_STARTED_AT_UTC}"
    )
    # Start Telegram polling in a background thread (single worker to limit memory)
    executor = ThreadPoolExecutor(max_workers=1)
    executor.submit(poll_telegram)

    if not _balance_job_scheduled:
        schedule.every().day.at("21:00").do(fetch_balance_and_notify)
        schedule.every().day.at("22:00").do(send_eod_report)
        _balance_job_scheduled = True

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

        # Overnight pause: skip pair scanning (fewer API calls). Telegram polling stays active.
        if config.should_skip_cycle_for_night_quiet():
            now_ts = time.time()
            if now_ts - _last_night_quiet_log_ts >= 600:
                _last_night_quiet_log_ts = now_ts
                log_event(
                    f"Night quiet hours ({config.NIGHT_QUIET_START_HOUR}:00–{config.NIGHT_QUIET_END_HOUR}:00 "
                    f"{config.NIGHT_QUIET_TZ}) — skipping scan. Use /night off in Telegram for 24/7."
                )
            time.sleep(config.NIGHT_QUIET_SLEEP_SEC)
            continue

        # ✅ Trading enabled
        main()
        log_event(f"🕒 Waiting {MAIN_LOOP_INTERVAL_SEC}s until next cycle...\n")
        for _ in range(MAIN_LOOP_INTERVAL_SEC // 10):
            try:
                schedule.run_pending()
            except Exception:
                pass
            time.sleep(10)