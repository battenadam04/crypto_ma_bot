import sys
import os
import json
from datetime import datetime, timedelta, timezone

import pandas as pd
import pandas_ta as ta
import time

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../')))

from utils.utils import (
    check_long_signal, check_short_signal, calculate_trade_levels, add_atr_column, check_range_trade, is_ranging, log_event,
)
from utils.exchangeUtils import init_exchange, get_top_tradable_pairs

BACKTEST_STATE_FILE = os.path.join(os.path.dirname(__file__), '..', 'last_backtest.json')
DEFAULT_BACKTEST_PAIRS = [
    'BTC/USDT', 'ETH/USDT', 'XRP/USDT', 'BNB/USDT', 'SOL/USDT', 'TRX/USDT',
    'DOGE/USDT', 'ADA/USDT', 'LINK/USDT', 'XLM/USDT', 'HBAR/USDT', 'LTC/USDT',
    'AVAX/USDT', 'SHIB/USDT', 'SUI/USDT', 'UNI/USDT'
]

exchange = init_exchange()


def _get_backtest_pairs(pairs_override=None):
    """Resolve pair list: override, then get_top_tradable_pairs, then env BACKTEST_PAIRS, then default."""
    if pairs_override:
        return [(s, None, None) if isinstance(s, str) else s for s in pairs_override]
    try:
        pairs = get_top_tradable_pairs(exchange, quote='USDT', top_n=20)
        if pairs:
            return pairs
    except Exception as e:
        log_event(f"get_top_tradable_pairs failed (e.g. CoinGecko blocked): {e}. Using fallback list.")
    env_pairs = os.getenv("BACKTEST_PAIRS", "").strip().split(",")
    env_pairs = [p.strip() for p in env_pairs if p.strip()]
    if env_pairs:
        return [(s, None, None) for s in env_pairs]
    return [(s, None, None) for s in DEFAULT_BACKTEST_PAIRS]


def fetch_data(pair, timeframe='5m', days=90):
    all_ohlcv = []
    now = datetime.now()
    since = int((now - timedelta(days=days)).timestamp() * 1000)

    limit = 200  # hard limit
    max_tries = 30  #increase this if needed
    loops = 0

    while loops < max_tries:
        ohlcv = exchange.fetch_ohlcv(pair, timeframe=timeframe, since=since, limit=limit)

        if not ohlcv:
            break

        all_ohlcv.extend(ohlcv)

        last_timestamp = ohlcv[-1][0]
        since = last_timestamp + 60_000  # advance 1 minute
        loops += 1

        time.sleep(0.3)  # rate limit buffer

        # Optional: stop early if already have enough data
        if len(all_ohlcv) >= 1000:
            break

    if not all_ohlcv:
        return pd.DataFrame()

    # Remove duplicates (sometimes exchanges return overlapping data)
    seen = set()
    unique_ohlcv = []
    for row in all_ohlcv:
        if row[0] not in seen:
            unique_ohlcv.append(row)
            seen.add(row[0])

    df = pd.DataFrame(unique_ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')

    # Add indicators
    df['ma10'] = df['close'].rolling(10).mean()
    df['ma20'] = df['close'].rolling(20).mean()
    df['ma50'] = df['close'].rolling(50).mean()
    df['rsi'] = df.ta.rsi(length=14)
    df['adx'] = df.ta.adx(length=14)['ADX_14']
    df['support'] = df['low'].rolling(window=50).min()
    df['resistance'] = df['high'].rolling(window=50).max()

    return df

def fetch_higher_timeframe_data(pair, timeframe='15m', days=90):
    all_ohlcv = []
    now = datetime.now()
    since = int((now - timedelta(days=days)).timestamp() * 1000)

    limit = 200
    loops = 0
    while loops < 30:
        ohlcv = exchange.fetch_ohlcv(pair, timeframe=timeframe, since=since, limit=limit)
        if not ohlcv:
            break
        all_ohlcv.extend(ohlcv)
        last_timestamp = ohlcv[-1][0]
        since = last_timestamp + 60_000 * 15  # advance 1h
        loops += 1
        time.sleep(0.3)
        if len(all_ohlcv) >= 1000:
            break

    if not all_ohlcv:
        return pd.DataFrame()

    seen = set()
    unique_ohlcv = []
    for row in all_ohlcv:
        if row[0] not in seen:
            unique_ohlcv.append(row)
            seen.add(row[0])

    df = pd.DataFrame(unique_ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
    df['ma20'] = df['close'].rolling(20).mean()
    df['ma50'] = df['close'].rolling(50).mean()
    return df




def check_trade_outcome(df, start_idx, direction, entry_price, max_lookahead=50, strategy="trend"):
    df = add_atr_column(df, period=7)
    levels = calculate_trade_levels(entry_price, direction, df, start_idx, strategy)
    tp, sl = levels['take_profit'], levels['stop_loss']

    is_long = direction in ('buy', 'long')
    for j in range(1, max_lookahead + 1):
        if start_idx + j >= len(df):
            break
        high, low = df.iloc[start_idx + j][['high', 'low']]
        if is_long:
            if high >= tp: return 'win'
            if low <= sl: return 'loss'
        else:
            if low <= tp: return 'win'
            if high >= sl: return 'loss'

    # Final fallback: resolve based on final close price
    final_close = df.iloc[min(len(df)-1, start_idx + max_lookahead)]['close']
    if is_long:
        return 'win' if final_close > entry_price else 'loss'
    return 'win' if final_close < entry_price else 'loss'


def _get_signal_at_bar(slice_df, htf_slice, entry_price):
    """
    Same signal logic as live/backtest at one bar. Returns ('buy'|'sell', 'trend'|'range') or None.
    """
    if len(htf_slice) < 6:
        return None
    ma20_slope = htf_slice['ma20'].iloc[-1] - htf_slice['ma20'].iloc[-4]
    trend_up = (
        htf_slice['ma20'].iloc[-1] > htf_slice['ma50'].iloc[-1] and
        htf_slice['ma20'].iloc[-1] > htf_slice['ma20'].iloc[-5] and ma20_slope > 0
    )
    trend_down = (
        htf_slice['ma20'].iloc[-1] < htf_slice['ma50'].iloc[-1] and
        htf_slice['ma20'].iloc[-1] < htf_slice['ma20'].iloc[-5] and ma20_slope < 0
    )
    min_adx = float(os.getenv("MIN_ADX_TREND", "0"))
    adx_ok = (min_adx <= 0 or ('adx' in slice_df.columns and pd.notna(slice_df['adx'].iloc[-1]) and slice_df['adx'].iloc[-1] >= min_adx))
    if adx_ok and check_long_signal(slice_df) and trend_up:
        return ('buy', 'trend')
    if adx_ok and check_short_signal(slice_df) and trend_down:
        return ('sell', 'trend')
    if is_ranging(slice_df) and not trend_up and not trend_down:
        buy_signal, sell_signal = check_range_trade(slice_df)
        if buy_signal:
            return ('buy', 'range')
        if sell_signal:
            return ('sell', 'range')
    return None


def simulate_combined_strategy(pair, df_5m,df_1h):
    long_wins = long_losses = long_none = 0
    short_wins = short_losses = short_none = 0
    strategy_used = []

    for i in range(60, len(df_5m) - 10):
        slice_df = df_5m.iloc[:i+1]
        current = df_5m.iloc[i]
        entry_price = float(current['close'])

        # Align with live: use 6-bar 15m slice so iloc[-5] and iloc[-4] exist; slope = current - 4 bars ago
        curr_time = df_5m.iloc[i]['timestamp']
        htf_slice = df_1h[df_1h['timestamp'] <= curr_time].iloc[-6:]

        if len(htf_slice) < 6:
            continue  # not enough higher timeframe data

        ma20_slope = htf_slice['ma20'].iloc[-1] - htf_slice['ma20'].iloc[-4]  # same as live (4-bar lookback)

        trend_up = (
            htf_slice['ma20'].iloc[-1] > htf_slice['ma50'].iloc[-1] and
            htf_slice['ma20'].iloc[-1] > htf_slice['ma20'].iloc[-5] and
            ma20_slope > 0
        )

        trend_down = (
            htf_slice['ma20'].iloc[-1] < htf_slice['ma50'].iloc[-1] and
            htf_slice['ma20'].iloc[-1] < htf_slice['ma20'].iloc[-5] and
            ma20_slope < 0
        )

        min_adx = float(os.getenv("MIN_ADX_TREND", "0"))
        adx_ok = (min_adx <= 0 or
                  ('adx' in slice_df.columns and pd.notna(slice_df['adx'].iloc[-1]) and slice_df['adx'].iloc[-1] >= min_adx))

        if adx_ok and check_long_signal(slice_df) and trend_up:
                result = check_trade_outcome(df_5m, i, 'buy', entry_price, 50, 'trend')
                strategy_used.append('ma')
                if result == 'win':
                    long_wins += 1
                elif result == 'loss':
                    long_losses += 1
                else:
                    long_none += 1
        elif adx_ok and check_short_signal(slice_df) and trend_down:
                result = check_trade_outcome(df_5m, i, 'sell', entry_price, 50, 'trend')
                strategy_used.append('ma')
                if result == 'win':
                    short_wins += 1
                elif result == 'loss':
                    short_losses += 1
                else:
                    short_none += 1
        elif is_ranging(slice_df) and not trend_up and not trend_down:
            buy_signal, sell_signal = check_range_trade(slice_df)
            if buy_signal:
                result = check_trade_outcome(df_5m, i, 'buy', entry_price, 50, 'range')
                strategy_used.append('range')
                if result == 'win':
                    long_wins += 1
                elif result == 'loss':
                    long_losses += 1
                else:
                    long_none += 1
            elif sell_signal:
                result = check_trade_outcome(df_5m, i, 'sell', entry_price, 50, 'range')
                strategy_used.append('range')
                if result == 'win':
                    short_wins += 1
                elif result == 'loss':
                    short_losses += 1
                else:
                    short_none += 1



    total_trades = long_wins + long_losses + long_none + short_wins + short_losses + short_none
    total_wins = long_wins + short_wins
    win_rate = round(total_wins / total_trades * 100, 2) if total_trades > 0 else 0
    range_used = strategy_used.count('range')
    ma_used = strategy_used.count('ma')

    log_event(f"\n--- Results for {pair} ---")
    log_event(f"Total Trades: {total_trades}")
    log_event(f"Wins: {total_wins} (Long: {long_wins}, Short: {short_wins})")
    log_event(f"Losses: {long_losses + short_losses} (Long: {long_losses}, Short: {short_losses})")
    log_event(f"Unresolved: {long_none + short_none} (Long: {long_none}, Short: {short_none})")
    log_event(f"Win Rate: {win_rate}%")
    log_event(f"MA Usage: {ma_used}, Range Usage: {range_used}")

    return {
                'win_rate': win_rate,
                'total_trades': total_trades,
                'ma_used': ma_used,
                'range_used': range_used
            }

def run_backtest(pairs_override=None):
    """
    Run backtest on pairs from get_top_tradable_pairs, or fallback to BACKTEST_PAIRS env / default.
    Persists good_pairs and per-pair results to last_backtest.json for live to use.
    """
    pairs = _get_backtest_pairs(pairs_override)
    win_rate_threshold = float(os.getenv("BACKTEST_WIN_RATE_THRESHOLD", "55"))

    good_pairs = []
    results_by_symbol = {}

    log_event(f"Backtest pairs: {[p[0] for p in pairs]}")
    for pair in pairs:
        symbol = pair[0] if isinstance(pair, (list, tuple)) else pair
        try:
            df = fetch_data(symbol, '5m', days=90)
            df_1h = fetch_higher_timeframe_data(symbol, '15m', days=90)
            if len(df) > 300:
                result = simulate_combined_strategy(pair, df, df_1h)
                results_by_symbol[symbol] = result
                log_event(f"CHECKING BACKTEST: {result}")
                if result['win_rate'] >= win_rate_threshold:
                    good_pairs.append(symbol)
        except Exception as e:
            log_event(f"❌ Error backtesting {symbol}: {e}")

    state = {
        "pairs": good_pairs,
        "run_at": datetime.now(timezone.utc).isoformat(),
        "win_rate_threshold": win_rate_threshold,
        "results": results_by_symbol,
    }
    try:
        path = os.path.abspath(BACKTEST_STATE_FILE)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            json.dump(state, f, indent=2)
        log_event(f"Wrote backtest state to {path} ({len(good_pairs)} good pairs).")
    except Exception as e:
        log_event(f"Failed to write last_backtest.json: {e}")

    return good_pairs


def run_portfolio_backtest(pairs_override=None, max_trades_per_bar=3):
    """
    Backtest the same way you trade live: at each bar, collect signals across all pairs,
    pick the top N by backtest win rate (same order as live), and resolve those trades.
    Returns a single *system* win rate so you can compare with live performance.

    Run after run_backtest() so last_backtest.json has per-pair results (used for ordering).
    """
    pairs = _get_backtest_pairs(pairs_override)
    symbols = [p[0] if isinstance(p, (list, tuple)) else p for p in pairs]

    # Load backtest win rates for ordering (same as live)
    state_path = os.path.abspath(BACKTEST_STATE_FILE)
    results_by_symbol = {}
    if os.path.isfile(state_path):
        try:
            with open(state_path, 'r') as f:
                data = json.load(f)
            results_by_symbol = data.get('results', {})
        except Exception:
            pass

    # Load 5m and 15m for each pair
    data_by_symbol = {}
    for sym in symbols:
        try:
            df_5m = fetch_data(sym, '5m', days=90)
            df_15m = fetch_higher_timeframe_data(sym, '15m', days=90)
            if len(df_5m) > 300 and len(df_15m) > 50:
                data_by_symbol[sym] = (df_5m, df_15m)
        except Exception as e:
            log_event(f"Portfolio backtest: skip {sym}: {e}")

    if not data_by_symbol:
        log_event("Portfolio backtest: no data for any pair.")
        return 0.0

    min_len = min(len(data_by_symbol[s][0]) for s in data_by_symbol) - 10
    if min_len < 70:
        log_event("Portfolio backtest: insufficient common bars.")
        return 0.0

    total_wins = total_losses = 0
    for i in range(60, min_len):
        signals_at_bar = []
        for symbol, (df_5m, df_15m) in data_by_symbol.items():
            slice_df = df_5m.iloc[: i + 1]
            curr_time = df_5m.iloc[i]['timestamp']
            htf_slice = df_15m[df_15m['timestamp'] <= curr_time].iloc[-6:]
            entry_price = float(df_5m.iloc[i]['close'])
            sig = _get_signal_at_bar(slice_df, htf_slice, entry_price)
            if sig is not None:
                direction, strategy_type = sig
                win_rate = 0.0
                if isinstance(results_by_symbol.get(symbol), dict):
                    win_rate = float(results_by_symbol[symbol].get('win_rate', 0))
                signals_at_bar.append((symbol, i, entry_price, direction, strategy_type, win_rate))

        # Same as live: take top N by backtest win rate
        signals_at_bar.sort(key=lambda x: x[5], reverse=True)
        for t in signals_at_bar[:max_trades_per_bar]:
            symbol, idx, entry_price, direction, strategy_type, _ = t
            df_5m = data_by_symbol[symbol][0]
            result = check_trade_outcome(df_5m, idx, direction, entry_price, 50, strategy_type)
            if result == 'win':
                total_wins += 1
            elif result == 'loss':
                total_losses += 1

    total_trades = total_wins + total_losses
    system_win_rate = round(total_wins / total_trades * 100, 2) if total_trades > 0 else 0.0
    log_event(f"\n--- Portfolio backtest (max {max_trades_per_bar} trades/bar, order by backtest win rate) ---")
    log_event(f"Total trades: {total_trades}, Wins: {total_wins}, Losses: {total_losses}")
    log_event(f"System win rate: {system_win_rate}%")

    # Persist so you can compare with live
    if os.path.isfile(state_path):
        try:
            with open(state_path, 'r') as f:
                state = json.load(f)
            state['portfolio_win_rate'] = system_win_rate
            state['portfolio_trades'] = total_trades
            state['portfolio_run_at'] = datetime.now(timezone.utc).isoformat()
            with open(state_path, 'w') as f:
                json.dump(state, f, indent=2)
        except Exception as e:
            log_event(f"Could not write portfolio_win_rate to state: {e}")

    return system_win_rate


if __name__ == "__main__":
    results = run_backtest()
    print("Backtest completed, good pairs:", results)
    # Optional: run portfolio backtest to get system win rate (matches multi-pair live behavior)
    if results:
        run_portfolio_backtest(pairs_override=results, max_trades_per_bar=3)