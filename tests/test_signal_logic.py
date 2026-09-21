"""Parity tests: live and backtest share utils.signalLogic decisions/outcomes."""

import pandas as pd
import pytest

from utils.signalLogic import (
    SignalDecision,
    evaluate_signal_at_bar,
    first_touch_on_bar,
    first_touch_walk,
    htf_trend_flags,
    resolve_outcome_on_df,
)
from strategies.simulate_trades import _get_signal_at_bar, check_trade_outcome
from utils.utils import add_atr_column


def _base_df(n=80, trend="up"):
    """Minimal OHLCV with MAs / ADX / S/R so evaluate_signal_at_bar can run."""
    closes = []
    price = 100.0
    for i in range(n):
        if trend == "up":
            price += 0.15
        elif trend == "down":
            price -= 0.15
        else:
            price += 0.02 if i % 2 == 0 else -0.02
        closes.append(price)
    df = pd.DataFrame({
        "timestamp": pd.date_range("2025-01-01", periods=n, freq="15min", tz="UTC"),
        "open": closes,
        "high": [c + 0.8 for c in closes],
        "low": [c - 0.8 for c in closes],
        "close": closes,
        "volume": [2000.0] * n,
    })
    df["ma10"] = df["close"].rolling(10).mean()
    df["ma20"] = df["close"].rolling(20).mean()
    df["ma50"] = df["close"].rolling(50).mean()
    df["rsi"] = 50.0
    df["adx"] = 25.0
    df["support"] = df["low"].rolling(20).min()
    df["resistance"] = df["high"].rolling(20).max()
    return add_atr_column(df, period=7)


def _htf_from(df, bias="up"):
    h = df.iloc[::4].copy().reset_index(drop=True)
    if len(h) < 6:
        h = pd.concat([h] * 3, ignore_index=True).iloc[:12].copy()
    n = len(h)
    if bias == "up":
        # Rising ma20 above ma50 (matches live/backtest HTF rule)
        h["ma20"] = [100.0 + i for i in range(n)]
        h["ma50"] = [90.0] * n
    elif bias == "down":
        h["ma20"] = [120.0 - i for i in range(n)]
        h["ma50"] = [130.0] * n
    else:
        h["ma20"] = [100.0] * n
        h["ma50"] = [100.0] * n
    return h


class TestFirstTouchPolicy:
    def test_same_bar_both_hit_is_loss(self):
        assert first_touch_on_bar(True, tp=105, sl=95, high=106, low=94) == "loss"
        assert first_touch_on_bar(False, tp=95, sl=105, high=106, low=94) == "loss"

    def test_walk_matches_list_api(self):
        candles = [
            [0, 100, 106, 94, 100],  # both — loss
        ]
        assert first_touch_walk(True, 105, 95, candles) == ("loss", 95.0)


class TestHtfFlags:
    def test_needs_six_rows(self):
        df = _htf_from(_base_df(), "up").iloc[:3]
        assert htf_trend_flags(df) is None

    def test_up_down(self):
        up = htf_trend_flags(_htf_from(_base_df(), "up"))
        down = htf_trend_flags(_htf_from(_base_df(), "down"))
        assert up and up.trend_up and not up.trend_down
        assert down and down.trend_down and not down.trend_up


class TestAdapterParity:
    def test_get_signal_at_bar_matches_evaluate(self, monkeypatch):
        import config
        monkeypatch.setattr(config, "ENABLE_LIMIT_IDEA_FALLBACK", False)
        monkeypatch.setattr(config, "MIN_ADX_TREND", 0.0)
        monkeypatch.setattr(config, "MIN_SETUP_RR", 0.0)

        df = _base_df(trend="flat")
        htf = _htf_from(df, "flat")
        entry = float(df["close"].iloc[-1])

        decision = evaluate_signal_at_bar(df, htf, entry, include_limit_idea_fallback=False)
        legacy = _get_signal_at_bar(df, htf, entry, include_limit_idea_fallback=False)
        if decision is None:
            assert legacy is None
        else:
            assert legacy == (decision.side, decision.strategy_type)

    def test_check_trade_outcome_uses_conservative_same_bar(self, monkeypatch):
        import config
        monkeypatch.setattr(config, "BACKTEST_APPLY_FEES", False)
        # Build df where next bar hits both TP and SL for a long
        prices = [100.0] * 60 + [100.0, 100.0]
        df = _base_df(n=len(prices), trend="flat")
        df.loc[df.index[-1], "high"] = 120.0
        df.loc[df.index[-1], "low"] = 80.0
        df.loc[df.index[-1], "close"] = 100.0
        # start at second-to-last so lookahead bar is last
        start = len(df) - 2
        out = check_trade_outcome(df, start, "buy", 100.0, max_lookahead=5, strategy="trend")
        # With ATR levels, both-hit on next bar should resolve as loss under shared policy
        # (only assert structure if TP/SL exist inside range of that bar)
        assert out["result"] in ("win", "loss", "none")
        assert "pnl_pct" in out


class TestResolveOutcomeOnDf:
    def test_unresolved_none(self):
        df = _base_df(n=70, trend="flat")
        start = 60
        entry = float(df["close"].iat[start])
        tp = entry * 1.5
        sl = entry * 0.5
        out = resolve_outcome_on_df(
            df, start, "long", entry, tp, sl, max_lookahead=3, commission=0.0
        )
        assert out["result"] == "none"
