import sys
import os
import json
import math
from datetime import datetime, timedelta, timezone

import pandas as pd
import pandas_ta as ta
import time

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../')))

# Mark this process as backtesting so shared helpers can suppress noisy prints.
os.environ.setdefault("BACKTESTING", "true")

from config import (
    BACKTEST_SLIPPAGE_BPS, BACKTEST_COMMISSION_BPS,
    BACKTEST_COOLDOWN_BARS, BACKTEST_LOOKAHEAD, BACKTEST_DAYS,
    MIN_ADX_TREND, LIMIT_ENTRY_OFFSET_PCT, LIMIT_IDEA_FALLBACK_PCT,
    BACKTEST_USE_LIMIT_IDEAS, BACKTEST_LIMIT_FILL_BARS, BACKTEST_MIN_RR_RATIO,
    CRYPTO_PAIRS,
)
from utils.utils import (
    check_long_signal,
    check_short_signal,
    calculate_trade_levels,
    add_atr_column,
    check_range_trade,
    is_ranging,
    log_event,
    calculate_mas,
)
from utils.exchangeUtils import get_exchange, get_auto_backtest_pairs

BACKTEST_STATE_FILE = os.path.join(os.path.dirname(__file__), '..', 'last_backtest.json')
BACKTEST_VERBOSE = os.getenv("BACKTEST_VERBOSE", "false").strip().lower() in ("1", "true", "yes", "y", "on")
# Per-pair win-rate screening: false = trend + range trades only (legacy; higher pass rate).
# true = include limit-idea proximity signals (matches live bot + portfolio backtest).
_BACKTEST_PER_PAIR_LIMIT_FALLBACK = os.getenv(
    "BACKTEST_PER_PAIR_LIMIT_FALLBACK", "false"
).strip().lower() in ("1", "true", "yes", "y", "on")
# Fallback universes when CRYPTO_PAIRS / BACKTEST_PAIRS / auto-discovery are unset.
DEFAULT_BACKTEST_PAIRS_PHEMEX = [
    'BTC/USDT:USDT', 'ETH/USDT:USDT', 'XRP/USDT:USDT', 'SOL/USDT:USDT',
    'DOGE/USDT:USDT', 'ADA/USDT:USDT', 'LINK/USDT:USDT', 'AVAX/USDT:USDT',
    'LTC/USDT:USDT', 'UNI/USDT:USDT', 'DOT/USDT:USDT', 'ATOM/USDT:USDT',
]
DEFAULT_BACKTEST_PAIRS_BINANCE = [
    'BTC/USDT', 'ETH/USDT', 'XRP/USDT', 'SOL/USDT',
    'DOGE/USDT', 'ADA/USDT', 'LINK/USDT', 'AVAX/USDT',
    'LTC/USDT', 'UNI/USDT', 'DOT/USDT', 'ATOM/USDT',
]


def _default_backtest_pair_symbols():
    if os.getenv("EXCHANGE", "phemex").strip().lower() == "binance_margin":
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
    override → BACKTEST_PAIRS → BACKTEST_AUTO_TOP_PAIRS (exchange + optional CoinGecko) →
    CRYPTO_PAIRS → defaults (symbol shape matches EXCHANGE: phemex vs binance_margin).
    """
    if pairs_override:
        return [(s, None, None) if isinstance(s, str) else s for s in pairs_override]
    env_pairs = os.getenv("BACKTEST_PAIRS", "").strip().split(",")
    env_pairs = [p.strip() for p in env_pairs if p.strip()]
    if env_pairs:
        return [(s, None, None) for s in env_pairs]
    if os.getenv("BACKTEST_AUTO_TOP_PAIRS", "false").strip().lower() in ("1", "true", "yes", "y", "on"):
        try:
            auto = get_auto_backtest_pairs(_get_exchange())
            if auto:
                return auto
            log_event(
                "BACKTEST_AUTO_TOP_PAIRS=true but discovery returned 0 pairs — "
                "check EXCHANGE (phemex / binance_margin / kucoin_futures), API keys if required, "
                "or lower BACKTEST_MIN_QUOTE_VOLUME / set BACKTEST_COINGECKO_MIN_CAP=0. "
                "Falling back to CRYPTO_PAIRS / defaults."
            )
        except Exception as e:
            log_event(f"BACKTEST_AUTO_TOP_PAIRS failed: {e}")
    configured = [p.strip() for p in (CRYPTO_PAIRS or []) if p.strip()]
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
    try:
        raw = int(os.getenv("BACKTEST_OHLCV_LIMIT", "1000"))
    except ValueError:
        raw = 1000
    return max(200, min(raw, 2000))


def _backtest_fetch_sleep_sec() -> float:
    if os.getenv("BACKTESTING", "").strip().lower() in ("1", "true", "yes", "y", "on"):
        return float(os.getenv("BACKTEST_FETCH_SLEEP_SEC", "0.05"))
    return 0.3


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

    # Match live bot: SMAIndicator (utils.calculate_mas), not plain rolling — avoids signal drift.
    df = calculate_mas(df)
    df['rsi'] = df.ta.rsi(length=14)
    df['adx'] = df.ta.adx(length=14)['ADX_14']
    df['support'] = df['low'].rolling(window=50).min()
    df['resistance'] = df['high'].rolling(window=50).max()

    return df


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
    df = calculate_mas(df)
    return df


def check_trade_outcome(df, start_idx, direction, entry_price,
                        max_lookahead=BACKTEST_LOOKAHEAD, strategy="trend"):
    """Resolve a trade against TP/SL levels. Returns dict with result and P&L.

    Expects df to already have an 'ATR' column (precomputed).
    """
    if 'ATR' not in df.columns:
        df = add_atr_column(df, period=7)

    apply_fees = os.getenv("BACKTEST_APPLY_FEES", "true").strip().lower() in ("1", "true", "yes", "y", "on")
    if apply_fees:
        entry_price = _apply_slippage(entry_price, direction)
        commission = _commission_cost(entry_price) * 2
    else:
        commission = 0.0

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


def _get_signal_at_bar(
    slice_df,
    htf_slice,
    entry_price,
    *,
    include_limit_idea_fallback=True,
):
    """Same signal logic as live at one bar. Returns ('buy'|'sell', 'trend'|'range') or None.

    When include_limit_idea_fallback is False, skips the proximity-based LIM paths (matches older
    per-pair screening). Live bot and portfolio backtest use True.
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

    if not include_limit_idea_fallback:
        return None

    # Fallback: if no normal signal, use limit-idea proximity in ranging conditions (live: _limit_idea_fallback_signal).
    if not trend_up and not trend_down and is_ranging(slice_df) and len(slice_df) > 0:
        last = slice_df.iloc[-1]
        close = float(last['close'])
        support = float(last['support']) if pd.notna(last.get('support')) else close
        resistance = float(last['resistance']) if pd.notna(last.get('resistance')) else close
        near_support = close <= support * (1 + LIMIT_IDEA_FALLBACK_PCT)
        near_resistance = close >= resistance * (1 - LIMIT_IDEA_FALLBACK_PCT)
        if near_support:
            return ('buy', 'range')
        if near_resistance:
            return ('sell', 'range')
    return None


def simulate_combined_strategy(pair, df_5m, df_1h):
    long_wins = long_losses = long_none = 0
    short_wins = short_losses = short_none = 0
    strategy_used = []
    pnl_list = []
    last_trade_bar = -BACKTEST_COOLDOWN_BARS

    df_5m = add_atr_column(df_5m, period=7)

    # O(n) align 5m bars to 15m window ends — avoids filtering the whole HTF df every bar.
    htf_end_idx = df_1h['timestamp'].searchsorted(df_5m['timestamp'], side='right') - 1

    # Signal helpers only need recent rows + precomputed indicators on full df (fixed window).
    _slice_lookback = 80

    for i in range(60, len(df_5m) - 10):
        if (i - last_trade_bar) < BACKTEST_COOLDOWN_BARS:
            continue

        sl_start = max(0, i - _slice_lookback)
        slice_df = df_5m.iloc[sl_start : i + 1]
        if len(slice_df) < 51:
            continue

        entry_price = float(df_5m['close'].iat[i])

        ei = int(htf_end_idx[i])
        if ei < 5:
            continue
        htf_slice = df_1h.iloc[ei - 5 : ei + 1]

        if len(htf_slice) < 6:
            continue

        sig = _get_signal_at_bar(
            slice_df,
            htf_slice,
            entry_price,
            include_limit_idea_fallback=_BACKTEST_PER_PAIR_LIMIT_FALLBACK,
        )
        if sig is None:
            continue
        direction, strat = sig

        # Always execute the normal signal entry (existing backtest behavior).
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

        # Optional: execute limit-idea entry alongside normal signal entry.
        if BACKTEST_USE_LIMIT_IDEAS:
            fill_idx, filled_entry_price = _resolve_backtest_entry(df_5m, i, direction, strat)
            if fill_idx is not None:
                limit_outcome = check_trade_outcome(
                    df_5m, fill_idx, direction, filled_entry_price, BACKTEST_LOOKAHEAD, strat
                )
                limit_result = limit_outcome['result']
                pnl_list.append(limit_outcome['pnl_pct'])
                strategy_used.append('ma' if strat == 'trend' else 'range')

                if limit_result == 'win':
                    if is_long:
                        long_wins += 1
                    else:
                        short_wins += 1
                elif limit_result == 'loss':
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

    _bt_log(f"\n--- Results for {pair} ---", verbose=True)
    _bt_log(f"Total Trades: {total_trades}", verbose=True)
    _bt_log(f"Wins: {total_wins} (Long: {long_wins}, Short: {short_wins})", verbose=True)
    _bt_log(f"Losses: {long_losses + short_losses} (Long: {long_losses}, Short: {short_losses})", verbose=True)
    _bt_log(f"Win Rate: {win_rate}%", verbose=True)
    _bt_log(f"MA Usage: {ma_used}, Range Usage: {range_used}", verbose=True)
    _bt_log(f"Sharpe: {risk_metrics['sharpe']} | Max DD: {risk_metrics['max_drawdown_pct']}% | PF: {risk_metrics['profit_factor']}", verbose=True)
    _bt_log(f"Avg Win: {risk_metrics['avg_win_pct']}% | Avg Loss: {risk_metrics['avg_loss_pct']}%", verbose=True)

    result = {
        'win_rate': win_rate,
        'total_trades': total_trades,
        'ma_used': ma_used,
        'range_used': range_used,
    }
    result.update(risk_metrics)
    return result


def run_backtest(pairs_override=None):
    """Run backtest on pairs. Only pairs with win_rate >= threshold (default 50%) are kept. No fallback."""
    pairs = _get_backtest_pairs(pairs_override)
    win_rate_threshold = float(os.getenv("BACKTEST_WIN_RATE_THRESHOLD", "50"))
    enforce_rr = os.getenv("BACKTEST_ENFORCE_RR", "false").strip().lower() in ("1", "true", "yes", "y", "on")
    min_rr_ratio = float(BACKTEST_MIN_RR_RATIO) if enforce_rr else 0.0
    min_trades = 3  # require at least 3 trades so 1-trade flukes don't qualify

    good_pairs = []
    results_by_symbol = {}

    _bt_log(f"Backtesting {len(pairs)} pairs...", verbose=False)
    for idx, pair in enumerate(pairs):
        symbol = pair[0] if isinstance(pair, (list, tuple)) else pair
        _bt_log(f"[{idx + 1}/{len(pairs)}] Backtesting {symbol}", verbose=False)
        try:
            df = fetch_data(symbol, '5m', days=BACKTEST_DAYS)
            df_1h = fetch_higher_timeframe_data(symbol, '15m', days=BACKTEST_DAYS)
            if len(df) > 300:
                result = simulate_combined_strategy(pair, df, df_1h)
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

    htf_end_by_sym = {
        sym: df_15m['timestamp'].searchsorted(df_5m['timestamp'], side='right') - 1
        for sym, (df_5m, df_15m) in data_by_symbol.items()
    }
    _slice_lookback = 80

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
            sl_start = max(0, i - _slice_lookback)
            slice_df = df_5m.iloc[sl_start : i + 1]
            if len(slice_df) < 51:
                continue
            ei = int(htf_end_by_sym[symbol][i])
            if ei < 5:
                continue
            htf_slice = df_15m.iloc[ei - 5 : ei + 1]
            if len(htf_slice) < 6:
                continue
            entry_price = float(df_5m['close'].iat[i])
            sig = _get_signal_at_bar(
                slice_df, htf_slice, entry_price, include_limit_idea_fallback=True
            )
            if sig is not None:
                direction, strategy_type = sig
                win_rate = 0.0
                if isinstance(results_by_symbol.get(symbol), dict):
                    win_rate = float(results_by_symbol[symbol].get('win_rate', 0))
                signals_at_bar.append((symbol, i, direction, strategy_type, win_rate))

        signals_at_bar.sort(key=lambda x: x[4], reverse=True)
        for t in signals_at_bar[:max_trades_per_bar]:
            symbol, idx, direction, strategy_type, _ = t
            df_5m = data_by_symbol[symbol][0]
            signal_entry_price = float(df_5m['close'].iat[idx])
            outcome = check_trade_outcome(
                df_5m, idx, direction, signal_entry_price, BACKTEST_LOOKAHEAD, strategy_type
            )
            pnl_list.append(outcome['pnl_pct'])
            last_trade_bar_by_sym[symbol] = idx

            if BACKTEST_USE_LIMIT_IDEAS:
                fill_idx, filled_entry_price = _resolve_backtest_entry(df_5m, idx, direction, strategy_type)
                if fill_idx is not None:
                    limit_outcome = check_trade_outcome(
                        df_5m, fill_idx, direction, filled_entry_price, BACKTEST_LOOKAHEAD, strategy_type
                    )
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
    log_event(f"Backtest OHLCV depth: BACKTEST_DAYS={BACKTEST_DAYS} (from config / project .env)")
    results = run_backtest()
    print("Backtest completed, good pairs:", results)
    if results:
        run_portfolio_backtest(pairs_override=results, max_trades_per_bar=3)
