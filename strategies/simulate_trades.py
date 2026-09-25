import sys
import os
import json
import math
import types
from datetime import datetime, timedelta, timezone

import pandas as pd
import time

try:
    import pandas_ta as ta  # noqa: F401 — registers DataFrame.ta for prepare_ltf_frame
    _HAS_PANDAS_TA = True
except ModuleNotFoundError:
    _HAS_PANDAS_TA = False
    sys.modules.setdefault("pandas_ta", types.ModuleType("pandas_ta"))


sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../')))

import config

from config import (
    BACKTEST_SLIPPAGE_BPS, BACKTEST_COMMISSION_BPS,
    BACKTEST_LOOKAHEAD, BACKTEST_DAYS,
    LIMIT_ENTRY_OFFSET_PCT,
    BACKTEST_USE_LIMIT_IDEAS, BACKTEST_LIMIT_FILL_BARS, BACKTEST_MIN_RR_RATIO,
    BACKTEST_WIN_RATE_THRESHOLD, BACKTEST_ENFORCE_RR, BACKTEST_APPLY_FEES,
    BACKTEST_AUTO_TOP_PAIRS, BACKTEST_PAIRS,
    BACKTEST_OHLCV_LIMIT, BACKTEST_FETCH_SLEEP_SEC, BACKTEST_VERBOSE,
    CRYPTO_PAIRS, EXCHANGE, SR_LOOKBACK_BARS, ENABLE_LIMIT_IDEA_FALLBACK,
    TIMEFRAME, HTF_TIMEFRAME, BACKTEST_MIN_TRADES,
    MAX_SIGNALS_PER_CYCLE,
)
from utils.utils import (
    add_atr_column,
    log_event,
)
from utils.signalLogic import (
    closed_bars_only,
    evaluate_signal_at_bar,
    htf_slice_for_bar,
    levels_for_signal,
    prepare_htf_frame,
    prepare_ltf_frame,
    rank_signal_key,
    resolve_outcome_on_df,
    signal_cooldown_bars,
    signal_config_snapshot,
)
from utils.exchangeUtils import get_exchange, get_auto_backtest_pairs

BACKTEST_STATE_FILE = os.path.join(os.path.dirname(__file__), '..', 'last_backtest.json')
# LIM must match live: one flag only (ENABLE_LIMIT_IDEA_FALLBACK).
_BACKTEST_PER_PAIR_LIMIT_FALLBACK = bool(ENABLE_LIMIT_IDEA_FALLBACK)


def _cooldown_bars() -> int:
    """Same silence window as live SIGNAL_COOLDOWN_SEC, in bars of TIMEFRAME."""
    return signal_cooldown_bars(TIMEFRAME)


# Fallback universes when CRYPTO_PAIRS / BACKTEST_PAIRS / auto-discovery are unset.
DEFAULT_BACKTEST_PAIRS_PHEMEX = [
    'XRP/USDT:USDT', 'SOL/USDT:USDT', 'DOGE/USDT:USDT', 'ADA/USDT:USDT',
    'LINK/USDT:USDT', 'AVAX/USDT:USDT', 'LTC/USDT:USDT', 'UNI/USDT:USDT',
    'DOT/USDT:USDT', 'ATOM/USDT:USDT',
]
DEFAULT_BACKTEST_PAIRS_BINANCE = [
    'XRP/USDT', 'SOL/USDT', 'DOGE/USDT', 'ADA/USDT',
    'LINK/USDT', 'AVAX/USDT', 'LTC/USDT', 'UNI/USDT',
    'DOT/USDT', 'ATOM/USDT',
]


def _default_backtest_pair_symbols():
    if EXCHANGE.strip().lower() == "binance_margin":
        return DEFAULT_BACKTEST_PAIRS_BINANCE
    return DEFAULT_BACKTEST_PAIRS_PHEMEX

def _bt_log(message: str, *, verbose: bool = False):
    """Backtest logging: keep output minimal unless BACKTEST_VERBOSE=true."""
    if verbose and not BACKTEST_VERBOSE:
        return
    log_event(message)

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


def _suggest_limit_entry(slice_df, direction, strategy_type, entry_price):
    """
    Mirror live limit suggestion logic for backtests.
    Uses rolling support/resistance levels from the signal bar.
    """
    if slice_df is None or len(slice_df) == 0:
        return float(entry_price)
    last = slice_df.iloc[-1]
    support = float(last['support']) if pd.notna(last.get('support')) else float(entry_price)
    resistance = float(last['resistance']) if pd.notna(last.get('resistance')) else float(entry_price)

    if direction in ('buy', 'long'):
        base_level = support if strategy_type == "range" else min(float(entry_price), support * 1.003)
        return float(base_level * (1 + LIMIT_ENTRY_OFFSET_PCT))
    base_level = resistance if strategy_type == "range" else max(float(entry_price), resistance * 0.997)
    return float(base_level * (1 - LIMIT_ENTRY_OFFSET_PCT))


def _resolve_backtest_entry(df, signal_idx, direction, strategy_type):
    """
    Return (fill_idx, fill_price) for a limit-idea entry fill.
    Limit is considered filled when touched within BACKTEST_LIMIT_FILL_BARS.
    """
    signal_price = float(df['close'].iat[signal_idx])
    slice_df = df.iloc[:signal_idx + 1]
    limit_price = _suggest_limit_entry(slice_df, direction, strategy_type, signal_price)
    max_fill_idx = min(len(df) - 1, signal_idx + max(1, BACKTEST_LIMIT_FILL_BARS))
    is_long = direction in ('buy', 'long')

    for j in range(signal_idx + 1, max_fill_idx + 1):
        high = float(df['high'].iat[j])
        low = float(df['low'].iat[j])
        if is_long and low <= limit_price:
            return j, limit_price
        if not is_long and high >= limit_price:
            return j, limit_price

    return None, None


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
        'rr_ratio': round((avg_win / abs(avg_loss)), 2) if avg_loss < 0 else 0.0,
        'equity_curve': [round(e, 4) for e in equity],
    }


def _get_backtest_pairs(pairs_override=None):
    """
    Resolve pair list:
    override → BACKTEST_PAIRS → BACKTEST_AUTO_TOP_PAIRS → CRYPTO_PAIRS → defaults.
    """
    if pairs_override:
        return [(s, None, None) if isinstance(s, str) else s for s in pairs_override]
    configured_bt = [p.strip() for p in (BACKTEST_PAIRS or []) if isinstance(p, str) and p.strip()]
    if configured_bt:
        return [(s, None, None) for s in configured_bt]
    if BACKTEST_AUTO_TOP_PAIRS:
        try:
            auto = get_auto_backtest_pairs(_get_exchange())
            if auto:
                return auto
            log_event(
                "BACKTEST_AUTO_TOP_PAIRS=true but discovery returned 0 pairs — "
                "check EXCHANGE in config.py, or lower BACKTEST_MIN_QUOTE_VOLUME / "
                "set BACKTEST_COINGECKO_MIN_CAP=0. Falling back to CRYPTO_PAIRS / defaults."
            )
        except Exception as e:
            log_event(f"BACKTEST_AUTO_TOP_PAIRS failed: {e}")
    configured = [p.strip() for p in (CRYPTO_PAIRS or []) if isinstance(p, str) and p.strip()]
    if configured:
        return [(s, None, None) for s in configured]
    return [(s, None, None) for s in _default_backtest_pair_symbols()]


def _timeframe_step_ms(timeframe: str) -> int:
    """One candle length in ms for paging fetch_ohlcv."""
    m = {
        '1m': 60_000,
        '3m': 3 * 60_000,
        '5m': 5 * 60_000,
        '15m': 15 * 60_000,
        '30m': 30 * 60_000,
        '1h': 3_600_000,
        '4h': 4 * 3_600_000,
        '1d': 86_400_000,
    }
    return m.get(timeframe, 5 * 60_000)


def _approx_bars_per_calendar_day(timeframe: str) -> int:
    """~24h of crypto candles per day (used to size fetch depth from BACKTEST_DAYS)."""
    per_day = {
        '1m': 1440,
        '3m': 480,
        '5m': 288,
        '15m': 96,
        '30m': 48,
        '1h': 24,
        '4h': 6,
        '1d': 1,
    }
    return per_day.get(timeframe, 288)


def _backtest_ohlcv_limit() -> int:
    """Larger pages = far fewer HTTP round-trips (Phemex/CCXT often allows up to 1000–2000)."""
    return max(200, min(int(BACKTEST_OHLCV_LIMIT), 2000))


def _backtest_fetch_sleep_sec() -> float:
    return float(BACKTEST_FETCH_SLEEP_SEC) if config.IS_BACKTESTING else 0.3


def fetch_data(pair, timeframe='5m', days=BACKTEST_DAYS):
    all_ohlcv = []
    now = datetime.now()
    since = int((now - timedelta(days=days)).timestamp() * 1000)

    limit = _backtest_ohlcv_limit()
    step_ms = _timeframe_step_ms(timeframe)
    sleep_sec = _backtest_fetch_sleep_sec()
    d = max(1, int(days))
    target_bars = max(800, _approx_bars_per_calendar_day(timeframe) * d)
    eff = max(150, limit - 5)
    max_loops = min(800, max(30, target_bars // eff + 25))

    loops = 0
    while loops < max_loops:
        ohlcv = _get_exchange().fetch_ohlcv(pair, timeframe=timeframe, since=since, limit=limit)

        if not ohlcv:
            break

        all_ohlcv.extend(ohlcv)

        last_timestamp = ohlcv[-1][0]
        since = last_timestamp + step_ms
        loops += 1

        time.sleep(sleep_sec)

        if len(all_ohlcv) >= target_bars:
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
    df = closed_bars_only(df, timeframe)
    if df is None or len(df) == 0:
        return pd.DataFrame()
    return prepare_ltf_frame(df)


def fetch_higher_timeframe_data(pair, timeframe='15m', days=BACKTEST_DAYS):
    all_ohlcv = []
    now = datetime.now()
    since = int((now - timedelta(days=days)).timestamp() * 1000)

    limit = _backtest_ohlcv_limit()
    step_ms = _timeframe_step_ms(timeframe)
    sleep_sec = _backtest_fetch_sleep_sec()
    d = max(1, int(days))
    target_bars = max(300, _approx_bars_per_calendar_day(timeframe) * d)
    eff = max(150, limit - 5)
    max_loops = min(800, max(25, target_bars // eff + 20))

    loops = 0
    while loops < max_loops:
        ohlcv = _get_exchange().fetch_ohlcv(pair, timeframe=timeframe, since=since, limit=limit)
        if not ohlcv:
            break
        all_ohlcv.extend(ohlcv)
        last_timestamp = ohlcv[-1][0]
        since = last_timestamp + step_ms
        loops += 1
        time.sleep(sleep_sec)
        if len(all_ohlcv) >= target_bars:
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
    df = closed_bars_only(df, timeframe)
    if df is None or len(df) == 0:
        return pd.DataFrame()
    return prepare_htf_frame(df)

def check_trade_outcome(df, start_idx, direction, entry_price,
                        max_lookahead=BACKTEST_LOOKAHEAD, strategy="trend"):
    """Resolve a trade against TP/SL levels. Returns dict with result and P&L.

    TP/SL come from the same levels_for_signal path as live (no slippage on levels).
    Slippage/fees only affect the fill used for P&L accounting.
    """
    if 'ATR' not in df.columns:
        df = add_atr_column(df, period=7)

    # Signal levels = live alert levels (shared calculator, raw entry).
    levels = levels_for_signal(entry_price, direction, df, start_idx, strategy)
    tp, sl = levels['take_profit'], levels['stop_loss']

    apply_fees = BACKTEST_APPLY_FEES
    fill = entry_price
    if apply_fees:
        fill = _apply_slippage(entry_price, direction)
        commission = _commission_cost(fill) * 2
    else:
        commission = 0.0

    return resolve_outcome_on_df(
        df,
        start_idx,
        direction,
        fill,
        tp,
        sl,
        max_lookahead=max_lookahead,
        skip_entry_bar=True,
        commission=commission,
        same_bar="conservative_sl",
    )


def _get_signal_at_bar(
    slice_df,
    htf_slice,
    entry_price,
    *,
    include_limit_idea_fallback=None,
):
    """Shared evaluate_signal_at_bar — returns SignalDecision or None."""
    if include_limit_idea_fallback is None:
        include_limit_idea_fallback = bool(ENABLE_LIMIT_IDEA_FALLBACK)
    return evaluate_signal_at_bar(
        slice_df,
        htf_slice,
        entry_price,
        include_limit_idea_fallback=include_limit_idea_fallback,
        include_breakout=False,
    )


def simulate_combined_strategy(pair, df_5m, df_1h):
    long_wins = long_losses = long_none = 0
    short_wins = short_losses = short_none = 0
    strategy_used = []
    pnl_list = []
    cooldown = _cooldown_bars()
    last_trade_bar = -cooldown

    # ATR already attached by prepare_ltf_frame; keep idempotent.
    if 'ATR' not in df_5m.columns:
        df_5m = add_atr_column(df_5m, period=7)

    # O(n) align LTF bars to HTF window ends — avoids filtering the whole HTF df every bar.
    htf_end_idx = df_1h['timestamp'].searchsorted(df_5m['timestamp'], side='right') - 1

    # Signal helpers only need recent rows + precomputed indicators on full df (fixed window).
    _slice_lookback = max(120, SR_LOOKBACK_BARS + 20)

    for i in range(max(60, SR_LOOKBACK_BARS), len(df_5m) - 10):
        if (i - last_trade_bar) < cooldown:
            continue

        sl_start = max(0, i - _slice_lookback)
        slice_df = df_5m.iloc[sl_start : i + 1]
        if len(slice_df) < 51:
            continue

        entry_price = float(df_5m['close'].iat[i])

        ei = int(htf_end_idx[i])
        htf_slice = htf_slice_for_bar(df_1h, ei)
        if htf_slice is None:
            continue

        decision = _get_signal_at_bar(
            slice_df,
            htf_slice,
            entry_price,
            include_limit_idea_fallback=_BACKTEST_PER_PAIR_LIMIT_FALLBACK,
        )
        if decision is None:
            continue
        direction, strat = decision.side, decision.strategy_type

        # Always execute the normal signal entry (existing backtest behavior).
        last_trade_bar = i
        outcome = check_trade_outcome(df_5m, i, direction, entry_price, BACKTEST_LOOKAHEAD, strat)
        result = outcome['result']
        strategy_used.append('ma' if strat in ('trend', 'breakout') else 'range')

        is_long = direction == 'buy'
        if result == 'win':
            pnl_list.append(outcome['pnl_pct'])
            if is_long:
                long_wins += 1
            else:
                short_wins += 1
        elif result == 'loss':
            pnl_list.append(outcome['pnl_pct'])
            if is_long:
                long_losses += 1
            else:
                short_losses += 1
        else:
            if is_long:
                long_none += 1
            else:
                short_none += 1

        # Optional: execute limit-idea entry alongside normal signal entry.
        if BACKTEST_USE_LIMIT_IDEAS:
            fill_idx, filled_entry_price = _resolve_backtest_entry(df_5m, i, direction, strat)
            if fill_idx is not None:
                limit_outcome = check_trade_outcome(
                    df_5m, fill_idx, direction, filled_entry_price, BACKTEST_LOOKAHEAD, strat
                )
                limit_result = limit_outcome['result']
                strategy_used.append('ma' if strat in ('trend', 'breakout') else 'range')

                if limit_result == 'win':
                    pnl_list.append(limit_outcome['pnl_pct'])
                    if is_long:
                        long_wins += 1
                    else:
                        short_wins += 1
                elif limit_result == 'loss':
                    pnl_list.append(limit_outcome['pnl_pct'])
                    if is_long:
                        long_losses += 1
                    else:
                        short_losses += 1
                else:
                    if is_long:
                        long_none += 1
                    else:
                        short_none += 1

    resolved = long_wins + long_losses + short_wins + short_losses
    total_trades = resolved
    total_wins = long_wins + short_wins
    win_rate = round(total_wins / total_trades * 100, 2) if total_trades > 0 else 0
    range_used = strategy_used.count('range')
    ma_used = strategy_used.count('ma')

    risk_metrics = _compute_risk_metrics(pnl_list)

    _bt_log(f"\n--- Results for {pair} ---", verbose=True)
    _bt_log(f"Resolved trades: {total_trades} (unresolved timeouts: {long_none + short_none})", verbose=True)
    _bt_log(f"Wins: {total_wins} (Long: {long_wins}, Short: {short_wins})", verbose=True)
    _bt_log(f"Losses: {long_losses + short_losses} (Long: {long_losses}, Short: {short_losses})", verbose=True)
    _bt_log(f"Win Rate: {win_rate}%", verbose=True)
    _bt_log(f"MA Usage: {ma_used}, Range Usage: {range_used}", verbose=True)
    _bt_log(f"Sharpe: {risk_metrics['sharpe']} | Max DD: {risk_metrics['max_drawdown_pct']}% | PF: {risk_metrics['profit_factor']}", verbose=True)
    _bt_log(f"Avg Win: {risk_metrics['avg_win_pct']}% | Avg Loss: {risk_metrics['avg_loss_pct']}%", verbose=True)

    result = {
        'win_rate': win_rate,
        'total_trades': total_trades,
        'unresolved': long_none + short_none,
        'ma_used': ma_used,
        'range_used': range_used,
    }
    result.update(risk_metrics)
    return result


def run_backtest(pairs_override=None):
    """Run backtest on pairs. Only pairs with win_rate >= threshold (default 50%) are kept. No fallback."""
    prev_flag = config.IS_BACKTESTING
    config.IS_BACKTESTING = True
    try:
        pairs = _get_backtest_pairs(pairs_override)
        win_rate_threshold = float(BACKTEST_WIN_RATE_THRESHOLD)
        enforce_rr = BACKTEST_ENFORCE_RR
        min_rr_ratio = float(BACKTEST_MIN_RR_RATIO) if enforce_rr else 0.0
        min_trades = max(2, int(BACKTEST_MIN_TRADES))  # require enough resolved trades so flukes don't qualify

        good_pairs = []
        results_by_symbol = {}

        _bt_log(f"Backtesting {len(pairs)} pairs...", verbose=False)
        for idx, pair in enumerate(pairs):
            symbol = pair[0] if isinstance(pair, (list, tuple)) else pair
            _bt_log(f"[{idx + 1}/{len(pairs)}] Backtesting {symbol}", verbose=False)
            try:
                df = fetch_data(symbol, TIMEFRAME, days=BACKTEST_DAYS)
                df_htf = fetch_higher_timeframe_data(symbol, HTF_TIMEFRAME, days=BACKTEST_DAYS)
                if len(df) > 300:
                    result = simulate_combined_strategy(pair, df, df_htf)
                    result_save = {k: v for k, v in result.items() if k != 'equity_curve'}
                    results_by_symbol[symbol] = result_save
                    _bt_log(f"Result: {result_save}", verbose=True)
                    total_trades = result.get('total_trades', 0)
                    rr_ratio = float(result.get('rr_ratio', 0.0))
                    if total_trades >= min_trades and result['win_rate'] >= win_rate_threshold and rr_ratio >= min_rr_ratio:
                        good_pairs.append(symbol)
            except Exception as e:
                _bt_log(f"❌ Error backtesting {symbol}: {e}", verbose=False)

        state = {
            "pairs": good_pairs,
            "run_at": datetime.now(timezone.utc).isoformat(),
            "win_rate_threshold": win_rate_threshold,
            "signal_config": signal_config_snapshot(),
            "levels_config": {"strategy_settings": signal_config_snapshot()["strategy_settings"]},
            "timeframe": TIMEFRAME,
            "htf_timeframe": HTF_TIMEFRAME,
            "results": results_by_symbol,
        }
        try:
            path = os.path.abspath(BACKTEST_STATE_FILE)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w") as f:
                json.dump(state, f, indent=2)
            _bt_log(f"Backtest complete: {len(good_pairs)} good pairs (threshold {win_rate_threshold}%, min trades {min_trades}, min RR {min_rr_ratio}).", verbose=False)
            _bt_log(f"Wrote backtest state to {path}", verbose=False)
        except Exception as e:
            _bt_log(f"Failed to write last_backtest.json: {e}", verbose=False)

        return good_pairs
    finally:
        config.IS_BACKTESTING = prev_flag


def run_portfolio_backtest(pairs_override=None, max_trades_per_bar=None):
    """
    Backtest the same way you trade live: at each bar, collect signals across all pairs,
    rank like live (SIG>LIM, trend>breakout>range, then WR), cap at MAX_SIGNALS_PER_CYCLE.
    """
    if max_trades_per_bar is None:
        max_trades_per_bar = int(MAX_SIGNALS_PER_CYCLE) if int(MAX_SIGNALS_PER_CYCLE) > 0 else 5
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
            df_ltf = fetch_data(sym, TIMEFRAME, days=BACKTEST_DAYS)
            df_htf = fetch_higher_timeframe_data(sym, HTF_TIMEFRAME, days=BACKTEST_DAYS)
            if len(df_ltf) > 300 and len(df_htf) > 50:
                if 'ATR' not in df_ltf.columns:
                    df_ltf = add_atr_column(df_ltf, period=7)
                data_by_symbol[sym] = (df_ltf, df_htf)
        except Exception as e:
            log_event(f"Portfolio backtest: skip {sym}: {e}")

    if not data_by_symbol:
        log_event("Portfolio backtest: no data for any pair.")
        return 0.0

    htf_end_by_sym = {
        sym: df_htf['timestamp'].searchsorted(df_ltf['timestamp'], side='right') - 1
        for sym, (df_ltf, df_htf) in data_by_symbol.items()
    }
    _slice_lookback = max(120, SR_LOOKBACK_BARS + 20)
    cooldown = _cooldown_bars()

    min_len = min(len(data_by_symbol[s][0]) for s in data_by_symbol) - 10
    if min_len < 70:
        log_event("Portfolio backtest: insufficient common bars.")
        return 0.0

    pnl_list = []
    last_trade_bar_by_sym = {s: -cooldown for s in data_by_symbol}

    for i in range(60, min_len):
        signals_at_bar = []
        for symbol, (df_ltf, df_htf) in data_by_symbol.items():
            if (i - last_trade_bar_by_sym[symbol]) < cooldown:
                continue
            sl_start = max(0, i - _slice_lookback)
            slice_df = df_ltf.iloc[sl_start : i + 1]
            if len(slice_df) < 51:
                continue
            ei = int(htf_end_by_sym[symbol][i])
            htf_slice = htf_slice_for_bar(df_htf, ei)
            if htf_slice is None:
                continue
            entry_price = float(df_ltf['close'].iat[i])
            decision = _get_signal_at_bar(
                slice_df,
                htf_slice,
                entry_price,
                include_limit_idea_fallback=ENABLE_LIMIT_IDEA_FALLBACK,
            )
            if decision is not None:
                win_rate = 0.0
                if isinstance(results_by_symbol.get(symbol), dict):
                    win_rate = float(results_by_symbol[symbol].get('win_rate', 0))
                signals_at_bar.append(
                    (symbol, i, decision, win_rate, rank_signal_key(
                        decision.signal_source, decision.strategy_type, win_rate
                    ))
                )

        signals_at_bar.sort(key=lambda x: x[4], reverse=True)
        for t in signals_at_bar[:max_trades_per_bar]:
            symbol, idx, decision, _, _ = t
            direction = decision.side
            strategy_type = decision.strategy_type
            df_ltf = data_by_symbol[symbol][0]
            signal_entry_price = float(df_ltf['close'].iat[idx])
            outcome = check_trade_outcome(
                df_ltf, idx, direction, signal_entry_price, BACKTEST_LOOKAHEAD, strategy_type
            )
            if outcome['result'] == 'none':
                last_trade_bar_by_sym[symbol] = idx
                continue
            pnl_list.append(outcome['pnl_pct'])
            last_trade_bar_by_sym[symbol] = idx

            if BACKTEST_USE_LIMIT_IDEAS:
                fill_idx, filled_entry_price = _resolve_backtest_entry(df_ltf, idx, direction, strategy_type)
                if fill_idx is not None:
                    limit_outcome = check_trade_outcome(
                        df_ltf, fill_idx, direction, filled_entry_price, BACKTEST_LOOKAHEAD, strategy_type
                    )
                    if limit_outcome['result'] != 'none':
                        pnl_list.append(limit_outcome['pnl_pct'])

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
    config.IS_BACKTESTING = True
    log_event(f"Backtest OHLCV depth: BACKTEST_DAYS={BACKTEST_DAYS} (from config / project .env)")
    results = run_backtest()
    print("Backtest completed, good pairs:", results)
    if results:
        run_portfolio_backtest(pairs_override=results)
