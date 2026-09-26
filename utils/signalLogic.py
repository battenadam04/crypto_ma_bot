"""Shared live + backtest signal decision and first-touch outcome logic.

Both `bot.process_pair` and `strategies.simulate_trades` must call these helpers
so scan path, LIM/breakout gates, frame prep, cooldown, ranking, and same-bar
TP/SL policy cannot drift.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Iterable, Literal, Optional, Tuple

import pandas as pd

import config
from utils.utils import (
    add_atr_column,
    calculate_mas,
    calculate_trade_levels,
    check_breakout_signal,
    check_long_signal,
    check_range_trade,
    check_short_signal,
    is_ranging,
    _strong_bearish_close,
    _strong_bullish_close,
)

Direction = Literal["long", "short"]
Side = Literal["buy", "sell"]
StrategyType = Literal["trend", "range", "breakout", "scalp"]
SignalSource = Literal["SIG", "LIM"]
SameBarPolicy = Literal["conservative_sl"]  # sole supported policy — live + backtest


@dataclass(frozen=True)
class TrendFlags:
    trend_up: bool
    trend_down: bool


@dataclass(frozen=True)
class SignalDecision:
    """Canonical signal at one bar (live and backtest)."""

    direction: Direction
    strategy_type: StrategyType
    signal_source: SignalSource

    @property
    def side(self) -> Side:
        return "buy" if self.direction == "long" else "sell"


def direction_to_side(direction: str) -> Side:
    d = (direction or "").lower()
    if d in ("long", "buy"):
        return "buy"
    return "sell"


def side_to_direction(side: str) -> Direction:
    s = (side or "").lower()
    if s in ("long", "buy"):
        return "long"
    return "short"


def timeframe_to_seconds(timeframe: str) -> int:
    tf = (timeframe or "15m").strip().lower()
    unit = tf[-1]
    try:
        n = int(tf[:-1])
    except ValueError:
        return 15 * 60
    if unit == "m":
        return n * 60
    if unit == "h":
        return n * 3600
    if unit == "d":
        return n * 86400
    return 15 * 60


def closed_bars_only(
    df: Optional[pd.DataFrame],
    timeframe: str,
    *,
    now: Optional[pd.Timestamp] = None,
) -> Optional[pd.DataFrame]:
    """
    Drop a still-forming candle so live matches backtest (closed bars only).

    ccxt timestamps are candle *open* times; a bar is closed when now >= open + tf.
    """
    if df is None or len(df) == 0:
        return df
    if "timestamp" not in df.columns:
        return df
    ts_now = now if now is not None else pd.Timestamp.now(tz="UTC")
    if ts_now.tzinfo is None:
        ts_now = ts_now.tz_localize("UTC")
    last_ts = df["timestamp"].iloc[-1]
    last_ts = pd.Timestamp(last_ts)
    if last_ts.tzinfo is None:
        last_ts = last_ts.tz_localize("UTC")
    else:
        last_ts = last_ts.tz_convert("UTC")
    period = pd.Timedelta(seconds=timeframe_to_seconds(timeframe))
    if ts_now < last_ts + period:
        return df.iloc[:-1].copy()
    return df


def prepare_ltf_frame(df: pd.DataFrame) -> pd.DataFrame:
    """Attach MAs / RSI / ADX / S/R / ATR — identical for live and backtest."""
    lookback = int(getattr(config, "SR_LOOKBACK_BARS", 80) or 80)
    out = calculate_mas(df)
    # Prefer pandas_ta (same as live bot); fall back to `ta` package.
    try:
        out["rsi"] = out.ta.rsi(length=14)
        out["adx"] = out.ta.adx(length=14)["ADX_14"]
    except Exception:
        from ta.momentum import RSIIndicator
        from ta.trend import ADXIndicator

        out["rsi"] = RSIIndicator(out["close"], window=14).rsi()
        out["adx"] = ADXIndicator(out["high"], out["low"], out["close"], window=14).adx()
    out["support"] = out["low"].rolling(window=lookback).min()
    out["resistance"] = out["high"].rolling(window=lookback).max()
    out = add_atr_column(out, period=7)
    return out


def prepare_htf_frame(df: pd.DataFrame) -> pd.DataFrame:
    """HTF frame only needs MAs for trend flags."""
    return calculate_mas(df)


def htf_slice_for_bar(htf_df: pd.DataFrame, end_idx: int) -> Optional[pd.DataFrame]:
    """Last 6 HTF bars ending at end_idx (inclusive) — shared live/backtest window."""
    if htf_df is None or len(htf_df) < 6 or end_idx < 5:
        return None
    return htf_df.iloc[end_idx - 5 : end_idx + 1]


def signal_cooldown_bars(timeframe: Optional[str] = None) -> int:
    """Bars of silence after a signal — derived from live SIGNAL_COOLDOWN_SEC."""
    tf = timeframe or getattr(config, "TIMEFRAME", "15m")
    sec = int(getattr(config, "SIGNAL_COOLDOWN_SEC", 1800) or 1800)
    bar = max(1, timeframe_to_seconds(tf))
    return max(1, int(math.ceil(sec / bar)))


def rank_signal_key(
    signal_source: str,
    strategy_type: str,
    win_rate: float = 0.0,
) -> Tuple[int, int, float]:
    """Same ranking live uses: SIG>LIM, trend>breakout>scalp>range, then backtest WR."""
    source_rank = 1 if signal_source == "SIG" else 0
    st = strategy_type or ""
    if st == "trend":
        strategy_rank = 3
    elif st == "breakout":
        strategy_rank = 2
    elif st == "scalp":
        strategy_rank = 1
    else:
        strategy_rank = 0
    return (source_rank, strategy_rank, float(win_rate or 0.0))


def signal_config_snapshot() -> dict:
    """Full fingerprint of knobs that affect signal decisions + levels."""
    import copy
    from utils.configUtils import strategy_settings

    return {
        "strategy_settings": copy.deepcopy(strategy_settings),
        "TIMEFRAME": getattr(config, "TIMEFRAME", "15m"),
        "HTF_TIMEFRAME": getattr(config, "HTF_TIMEFRAME", "1h"),
        "MULTI_TF_ENABLED": bool(getattr(config, "MULTI_TF_ENABLED", False)),
        "MULTI_TF_EXTRA": list(getattr(config, "MULTI_TF_EXTRA", []) or []),
        "ENABLE_LIMIT_IDEA_FALLBACK": bool(
            getattr(config, "ENABLE_LIMIT_IDEA_FALLBACK", False)
        ),
        "MIN_ADX_TREND": float(getattr(config, "MIN_ADX_TREND", 0) or 0),
        "MIN_SETUP_RR": float(getattr(config, "MIN_SETUP_RR", 0) or 0),
        "CONTINUATION_PULLBACK_PCT": float(
            getattr(config, "CONTINUATION_PULLBACK_PCT", 0) or 0
        ),
        "ENABLE_COUNTER_HTF_SCALP": bool(
            getattr(config, "ENABLE_COUNTER_HTF_SCALP", True)
        ),
        "LOCATION_CLEAR_PCT": float(getattr(config, "LOCATION_CLEAR_PCT", 0.015) or 0),
        "LOCATION_CLEAR_PCT_STRICT": float(
            getattr(config, "LOCATION_CLEAR_PCT_STRICT", 0.02) or 0
        ),
        "SIGNAL_COOLDOWN_SEC": int(getattr(config, "SIGNAL_COOLDOWN_SEC", 0) or 0),
        "MAX_SIGNALS_PER_CYCLE": int(getattr(config, "MAX_SIGNALS_PER_CYCLE", 0) or 0),
        "SR_LOOKBACK_BARS": int(getattr(config, "SR_LOOKBACK_BARS", 0) or 0),
        "RSI_OVERSOLD": float(getattr(config, "RSI_OVERSOLD", 0) or 0),
        "RSI_OVERBOUGHT": float(getattr(config, "RSI_OVERBOUGHT", 0) or 0),
        "RANGE_ADX_THRESHOLD": float(getattr(config, "RANGE_ADX_THRESHOLD", 0) or 0),
        "RANGE_MAX_PCT": float(getattr(config, "RANGE_MAX_PCT", 0) or 0),
        "RANGE_TP_TARGET": str(getattr(config, "RANGE_TP_TARGET", "")),
        "BACKTEST_LOOKAHEAD": int(getattr(config, "BACKTEST_LOOKAHEAD", 0) or 0),
    }


def signal_config_matches(snapshot: Optional[dict]) -> bool:
    if not snapshot or not isinstance(snapshot, dict):
        return False
    return snapshot == signal_config_snapshot()


def htf_trend_flags(htf_slice: pd.DataFrame) -> Optional[TrendFlags]:
    """1h bias: ma20 vs ma50 only (no slope/extra lookback gates)."""
    if htf_slice is None or len(htf_slice) < 1:
        return None
    if "ma20" not in htf_slice.columns or "ma50" not in htf_slice.columns:
        return None
    ma20_last = htf_slice["ma20"].iloc[-1]
    ma50_last = htf_slice["ma50"].iloc[-1]
    if pd.isna(ma20_last) or pd.isna(ma50_last):
        return None
    trend_up = float(ma20_last) > float(ma50_last)
    trend_down = float(ma20_last) < float(ma50_last)
    return TrendFlags(trend_up=trend_up, trend_down=trend_down)


def levels_for_signal(
    entry_price: float,
    direction: str,
    df: pd.DataFrame,
    start_idx: int,
    strategy_type: str = "trend",
) -> dict:
    """
    Single TP/SL calculator for live alerts and backtest grading.

    Always uses `utils.configUtils.strategy_settings` via calculate_trade_levels.
    Do not apply slippage here — signal levels must match what we post live.
    """
    work = df
    if "ATR" not in work.columns:
        work = add_atr_column(work, period=7)
    side = direction_to_side(direction)
    return calculate_trade_levels(
        float(entry_price), side, work, int(start_idx), strategy_type
    )


def setup_meets_min_rr(
    slice_df: pd.DataFrame,
    entry_price: float,
    direction: str,
    strategy_type: str,
    *,
    min_rr: Optional[float] = None,
) -> bool:
    """Reject setups whose indicative TP/SL offer weak reward:risk. min_rr<=0 disables."""
    try:
        threshold = float(min_rr if min_rr is not None else config.MIN_SETUP_RR)
        if threshold <= 0:
            return True
        levels = levels_for_signal(
            entry_price, direction, slice_df, len(slice_df) - 1, strategy_type
        )
        return float(levels.get("rr_ratio") or 0) >= threshold
    except Exception:
        return False


def _adx_ok(slice_df: pd.DataFrame) -> bool:
    min_adx = float(getattr(config, "MIN_ADX_TREND", 0) or 0)
    if min_adx <= 0:
        return True
    if "adx" not in slice_df.columns:
        return False
    adx = slice_df["adx"].iloc[-1]
    return bool(pd.notna(adx) and float(adx) >= min_adx)


def _location_ok(slice_df: pd.DataFrame, direction: str, *, strict: bool = False) -> bool:
    """Confirm #3: price not pressing into the opposing structural S/R."""
    last = slice_df.iloc[-1]
    close = float(last["close"])
    if strict:
        buf = float(getattr(config, "LOCATION_CLEAR_PCT_STRICT", 0.02) or 0.02)
    else:
        buf = float(getattr(config, "LOCATION_CLEAR_PCT", 0.015) or 0.015)
    if direction in ("long", "buy"):
        res = last.get("resistance")
        if res is None or pd.isna(res):
            return True
        return close < float(res) * (1.0 - buf)
    sup = last.get("support")
    if sup is None or pd.isna(sup):
        return True
    return close > float(sup) * (1.0 + buf)


def _scalp_candle_ok(slice_df: pd.DataFrame, direction: str) -> bool:
    """Extra scalp quality: decisive close in trade direction."""
    last = slice_df.iloc[-1]
    if direction in ("long", "buy"):
        return _strong_bullish_close(last)
    return _strong_bearish_close(last)


def _limit_idea_decision(
    slice_df: pd.DataFrame,
    flags: TrendFlags,
) -> Optional[SignalDecision]:
    """Proximity LIM near S/R when ranging and no HTF trend (shared live/backtest)."""
    if flags.trend_up or flags.trend_down:
        return None
    if slice_df is None or len(slice_df) < 51:
        return None
    if not is_ranging(slice_df):
        return None
    last = slice_df.iloc[-1]
    close = float(last["close"])
    support = float(last["support"]) if pd.notna(last.get("support")) else close
    resistance = float(last["resistance"]) if pd.notna(last.get("resistance")) else close
    lim_pct = float(getattr(config, "LIMIT_IDEA_FALLBACK_PCT", 0.003))
    if close <= support * (1 + lim_pct):
        return SignalDecision(direction="long", strategy_type="range", signal_source="LIM")
    if close >= resistance * (1 - lim_pct):
        return SignalDecision(direction="short", strategy_type="range", signal_source="LIM")
    return None


def evaluate_signal_at_bar(
    slice_df: pd.DataFrame,
    htf_slice: pd.DataFrame,
    entry_price: float,
    *,
    include_limit_idea_fallback: Optional[bool] = None,
    include_breakout: bool = False,
) -> Optional[SignalDecision]:
    """
    Shared live/backtest decision.

    Primary (trend) — core 3 confirms:
      1) 1h HTF bias agrees
      2) 15m MA cross / pullback reclaim
      3) location clear of opposing S/R
      (+ optional mild ADX via MIN_ADX_TREND)

    Secondary (scalp) — counter-HTF, tighter TP via strategy_type=scalp:
      1) 15m MA trigger
      2) stronger location
      3) decisive candle
      4) explicitly against 1h bias
    """
    if slice_df is None or len(slice_df) < 51:
        return None
    flags = htf_trend_flags(htf_slice)
    if flags is None:
        return None

    if include_limit_idea_fallback is None:
        include_limit_idea_fallback = bool(
            getattr(config, "ENABLE_LIMIT_IDEA_FALLBACK", False)
        )
    allow_scalp = bool(getattr(config, "ENABLE_COUNTER_HTF_SCALP", True))

    adx_ok = _adx_ok(slice_df)
    long_trig = check_long_signal(slice_df)
    short_trig = check_short_signal(slice_df)

    # --- Primary: with-HTF trend ---
    if adx_ok and long_trig and flags.trend_up and _location_ok(slice_df, "long"):
        if setup_meets_min_rr(slice_df, entry_price, "long", "trend"):
            return SignalDecision("long", "trend", "SIG")
    if adx_ok and short_trig and flags.trend_down and _location_ok(slice_df, "short"):
        if setup_meets_min_rr(slice_df, entry_price, "short", "trend"):
            return SignalDecision("short", "trend", "SIG")

    # --- Secondary: against-HTF scalp (tighter targets) ---
    if allow_scalp:
        if (
            long_trig
            and flags.trend_down
            and _location_ok(slice_df, "long", strict=True)
            and _scalp_candle_ok(slice_df, "long")
        ):
            if setup_meets_min_rr(slice_df, entry_price, "long", "scalp"):
                return SignalDecision("long", "scalp", "SIG")
        if (
            short_trig
            and flags.trend_up
            and _location_ok(slice_df, "short", strict=True)
            and _scalp_candle_ok(slice_df, "short")
        ):
            if setup_meets_min_rr(slice_df, entry_price, "short", "scalp"):
                return SignalDecision("short", "scalp", "SIG")

    if include_breakout:
        if check_breakout_signal(slice_df, "long") and flags.trend_up:
            if setup_meets_min_rr(slice_df, entry_price, "long", "trend"):
                return SignalDecision("long", "breakout", "SIG")
        if check_breakout_signal(slice_df, "short") and flags.trend_down:
            if setup_meets_min_rr(slice_df, entry_price, "short", "trend"):
                return SignalDecision("short", "breakout", "SIG")

    if is_ranging(slice_df) and not flags.trend_up and not flags.trend_down:
        buy_signal, sell_signal = check_range_trade(slice_df)
        if buy_signal and setup_meets_min_rr(slice_df, entry_price, "long", "range"):
            return SignalDecision("long", "range", "SIG")
        if sell_signal and setup_meets_min_rr(slice_df, entry_price, "short", "range"):
            return SignalDecision("short", "range", "SIG")

    if include_limit_idea_fallback:
        return _limit_idea_decision(slice_df, flags)
    return None


def first_touch_on_bar(
    is_long: bool,
    tp: float,
    sl: float,
    high: float,
    low: float,
    *,
    same_bar: SameBarPolicy = "conservative_sl",
) -> Optional[Literal["win", "loss"]]:
    """Resolve one OHLC bar. Same-bar TP+SL → loss (conservative_sl)."""
    if is_long:
        hit_tp = high >= tp
        hit_sl = low <= sl
    else:
        hit_tp = low <= tp
        hit_sl = high >= sl
    if hit_tp and hit_sl:
        if same_bar == "conservative_sl":
            return "loss"
        return "loss"
    if hit_sl:
        return "loss"
    if hit_tp:
        return "win"
    return None


def first_touch_walk(
    is_long: bool,
    tp: float,
    sl: float,
    candles: Iterable[Any],
    *,
    high_idx: int = 2,
    low_idx: int = 3,
    same_bar: SameBarPolicy = "conservative_sl",
) -> Optional[tuple[Literal["win", "loss"], float]]:
    """
    Walk OHLCV rows (list-like [ts, o, h, l, c, ...]) in time order.
    Returns (result, exit_price) or None if neither level touched.
    """
    for row in candles:
        high = float(row[high_idx])
        low = float(row[low_idx])
        hit = first_touch_on_bar(is_long, tp, sl, high, low, same_bar=same_bar)
        if hit == "loss":
            return "loss", float(sl)
        if hit == "win":
            return "win", float(tp)
    return None


def resolve_outcome_on_df(
    df: pd.DataFrame,
    start_idx: int,
    direction: str,
    entry_price: float,
    tp: float,
    sl: float,
    *,
    max_lookahead: int,
    skip_entry_bar: bool = True,
    commission: float = 0.0,
    same_bar: SameBarPolicy = "conservative_sl",
) -> dict:
    """
    Shared bar-walk outcome used by backtest (and available for channel resolve).

    skip_entry_bar=True matches historical backtest (resolve from bar start_idx+1).
    PnL is returned as a **fraction** of entry (backtest convention).
    """
    is_long = direction_to_side(direction) == "buy"
    start = start_idx + (1 if skip_entry_bar else 0)
    end = min(len(df), start_idx + max_lookahead + 1)
    for j in range(start, end):
        high = float(df["high"].iat[j])
        low = float(df["low"].iat[j])
        hit = first_touch_on_bar(is_long, tp, sl, high, low, same_bar=same_bar)
        if hit == "win":
            if is_long:
                pnl = (tp - entry_price - commission) / entry_price
            else:
                pnl = (entry_price - tp - commission) / entry_price
            return {"result": "win", "pnl_pct": pnl, "tp": tp, "sl": sl}
        if hit == "loss":
            if is_long:
                pnl = (sl - entry_price - commission) / entry_price
            else:
                pnl = (entry_price - sl - commission) / entry_price
            return {"result": "loss", "pnl_pct": pnl, "tp": tp, "sl": sl}

    final_idx = min(len(df) - 1, start_idx + max_lookahead)
    final_close = float(df["close"].iat[final_idx])
    if is_long:
        pnl = (final_close - entry_price - commission) / entry_price
    else:
        pnl = (entry_price - final_close - commission) / entry_price
    return {"result": "none", "pnl_pct": pnl, "tp": tp, "sl": sl}
