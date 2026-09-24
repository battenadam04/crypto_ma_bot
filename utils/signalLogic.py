"""Shared live + backtest signal decision and first-touch outcome logic.

Both `bot.process_pair` and `strategies.simulate_trades` must call these helpers
so scan path, LIM/breakout gates, and same-bar TP/SL policy cannot drift.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Literal, Optional

import pandas as pd

import config
from utils.utils import (
    add_atr_column,
    calculate_trade_levels,
    check_breakout_signal,
    check_long_signal,
    check_range_trade,
    check_short_signal,
    is_ranging,
)

Direction = Literal["long", "short"]
Side = Literal["buy", "sell"]
StrategyType = Literal["trend", "range", "breakout"]
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


def htf_trend_flags(htf_slice: pd.DataFrame) -> Optional[TrendFlags]:
    """HTF bias used by live and backtest. Needs ≥6 rows with ma20/ma50."""
    if htf_slice is None or len(htf_slice) < 6:
        return None
    if "ma20" not in htf_slice.columns or "ma50" not in htf_slice.columns:
        return None
    ma20_last = htf_slice["ma20"].iloc[-1]
    ma50_last = htf_slice["ma50"].iloc[-1]
    ma20_prev5 = htf_slice["ma20"].iloc[-5]
    ma20_prev4 = htf_slice["ma20"].iloc[-4]
    if pd.isna(ma20_last) or pd.isna(ma50_last) or pd.isna(ma20_prev5) or pd.isna(ma20_prev4):
        return None
    ma20_slope = float(ma20_last) - float(ma20_prev4)
    trend_up = (
        float(ma20_last) > float(ma50_last)
        and float(ma20_last) > float(ma20_prev5)
        and ma20_slope > 0
    )
    trend_down = (
        float(ma20_last) < float(ma50_last)
        and float(ma20_last) < float(ma20_prev5)
        and ma20_slope < 0
    )
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
    """Reject setups whose indicative TP/SL offer weak reward:risk."""
    try:
        levels = levels_for_signal(
            entry_price, direction, slice_df, len(slice_df) - 1, strategy_type
        )
        threshold = float(min_rr if min_rr is not None else config.MIN_SETUP_RR)
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
    include_breakout: bool = True,
) -> Optional[SignalDecision]:
    """
    Single bar signal decision for live and backtest.

    Priority (matches former live `process_pair`):
      trend SIG → breakout SIG → range SIG → optional LIM
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

    adx_ok = _adx_ok(slice_df)

    if adx_ok and check_long_signal(slice_df) and flags.trend_up:
        if setup_meets_min_rr(slice_df, entry_price, "long", "trend"):
            return SignalDecision("long", "trend", "SIG")
    if adx_ok and check_short_signal(slice_df) and flags.trend_down:
        if setup_meets_min_rr(slice_df, entry_price, "short", "trend"):
            return SignalDecision("short", "trend", "SIG")

    if include_breakout:
        # RR gate uses trend levels (legacy live behaviour); alert/backtest use breakout levels.
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
