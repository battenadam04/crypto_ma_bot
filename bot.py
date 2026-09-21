import config
import json
import os
import threading
import pandas as pd
import pandas_ta as ta  # noqa: F401 — registers `DataFrame.ta` for RSI/ADX in process_pair
import time
from datetime import datetime, timedelta, timezone
from concurrent.futures import ThreadPoolExecutor
import schedule

from config import (
    MAIN_LOOP_INTERVAL_SEC,
    LIMIT_ENTRY_OFFSET_PCT,
    SIGNAL_COOLDOWN_SEC,
    MAX_SIGNALS_PER_CYCLE,
    SR_LOOKBACK_BARS,
)
from utils.telegramUtils import poll_telegram, send_telegram
from utils.utils import (
    add_atr_column, calculate_mas, log_event,
)
from utils.signalLogic import evaluate_signal_at_bar
from utils.exchangeUtils import get_exchange, build_indicative_levels
from utils.signalTracker import record_signal, send_eod_report, monitor_signal_outcomes
from utils.signalFormat import format_limit_hint, format_signal_message


BACKTEST_STATE_FILE = "last_backtest.json"  # relative to project root (bot dir)

_last_night_quiet_log_ts = 0.0
_last_macro_pause_log_ts = 0.0
# (symbol, direction) -> unix timestamp of last alert — prevents spam on sticky setups
_recent_signals = {}

# Fallback watchlist excludes mega-caps (same rationale as BACKTEST_EXCLUDE_BASES).
_DEFAULT_PAIRS_PHEMEX = [
    'XRP/USDT:USDT', 'SOL/USDT:USDT', 'DOGE/USDT:USDT', 'ADA/USDT:USDT',
    'LINK/USDT:USDT', 'AVAX/USDT:USDT', 'LTC/USDT:USDT', 'UNI/USDT:USDT',
    'DOT/USDT:USDT', 'ATOM/USDT:USDT',
]
_DEFAULT_PAIRS_BINANCE_MARGIN = [
    'XRP/USDT', 'SOL/USDT', 'DOGE/USDT', 'ADA/USDT',
    'LINK/USDT', 'AVAX/USDT', 'LTC/USDT', 'UNI/USDT',
    'DOT/USDT', 'ATOM/USDT',
]


def _default_live_pairs():
    """Symbol shape must match EXCHANGE (Phemex perps vs Binance margin spot)."""
    if config.EXCHANGE.strip().lower() == "binance_margin":
        return _DEFAULT_PAIRS_BINANCE_MARGIN.copy()
    return _DEFAULT_PAIRS_PHEMEX.copy()


DEFAULT_PAIRS = _default_live_pairs()

exchange = get_exchange()

# Higher-timeframe cache: keep only last 60 rows per symbol (enough for MA50); cap total entries
HTF_CACHE_TTL_SEC = 900
HTF_CACHE_MAX_ROWS = 60
HTF_CACHE_MAX_SYMBOLS = 32
higher_timeframe_cache = {}
_eod_job_scheduled = False
_auto_backtest_scheduled = False
_auto_backtest_lock = threading.Lock()


def _fmt_symbols_short(symbols, limit=8):
    syms = [str(s) for s in (symbols or [])]
    if not syms:
        return "(none)"
    if len(syms) <= limit:
        return ", ".join(syms)
    return ", ".join(syms[:limit]) + f" (+{len(syms) - limit} more)"


def _run_auto_backtest():
    """Refresh last_backtest.json; run off the main scan loop (daemon thread)."""
    if not _auto_backtest_lock.acquire(blocking=False):
        log_event("⏭️ Scheduled backtest skipped — already running")
        return
    try:
        log_event("🧪 Scheduled weekly backtest starting…")
        if config.AUTO_BACKTEST_NOTIFY:
            try:
                send_telegram(
                    "🧪 Weekly backtest started — refreshing pair universe…",
                    bypass_rate_limit=True,
                )
            except Exception as e:
                log_event(f"Auto-backtest start notify failed: {e}")

        # Lazy import: simulate_trades pulls heavy deps; safe after IS_BACKTESTING fix.
        from strategies.simulate_trades import run_backtest, run_portfolio_backtest

        good = run_backtest()
        portfolio_wr = None
        if good:
            portfolio_wr = run_portfolio_backtest(pairs_override=good, max_trades_per_bar=3)

        log_event(
            f"✅ Scheduled backtest done: {len(good or [])} qualifying pair(s)"
            + (f", portfolio WR={portfolio_wr}%" if portfolio_wr is not None else "")
        )
        if config.AUTO_BACKTEST_NOTIFY:
            try:
                lines = [
                    "✅ <b>Weekly backtest complete</b>",
                    f"Qualifying pairs: <b>{len(good or [])}</b>",
                    f"Watchlist: <code>{_fmt_symbols_short(good)}</code>",
                ]
                if portfolio_wr is not None:
                    lines.append(f"Portfolio win rate: <b>{portfolio_wr}%</b>")
                lines.append("<i>Watchlist refreshed for upcoming setups.</i>")
                send_telegram("\n".join(lines), parse_mode="HTML", bypass_rate_limit=True)
            except Exception as e:
                log_event(f"Auto-backtest finish notify failed: {e}")
    except Exception as e:
        log_event(f"❌ Scheduled backtest failed: {e}")
        if config.AUTO_BACKTEST_NOTIFY:
            try:
                send_telegram(
                    f"❌ Weekly backtest failed: {e}",
                    bypass_rate_limit=True,
                )
            except Exception:
                pass
    finally:
        _auto_backtest_lock.release()


def _kick_auto_backtest():
    """Schedule callback: spawn a daemon thread so scans / Telegram keep running."""
    threading.Thread(target=_run_auto_backtest, name="auto-backtest", daemon=True).start()


def _schedule_auto_backtest_job():
    """Register weekly backtest with the schedule library (UTC by default)."""
    if not config.AUTO_BACKTEST_ENABLED:
        log_event("Auto-backtest disabled (AUTO_BACKTEST_ENABLED=False)")
        return
    day = (config.AUTO_BACKTEST_DAY or "sunday").strip().lower()
    at = (config.AUTO_BACKTEST_AT or "06:00").strip()
    tz = (config.AUTO_BACKTEST_TZ or "UTC").strip()
    day_job = getattr(schedule.every(), day, None)
    if day_job is None:
        log_event(f"Invalid AUTO_BACKTEST_DAY={day!r}; expected monday…sunday. Using sunday.")
        day_job = schedule.every().sunday
    day_job.at(at, tz).do(_kick_auto_backtest)
    log_event(f"🗓️ Auto-backtest scheduled: every {day} at {at} {tz}")


def _minutes_per_bar(timeframe: str) -> int:
    tf = (timeframe or "").strip().lower()
    return {
        "1m": 1,
        "3m": 3,
        "5m": 5,
        "15m": 15,
        "30m": 30,
        "1h": 60,
        "2h": 120,
        "4h": 240,
        "1d": 1440,
    }.get(tf, 15)


def _hours_back_for_timeframe(timeframe: str, min_bars: int = 90) -> int:
    """
    Bound OHLCV history so we always have enough bars for MA50 (+buffer).

    Previously 1h used a flat 48h window (~48 candles), which failed the HTF
    len>=51 gate and skipped every pair after HTF moved to 1h.
    """
    minutes = _minutes_per_bar(timeframe)
    hours_needed = int((min_bars * minutes + 59) // 60)
    return max(hours_needed, 6)


def fetch_data(symbol, timeframe=None, limit=350):
    """Fetch OHLCV; limit size to avoid large allocations."""
    try:
        timeframe = timeframe or config.TIMEFRAME
        # Signal TF needs SR lookback; HTF needs MA50 — size window from the stricter need.
        min_bars = max(90, int(SR_LOOKBACK_BARS) + 20)
        hours_back = _hours_back_for_timeframe(timeframe, min_bars=min_bars)
        since_dt = datetime.now(timezone.utc) - timedelta(hours=hours_back)
        since_ms = int(since_dt.timestamp() * 1000)
        ohlcv = exchange.fetch_ohlcv(symbol, timeframe=timeframe, since=since_ms, limit=min(limit, 500))
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        return df
    except Exception as e:
        log_event(f"❌ Error fetching data for {symbol}: {str(e)}")
        return None


def _signal_on_cooldown(symbol, direction) -> bool:
    last = _recent_signals.get((symbol, direction))
    if last is None:
        return False
    return (time.time() - last) < SIGNAL_COOLDOWN_SEC


def _mark_signal_sent(symbol, direction) -> None:
    _recent_signals[(symbol, direction)] = time.time()
    # Bound memory: drop oldest when large
    if len(_recent_signals) > 200:
        oldest_key = min(_recent_signals, key=_recent_signals.get)
        del _recent_signals[oldest_key]


def build_limit_order_hint(df, direction, strategy_type):
    """One-line limit entry suggestion for manual traders."""
    if df is None or len(df) == 0:
        return ""

    last = df.iloc[-1]
    close = float(last['close'])
    support = float(last['support']) if pd.notna(last.get('support')) else close
    resistance = float(last['resistance']) if pd.notna(last.get('resistance')) else close

    if direction == 'long':
        base_level = support if strategy_type == "range" else min(close, support * 1.003)
        limit_price = base_level * (1 + LIMIT_ENTRY_OFFSET_PCT)
        dist_pct = ((close - limit_price) / close) * 100
        return format_limit_hint(limit_price, dist_pct, direction)

    base_level = resistance if strategy_type == "range" else max(close, resistance * 0.997)
    limit_price = base_level * (1 - LIMIT_ENTRY_OFFSET_PCT)
    dist_pct = ((limit_price - close) / close) * 100
    return format_limit_hint(limit_price, dist_pct, direction)


def handle_signal(symbol, direction, df, strategy_type="trend", signal_source="SIG", timeframe=None):
    """Compose and send a signals-only Telegram alert with indicative TP/SL.
    If live trading is enabled, also execute the trade on Phemex."""
    try:
        timeframe = timeframe or config.TIMEFRAME
        df = add_atr_column(df)
        side = 'buy' if direction == 'long' else 'sell'
        log_event(f"📣 Signal: {strategy_type} {direction} for {symbol} (src={signal_source}, tf={timeframe})")

        levels = build_indicative_levels(
            exchange=exchange,
            df=df,
            symbol=symbol,
            side=side,
            strategy_type=strategy_type,
        )
        if levels is None or not isinstance(levels, dict):
            log_event(f"❌ build_indicative_levels returned invalid result for {symbol}: {levels!r}")
            return

        status = levels.get('status', 'unknown')
        error = levels.get('message', 'none')
        filled_entry = levels.get('filled_entry', 'none')
        tp_price = levels.get('tp_price')
        sl_price = levels.get('sl_price')
        tp = levels.get('tp_order') if tp_price is None else tp_price
        sl = levels.get('sl_order') if sl_price is None else sl_price

        limit_hint = build_limit_order_hint(df, direction, strategy_type)

        live_status = ""
        if config.LIVE_TRADING_ENABLED and status == 'success':
            try:
                from utils.liveTrading import execute_trade
                result = execute_trade(symbol, side, filled_entry, tp_price, sl_price, strategy_type)
                if result and result.get('success'):
                    if result.get('flattened_only'):
                        live_status = f"\n🔄 Flattened opposite position (did not reverse): {result.get('error', 'ok')}"
                    else:
                        live_status = f"\n🟢 LIVE ORDER PLACED: {result.get('order_id', 'ok')}"
                else:
                    live_status = f"\n🔴 Live order failed: {result.get('error', 'unknown')}"
            except Exception as e:
                live_status = f"\n🔴 Live execution error: {e}"

        # Pro channel is read-only for members — keep operator/live details out of the feed.
        message = format_signal_message(
            symbol=symbol,
            direction=direction,
            timeframe=timeframe,
            strategy_type=strategy_type,
            entry=filled_entry,
            tp=tp,
            sl=sl,
            signal_source=signal_source,
            limit_hint=limit_hint,
            status=status,
            error=error if status != "success" else "",
        )

        send_telegram(message, parse_mode="HTML")
        log_event(f"Signal: {message}")
        _mark_signal_sent(symbol, direction)

        if live_status:
            try:
                from utils.telegramUtils import send_telegram_admins
                send_telegram_admins(
                    f"⚡ Live trading update for <b>{symbol}</b> ({timeframe})\n"
                    f"{live_status.strip()}",
                    parse_mode="HTML",
                )
            except Exception as e:
                log_event(f"Admin live-status notify failed: {e}")

        if status == 'success':
            record_signal(
                symbol,
                direction,
                strategy_type,
                filled_entry,
                tp_price or tp,
                sl_price or sl,
                timeframe=timeframe,
            )
    except Exception as e:
        log_event(f"❌ Error in handle_signal for {symbol}: {e}")


def process_pair(symbol):
    """
    Check one pair for a signal. Returns a signal dict or None.
    Does not send Telegram alerts; caller ranks/filters before dispatch.
    Uses shared utils.signalLogic.evaluate_signal_at_bar (same as backtest).
    """
    log_event(f"🔍 Checking {symbol} on {config.TIMEFRAME} timeframe...")
    lower_df = fetch_data(symbol, config.TIMEFRAME)
    if lower_df is None or len(lower_df) < 51:
        log_event(f"⚠️ Skipping {symbol} — insufficient lower timeframe data.")
        return None
    lower_df = calculate_mas(lower_df)

    now = time.time()
    if symbol not in higher_timeframe_cache or now - higher_timeframe_cache[symbol]['timestamp'] > HTF_CACHE_TTL_SEC:
        # Need >=51 1h bars for MA50; request a comfortable buffer.
        higher_df = fetch_data(symbol, config.HTF_TIMEFRAME, limit=200)
        if higher_df is None or len(higher_df) < 51:
            got = 0 if higher_df is None else len(higher_df)
            log_event(
                f"⚠️ Skipping {symbol} — insufficient higher timeframe data "
                f"({config.HTF_TIMEFRAME}: {got} bars, need ≥51)."
            )
            return None
        higher_df = calculate_mas(higher_df)
        higher_df = higher_df.tail(HTF_CACHE_MAX_ROWS).copy()
        if len(higher_timeframe_cache) >= HTF_CACHE_MAX_SYMBOLS:
            oldest = min(higher_timeframe_cache, key=lambda s: higher_timeframe_cache[s]['timestamp'])
            del higher_timeframe_cache[oldest]
        higher_timeframe_cache[symbol] = {'timestamp': now, 'data': higher_df}
    else:
        higher_df = higher_timeframe_cache[symbol]['data']

    # Guard against stale cache rows with NaN MAs (should be rare after the fetch fix).
    if (
        pd.isna(higher_df['ma20'].iloc[-1])
        or pd.isna(higher_df['ma50'].iloc[-1])
        or len(higher_df) < 5
    ):
        log_event(f"⚠️ Skipping {symbol} — HTF MAs not ready yet.")
        higher_timeframe_cache.pop(symbol, None)
        return None

    lower_df['rsi'] = lower_df.ta.rsi(length=14)
    lower_df['adx'] = lower_df.ta.adx(length=14)['ADX_14']
    lower_df['support'] = lower_df['low'].rolling(window=SR_LOOKBACK_BARS).min()
    lower_df['resistance'] = lower_df['high'].rolling(window=SR_LOOKBACK_BARS).max()
    lower_df = add_atr_column(lower_df)

    # Align HTF slice to the same window backtest uses (last 6 HTF bars including current).
    htf_slice = higher_df.iloc[-6:] if len(higher_df) >= 6 else higher_df
    entry_price = float(lower_df['close'].iloc[-1])
    decision = evaluate_signal_at_bar(lower_df, htf_slice, entry_price)

    if decision is None:
        log_event(f"✅ No confirmed signal for {symbol} this cycle.")
        return None

    if decision.signal_source == "LIM":
        log_event(f"🧠 Limit-idea fallback triggered for {symbol} ({decision.direction})")

    return {
        'symbol': symbol,
        'direction': decision.direction,
        'strategy_type': decision.strategy_type,
        'signal_source': decision.signal_source,
        'df': lower_df,
    }


def get_backtest_win_rates():
    """Load per-pair win rates from last backtest for ranking."""
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


def get_trading_pairs():
    """
    Scan universe: last_backtest.json pairs (win-rate filtered), then CRYPTO_PAIRS, then defaults.
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


def _rank_key(sig, win_rates):
    """Prefer confirmed SIG over LIM, trend/breakout over range, then backtest win rate."""
    source_rank = 1 if sig.get('signal_source') == 'SIG' else 0
    st = sig.get('strategy_type', '')
    strategy_rank = 2 if st == 'trend' else (1 if st == 'breakout' else 0)
    wr = win_rates.get(sig['symbol'], 0.0)
    return (source_rank, strategy_rank, wr)


def main():
    generated_pairs = get_trading_pairs()
    if not generated_pairs:
        log_event(
            "⚠️ No pairs to scan — run `python strategies/simulate_trades.py` to refresh last_backtest.json, "
            "or set CRYPTO_PAIRS in config.py."
        )
        return

    log_event(
        f"📋 Scanning {len(generated_pairs)} pair(s) "
        f"(from last_backtest.json when present, else CRYPTO_PAIRS / defaults)."
    )

    signals = []

    # Primary timeframe scan
    for pair in generated_pairs:
        sig = process_pair(pair)
        if sig is not None:
            signals.append(sig)

    # Multi-timeframe scan: check additional timeframes for more entry opportunities
    if config.MULTI_TF_ENABLED and config.MULTI_TF_EXTRA:
        primary_tf = config.TIMEFRAME
        for extra_tf in config.MULTI_TF_EXTRA:
            if extra_tf == primary_tf:
                continue
            log_event(f"🔄 Multi-TF scan: checking {extra_tf} timeframe...")
            old_tf = config.TIMEFRAME
            config.TIMEFRAME = extra_tf
            for pair in generated_pairs:
                already_signalled = any(s['symbol'] == pair for s in signals)
                if already_signalled:
                    continue
                sig = process_pair(pair)
                if sig is not None:
                    sig['timeframe'] = extra_tf
                    signals.append(sig)
            config.TIMEFRAME = old_tf

    win_rates = get_backtest_win_rates()

    # Drop repeats still within cooldown
    before_cd = len(signals)
    signals = [s for s in signals if not _signal_on_cooldown(s['symbol'], s['direction'])]
    skipped_cd = before_cd - len(signals)
    if skipped_cd:
        log_event(f"⏳ Skipped {skipped_cd} signal(s) still on cooldown ({SIGNAL_COOLDOWN_SEC}s).")

    signals.sort(key=lambda s: _rank_key(s, win_rates), reverse=True)

    if MAX_SIGNALS_PER_CYCLE > 0 and len(signals) > MAX_SIGNALS_PER_CYCLE:
        dropped = signals[MAX_SIGNALS_PER_CYCLE:]
        log_event(
            f"📉 Capping alerts to {MAX_SIGNALS_PER_CYCLE}/cycle; "
            f"holding back: {[d['symbol'] for d in dropped]}"
        )
        signals = signals[:MAX_SIGNALS_PER_CYCLE]

    if signals:
        log_event(
            f"Signals this cycle: "
            f"{[(s['symbol'], s.get('signal_source'), s['direction']) for s in signals]}"
        )

    for sig in signals:
        handle_signal(
            sig['symbol'],
            sig['direction'],
            sig['df'],
            strategy_type=sig['strategy_type'],
            signal_source=sig.get('signal_source', 'SIG'),
            timeframe=sig.get('timeframe', config.TIMEFRAME),
        )

    if len(higher_timeframe_cache) > len(generated_pairs) + 5:
        allowed = set(generated_pairs)
        for sym in list(higher_timeframe_cache):
            if sym not in allowed:
                del higher_timeframe_cache[sym]


if __name__ == '__main__':
    log_event(
        f"🤖 Bot starting (signals-only). Instance={config.BOT_INSTANCE_ID} Host={config.BOT_HOSTNAME} "
        f"PID={config.BOT_PID} Started={config.BOT_STARTED_AT_UTC}"
    )
    admin_ids = config.telegram_admin_id_set()
    if admin_ids:
        log_event(f"🔒 Admin lock ON — {len(admin_ids)} admin id(s); signals → TELEGRAM_CHAT_ID channel")
    else:
        log_event(
            "⚠️ TELEGRAM_ADMIN_IDS unset — any user who can DM the bot may change settings. "
            "Set admin ids before Whop launch."
        )
    chat_dest = config.TELEGRAM_CHAT_ID or "(unset)"
    log_event(f"📣 Signal destination chat_id={chat_dest}")
    executor = ThreadPoolExecutor(max_workers=1)
    executor.submit(poll_telegram)

    if not _eod_job_scheduled:
        schedule.every().day.at("22:00").do(send_eod_report)
        _eod_job_scheduled = True

    if not _auto_backtest_scheduled:
        _schedule_auto_backtest_job()
        _auto_backtest_scheduled = True

    while True:
        try:
            schedule.run_pending()
        except Exception as e:
            log_event(f"Schedule run_pending: {e}")

        if not config.TRADING_ENABLED:
            log_event("🚫 Signal scanning disabled. Sleeping 60 seconds...")
            time.sleep(60)
            continue

        # Follow up posted setups even when scanning is paused for macro/night
        try:
            monitor_signal_outcomes()
        except Exception as e:
            log_event(f"Signal outcome monitor failed: {e}")

        # US high-impact data pause (CPI / NFP / FOMC / GDP) — notify even overnight
        try:
            from utils.macroCalendar import (
                notify_macro_morning_warnings,
                notify_macro_pause_transitions,
            )
            notify_macro_morning_warnings(send_telegram)
            macro_pause = notify_macro_pause_transitions(send_telegram)
        except Exception as e:
            log_event(f"Macro pause check failed: {e}")
            macro_pause = None

        # Reassurance when filters hold (silence ≠ offline)
        try:
            from utils.channelHeartbeat import maybe_send_quiet_heartbeat
            maybe_send_quiet_heartbeat(send_telegram)
        except Exception as e:
            log_event(f"Quiet heartbeat check failed: {e}")

        if macro_pause:
            now_ts = time.time()
            if now_ts - _last_macro_pause_log_ts >= 600:
                _last_macro_pause_log_ts = now_ts
                mins_left = max(1, int(macro_pause["remaining_sec"] // 60))
                log_event(
                    f"Macro pause ({macro_pause['name']}) — skipping scan. "
                    f"Resume in ~{mins_left}m."
                )
            time.sleep(config.MACRO_PAUSE_SLEEP_SEC)
            continue

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

        main()

        # Watchdog: verify all live positions have SL protection
        if config.LIVE_TRADING_ENABLED:
            try:
                from utils.liveTrading import watchdog_check_positions, monitor_trade_outcomes
                watchdog_check_positions()
                monitor_trade_outcomes()
            except Exception as e:
                log_event(f"Watchdog/monitor error: {e}")

        log_event(f"🕒 Waiting {MAIN_LOOP_INTERVAL_SEC}s until next cycle...\n")
        for _ in range(MAIN_LOOP_INTERVAL_SEC // 10):
            try:
                schedule.run_pending()
            except Exception:
                pass
            time.sleep(10)
