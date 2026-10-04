"""Rolling walk-forward windows for the live watchlist.

Window sizes follow claude-trading-skills/skills/walk-forward-validation for an
intraday 15m/1h book: a fixed recent train, a short untouched test, and an
embargo at least twice the trade label horizon so a research trade cannot
resolve inside the holdout.
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from typing import Optional

import pandas as pd

import config
from utils.signalLogic import backtest_result_qualifies


def _as_utc(ts: datetime) -> datetime:
    if ts.tzinfo is None:
        return ts.replace(tzinfo=timezone.utc)
    return ts.astimezone(timezone.utc)


def promotion_windows(now: Optional[datetime] = None) -> dict:
    """Calendar bounds for one rolling fold ending at `now`."""
    end = _as_utc(now or datetime.now(timezone.utc)).replace(microsecond=0)
    test_days = int(config.WALK_FORWARD_TEST_DAYS)
    train_days = int(config.WALK_FORWARD_TRAIN_DAYS)
    embargo_hours = int(config.WALK_FORWARD_EMBARGO_HOURS)
    test_start = end - timedelta(days=test_days)
    train_end = test_start - timedelta(hours=embargo_hours)
    train_start = train_end - timedelta(days=train_days)
    return {
        "window_type": "rolling",
        "train_days": train_days,
        "test_days": test_days,
        "embargo_hours": embargo_hours,
        "train_start": train_start,
        "train_end": train_end,
        "test_start": test_start,
        "test_end": end,
    }


def promotion_fetch_days() -> int:
    """Bars to request so the train window has indicator warmup before it."""
    embargo_days = float(config.WALK_FORWARD_EMBARGO_HOURS) / 24.0
    span = (
        float(config.WALK_FORWARD_TRAIN_DAYS)
        + float(config.WALK_FORWARD_TEST_DAYS)
        + embargo_days
        + 4.0
    )
    return max(int(config.BACKTEST_DAYS), int(math.ceil(span)))


def bar_timestamp(ts) -> pd.Timestamp:
    t = pd.Timestamp(ts)
    if t.tzinfo is None:
        return t.tz_localize("UTC")
    return t.tz_convert("UTC")


def in_entry_window(ts, entry_start, entry_end) -> bool:
    """True when a bar may open a trade. Bounds are [start, end)."""
    if entry_start is None and entry_end is None:
        return True
    t = bar_timestamp(ts)
    if entry_start is not None and t < bar_timestamp(entry_start):
        return False
    if entry_end is not None and t >= bar_timestamp(entry_end):
        return False
    return True


def frame_covers_train(df: pd.DataFrame, train_start) -> bool:
    """False when the listing does not reach the start of the research window."""
    if df is None or len(df) == 0 or "timestamp" not in df.columns:
        return False
    return bool(bar_timestamp(df["timestamp"].iloc[0]) <= bar_timestamp(train_start))


def holdout_result_qualifies(result) -> bool:
    """Untouched-window gate. Research win rate does not apply here."""
    if not isinstance(result, dict):
        return False
    try:
        trades = int(result.get("total_trades") or 0)
        pf = float(result.get("profit_factor"))
        net = float(result.get("net_pnl_pct"))
    except (TypeError, ValueError):
        return False
    n_min = int(config.WALK_FORWARD_HOLDOUT_MIN_TRADES)
    pf_min = float(config.WALK_FORWARD_HOLDOUT_MIN_PF)
    pf_ok = math.isinf(pf) or pf >= pf_min
    return trades >= n_min and pf_ok and net > 0


def promote_from_results(results: dict, portfolio_holdout: Optional[dict]) -> tuple[list, dict]:
    """Pairs that pass research and holdout, then the book-level holdout check."""
    candidates = []
    if isinstance(results, dict):
        for sym, row in results.items():
            if not isinstance(sym, str) or not isinstance(row, dict):
                continue
            if backtest_result_qualifies(row) and holdout_result_qualifies(row.get("holdout")):
                candidates.append(sym)

    windows = {}
    net = None
    pf = None
    trades = None
    if isinstance(portfolio_holdout, dict):
        net = portfolio_holdout.get("net_pnl_pct")
        pf = portfolio_holdout.get("profit_factor")
        trades = portfolio_holdout.get("trades")

    stood_down = False
    reason = ""
    if not candidates:
        stood_down = True
        reason = (
            "No pair passed the research gate and a positive untouched holdout."
        )
    else:
        try:
            net_val = float(net)
        except (TypeError, ValueError):
            net_val = 0.0
        if net_val <= 0:
            stood_down = True
            reason = "Combined holdout is not net positive. The book is off."
            candidates = []

    return candidates, {
        "stood_down": stood_down,
        "reason": reason,
        "portfolio_holdout_net_pnl_pct": net,
        "portfolio_holdout_profit_factor": pf,
        "portfolio_holdout_trades": trades,
        "windows": windows,
    }
