import sys
import os
import json
import math
from datetime import datetime, timedelta, timezone

import pandas as pd
import pandas_ta as ta
import time

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../')))

from config import (
    BACKTEST_SLIPPAGE_BPS, BACKTEST_COMMISSION_BPS,
    BACKTEST_COOLDOWN_BARS, BACKTEST_LOOKAHEAD, BACKTEST_DAYS,
    MIN_ADX_TREND,
)
from utils.utils import (
    check_long_signal, check_short_signal, calculate_trade_levels,
    add_atr_column, check_range_trade, is_ranging, log_event,
)
from utils.exchangeUtils import get_exchange, get_top_tradable_pairs

BACKTEST_STATE_FILE = os.path.join(os.path.dirname(__file__), '..', 'last_backtest.json')
DEFAULT_BACKTEST_PAIRS = [
    'BTC/USDT', 'ETH/USDT', 'XRP/USDT', 'BNB/USDT', 'SOL/USDT', 'TRX/USDT',
    'DOGE/USDT', 'ADA/USDT', 'LINK/USDT', 'XLM/USDT', 'HBAR/USDT', 'LTC/USDT',
    'AVAX/USDT', 'SHIB/USDT', 'SUI/USDT', 'UNI/USDT'
]

def _get_exchange():
    return get_exchange()


def _apply_slippage(price, direction):
    """Worsen the entry price by BACKTEST_SLIPPAGE_BPS basis points."""
    slip = price * (BACKTEST_SLIPPAGE_BPS / 10_000)
    if direction in ('buy', 'long'):
        return price + slip
    return price - slip


def _commission_cost(price):
    """Per-side commission in price units."""
    return price * (BACKTEST_COMMISSION_BPS / 10_000)


def _compute_risk_metrics(pnl_list):
    """Compute risk metrics from a list of per-trade P&L percentages."""
    if not pnl_list:
        return {'sharpe': 0.0, 'max_drawdown_pct': 0.0, 'profit_factor': 0.0, 'avg_win': 0.0, 'avg_loss': 0.0}

    wins = [p for p in pnl_list if p > 0]
    losses = [p for p in pnl_list if p < 0]

    avg_win = sum(wins) / len(wins) if wins else 0.0
    avg_loss = sum(losses) / len(losses) if losses else 0.0
    gross_profit = sum(wins)
    gross_loss = abs(sum(losses))
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else float('inf') if gross_profit > 0 else 0.0

    equity = [1.0]
    for p in pnl_list:
        equity.append(equity[-1] * (1 + p))
    peak = equity[0]
    max_dd = 0.0
    for e in equity:
        if e > peak:
            peak = e
        dd = (peak - e) / peak if peak > 0 else 0
        if dd > max_dd:
            max_dd = dd

    mean_ret = sum(pnl_list) / len(pnl_list)
    if len(pnl_list) > 1:
        variance = sum((p - mean_ret) ** 2 for p in pnl_list) / (len(pnl_list) - 1)
        std = math.sqrt(variance)
        sharpe = (mean_ret / std) * math.sqrt(252) if std > 0 else 0.0
    else:
        sharpe = 0.0

    return {
        'sharpe': round(sharpe, 2),
        'max_drawdown_pct': round(max_dd * 100, 2),
        'profit_factor': round(profit_factor, 2),
        'avg_win_pct': round(avg_win * 100, 4),
        'avg_loss_pct': round(avg_loss * 100, 4),
        'equity_curve': [round(e, 4) for e in equity],
    }


def _get_backtest_pairs(pairs_override=None):
    """Resolve pair list: override, then get_top_tradable_pairs, then env BACKTEST_PAIRS, then default."""
    if pairs_override:
        return [(s, None, None) if isinstance(s, str) else s for s in pairs_override]
    try:
        pairs = get_top_tradable_pairs(_get_exchange(), quote='USDT', top_n=20)
        if pairs:
            return pairs
    except Exception as e:
        log_event(f"get_top_tradable_pairs failed (e.g. CoinGecko blocked): {e}. Using fallback list.")
    env_pairs = os.getenv("BACKTEST_PAIRS", "").strip().split(",")
    env_pairs = [p.strip() for p in env_pairs if p.strip()]
    if env_pairs:
        return [(s, None, None) for s in env_pairs]
    return [(s, None, None) for s in DEFAULT_BACKTEST_PAIRS]


def fetch_data(pair, timeframe='5m', days=BACKTEST_DAYS):
    all_ohlcv = []
    now = datetime.now()
    since = int((now - timedelta(days=days)).timestamp() * 1000)

    limit = 200
    max_tries = 30
    loops = 0

    while loops < max_tries:
        ohlcv = _get_exchange().fetch_ohlcv(pair, timeframe=timeframe, since=since, limit=limit)

        if not ohlcv:
            break

        all_ohlcv.extend(ohlcv)

        last_timestamp = ohlcv[-1][0]
        since = last_timestamp + 60_000
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

    df['ma10'] = df['close'].rolling(10).mean()
    df['ma20'] = df['close'].rolling(20).mean()
    df['ma50'] = df['close'].rolling(50).mean()
    df['rsi'] = df.ta.rsi(length=14)
    df['adx'] = df.ta.adx(length=14)['ADX_14']
    df['support'] = df['low'].rolling(window=50).min()
    df['resistance'] = df['high'].rolling(window=50).max()

    return df


def fetch_higher_timeframe_data(pair, timeframe='15m', days=BACKTEST_DAYS):
    all_ohlcv = []
    now = datetime.now()
    since = int((now - timedelta(days=days)).timestamp() * 1000)

    limit = 200
    loops = 0
    while loops < 30:
        ohlcv = _get_exchange().fetch_ohlcv(pair, timeframe=timeframe, since=since, limit=limit)
        if not ohlcv:
            break
        all_ohlcv.extend(ohlcv)
        last_timestamp = ohlcv[-1][0]
        since = last_timestamp + 60_000 * 15
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


def check_trade_outcome(df, start_idx, direction, entry_price,
                        max_lookahead=BACKTEST_LOOKAHEAD, strategy="trend"):
    """Resolve a trade against TP/SL levels. Returns dict with result and P&L.

    Expects df to already have an 'ATR' column (precomputed).
    """
    if 'ATR' not in df.columns:
        df = add_atr_column(df, period=7)

    entry_price = _apply_slippage(entry_price, direction)
    commission = _commission_cost(entry_price) * 2

    levels = calculate_trade_levels(entry_price, direction, df, start_idx, strategy)
    tp, sl = levels['take_profit'], levels['stop_loss']

    is_long = direction in ('buy', 'long')

    for j in range(1, max_lookahead + 1):
        if start_idx + j >= len(df):
            break
        high = df['high'].iat[start_idx + j]
        low = df['low'].iat[start_idx + j]
        if is_long:
            if high >= tp:
                pnl_pct = (tp - entry_price - commission) / entry_price
                return {'result': 'win', 'pnl_pct': pnl_pct}
            if low <= sl:
                pnl_pct = (sl - entry_price - commission) / entry_price
                return {'result': 'loss', 'pnl_pct': pnl_pct}
        else:
            if low <= tp:
                pnl_pct = (entry_price - tp - commission) / entry_price
                return {'result': 'win', 'pnl_pct': pnl_pct}
            if high >= sl:
                pnl_pct = (entry_price - sl - commission) / entry_price
                return {'result': 'loss', 'pnl_pct': pnl_pct}

    final_close = df['close'].iat[min(len(df) - 1, start_idx + max_lookahead)]
    if is_long:
        pnl_pct = (final_close - entry_price - commission) / entry_price
    else:
        pnl_pct = (entry_price - final_close - commission) / entry_price

    result = 'win' if pnl_pct > 0 else 'loss'
    return {'result': result, 'pnl_pct': pnl_pct}


def _get_signal_at_bar(slice_df, htf_slice, entry_price):
    """Same signal logic as live at one bar. Returns ('buy'|'sell', 'trend'|'range') or None."""
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
    adx_ok = (MIN_ADX_TREND <= 0 or ('adx' in slice_df.columns and pd.notna(slice_df['adx'].iloc[-1]) and slice_df['adx'].iloc[-1] >= MIN_ADX_TREND))
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


def simulate_combined_strategy(pair, df_5m, df_1h):
    long_wins = long_losses = long_none = 0
    short_wins = short_losses = short_none = 0
    strategy_used = []
    pnl_list = []
    last_trade_bar = -BACKTEST_COOLDOWN_BARS

    df_5m = add_atr_column(df_5m, period=7)

    for i in range(60, len(df_5m) - 10):
        if (i - last_trade_bar) < BACKTEST_COOLDOWN_BARS:
            continue

        slice_df = df_5m.iloc[:i + 1]
        entry_price = float(df_5m['close'].iat[i])

        curr_time = df_5m['timestamp'].iat[i]
        htf_slice = df_1h[df_1h['timestamp'] <= curr_time].iloc[-6:]

        if len(htf_slice) < 6:
            continue

        ma20_slope = htf_slice['ma20'].iloc[-1] - htf_slice['ma20'].iloc[-4]

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

        adx_ok = (MIN_ADX_TREND <= 0 or
                  ('adx' in slice_df.columns and pd.notna(slice_df['adx'].iloc[-1]) and slice_df['adx'].iloc[-1] >= MIN_ADX_TREND))

        direction = None
        strat = None

        if adx_ok and check_long_signal(slice_df) and trend_up:
            direction, strat = 'buy', 'trend'
        elif adx_ok and check_short_signal(slice_df) and trend_down:
            direction, strat = 'sell', 'trend'
        elif is_ranging(slice_df) and not trend_up and not trend_down:
            buy_signal, sell_signal = check_range_trade(slice_df)
            if buy_signal:
                direction, strat = 'buy', 'range'
            elif sell_signal:
                direction, strat = 'sell', 'range'

        if direction is None:
            continue

        last_trade_bar = i
        outcome = check_trade_outcome(df_5m, i, direction, entry_price, BACKTEST_LOOKAHEAD, strat)
        result = outcome['result']
        pnl_list.append(outcome['pnl_pct'])
        strategy_used.append('ma' if strat == 'trend' else 'range')

        is_long = direction == 'buy'
        if result == 'win':
            if is_long:
                long_wins += 1
            else:
                short_wins += 1
        elif result == 'loss':
            if is_long:
                long_losses += 1
            else:
                short_losses += 1
        else:
            if is_long:
                long_none += 1
            else:
                short_none += 1

    total_trades = long_wins + long_losses + long_none + short_wins + short_losses + short_none
    total_wins = long_wins + short_wins
    win_rate = round(total_wins / total_trades * 100, 2) if total_trades > 0 else 0
    range_used = strategy_used.count('range')
    ma_used = strategy_used.count('ma')

    risk_metrics = _compute_risk_metrics(pnl_list)

    log_event(f"\n--- Results for {pair} ---")
    log_event(f"Total Trades: {total_trades}")
    log_event(f"Wins: {total_wins} (Long: {long_wins}, Short: {short_wins})")
    log_event(f"Losses: {long_losses + short_losses} (Long: {long_losses}, Short: {short_losses})")
    log_event(f"Win Rate: {win_rate}%")
    log_event(f"MA Usage: {ma_used}, Range Usage: {range_used}")
    log_event(f"Sharpe: {risk_metrics['sharpe']} | Max DD: {risk_metrics['max_drawdown_pct']}% | PF: {risk_metrics['profit_factor']}")
    log_event(f"Avg Win: {risk_metrics['avg_win_pct']}% | Avg Loss: {risk_metrics['avg_loss_pct']}%")

    result = {
        'win_rate': win_rate,
        'total_trades': total_trades,
        'ma_used': ma_used,
        'range_used': range_used,
    }
    result.update(risk_metrics)
    return result


def run_backtest(pairs_override=None):
    """Run backtest on pairs. Persists good_pairs and per-pair results to last_backtest.json."""
    pairs = _get_backtest_pairs(pairs_override)
    win_rate_threshold = float(os.getenv("BACKTEST_WIN_RATE_THRESHOLD", "50"))
    min_trades = int(os.getenv("BACKTEST_MIN_TRADES", "3"))
    min_pairs = int(os.getenv("BACKTEST_MIN_PAIRS", "3"))
    top_n_fallback = int(os.getenv("BACKTEST_TOP_N_FALLBACK", "8"))

    good_pairs = []
    results_by_symbol = {}

    log_event(f"Backtest pairs: {[p[0] for p in pairs]}")
    for pair in pairs:
        symbol = pair[0] if isinstance(pair, (list, tuple)) else pair
        try:
            df = fetch_data(symbol, '5m', days=BACKTEST_DAYS)
            df_1h = fetch_higher_timeframe_data(symbol, '15m', days=BACKTEST_DAYS)
            if len(df) > 300:
                result = simulate_combined_strategy(pair, df, df_1h)
                result_save = {k: v for k, v in result.items() if k != 'equity_curve'}
                results_by_symbol[symbol] = result_save
                log_event(f"CHECKING BACKTEST: {result_save}")
                total_trades = result.get('total_trades', 0)
                if total_trades >= min_trades and result['win_rate'] >= win_rate_threshold:
                    good_pairs.append(symbol)
        except Exception as e:
            log_event(f"❌ Error backtesting {symbol}: {e}")

    # If too few pairs passed the threshold, take top N by win rate (then by total_trades) so we trade multiple pairs
    if len(good_pairs) < min_pairs and results_by_symbol:
        sorted_symbols = sorted(
            results_by_symbol.keys(),
            key=lambda s: (
                results_by_symbol[s].get('win_rate', 0),
                results_by_symbol[s].get('total_trades', 0),
            ),
            reverse=True,
        )
        # Only include pairs that have at least min_trades (avoid 1-trade flukes)
        fallback = [
            s for s in sorted_symbols
            if results_by_symbol[s].get('total_trades', 0) >= min_trades
        ][:top_n_fallback]
        if fallback:
            log_event(f"Fallback: only {len(good_pairs)} passed threshold; using top {len(fallback)} by win rate: {fallback}")
            good_pairs = fallback

    state = {
        "pairs": good_pairs,
        "run_at": datetime.now(timezone.utc).isoformat(),
        "win_rate_threshold": win_rate_threshold,
        "min_trades": min_trades,
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
    """
    pairs = _get_backtest_pairs(pairs_override)
    symbols = [p[0] if isinstance(p, (list, tuple)) else p for p in pairs]

    state_path = os.path.abspath(BACKTEST_STATE_FILE)
    results_by_symbol = {}
    if os.path.isfile(state_path):
        try:
            with open(state_path, 'r') as f:
                data = json.load(f)
            results_by_symbol = data.get('results', {})
        except Exception:
            pass

    data_by_symbol = {}
    for sym in symbols:
        try:
            df_5m = fetch_data(sym, '5m', days=BACKTEST_DAYS)
            df_15m = fetch_higher_timeframe_data(sym, '15m', days=BACKTEST_DAYS)
            if len(df_5m) > 300 and len(df_15m) > 50:
                df_5m = add_atr_column(df_5m, period=7)
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

    pnl_list = []
    last_trade_bar_by_sym = {s: -BACKTEST_COOLDOWN_BARS for s in data_by_symbol}

    for i in range(60, min_len):
        signals_at_bar = []
        for symbol, (df_5m, df_15m) in data_by_symbol.items():
            if (i - last_trade_bar_by_sym[symbol]) < BACKTEST_COOLDOWN_BARS:
                continue
            slice_df = df_5m.iloc[: i + 1]
            curr_time = df_5m['timestamp'].iat[i]
            htf_slice = df_15m[df_15m['timestamp'] <= curr_time].iloc[-6:]
            entry_price = float(df_5m['close'].iat[i])
            sig = _get_signal_at_bar(slice_df, htf_slice, entry_price)
            if sig is not None:
                direction, strategy_type = sig
                win_rate = 0.0
                if isinstance(results_by_symbol.get(symbol), dict):
                    win_rate = float(results_by_symbol[symbol].get('win_rate', 0))
                signals_at_bar.append((symbol, i, entry_price, direction, strategy_type, win_rate))

        signals_at_bar.sort(key=lambda x: x[5], reverse=True)
        for t in signals_at_bar[:max_trades_per_bar]:
            symbol, idx, entry_price, direction, strategy_type, _ = t
            df_5m = data_by_symbol[symbol][0]
            outcome = check_trade_outcome(df_5m, idx, direction, entry_price, BACKTEST_LOOKAHEAD, strategy_type)
            pnl_list.append(outcome['pnl_pct'])
            last_trade_bar_by_sym[symbol] = i

    total_wins = sum(1 for p in pnl_list if p > 0)
    total_losses = sum(1 for p in pnl_list if p <= 0)
    total_trades = len(pnl_list)
    system_win_rate = round(total_wins / total_trades * 100, 2) if total_trades > 0 else 0.0

    risk_metrics = _compute_risk_metrics(pnl_list)

    log_event(f"\n--- Portfolio backtest (max {max_trades_per_bar} trades/bar) ---")
    log_event(f"Total trades: {total_trades}, Wins: {total_wins}, Losses: {total_losses}")
    log_event(f"System win rate: {system_win_rate}%")
    log_event(f"Sharpe: {risk_metrics['sharpe']} | Max DD: {risk_metrics['max_drawdown_pct']}% | PF: {risk_metrics['profit_factor']}")

    if os.path.isfile(state_path):
        try:
            with open(state_path, 'r') as f:
                state = json.load(f)
            state['portfolio_win_rate'] = system_win_rate
            state['portfolio_trades'] = total_trades
            state['portfolio_sharpe'] = risk_metrics['sharpe']
            state['portfolio_max_drawdown_pct'] = risk_metrics['max_drawdown_pct']
            state['portfolio_profit_factor'] = risk_metrics['profit_factor']
            state['portfolio_run_at'] = datetime.now(timezone.utc).isoformat()
            with open(state_path, 'w') as f:
                json.dump(state, f, indent=2)
        except Exception as e:
            log_event(f"Could not write portfolio results to state: {e}")

    return system_win_rate


if __name__ == "__main__":
    results = run_backtest()
    print("Backtest completed, good pairs:", results)
    if results:
        run_portfolio_backtest(pairs_override=results, max_trades_per_bar=3)
