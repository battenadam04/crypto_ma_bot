"""Tests for Pro channel signal message formatting."""

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from utils.signalFormat import (
    display_symbol,
    format_limit_hint,
    format_signal_guide,
    format_signal_message,
    format_signal_outcome_message,
)


class TestSignalFormat:
    def test_display_symbol_strips_settle_suffix(self):
        assert display_symbol("XRP/USDT:USDT") == "XRP/USDT"
        assert display_symbol("SUI/USDT") == "SUI/USDT"

    def test_beginner_friendly_long_signal(self):
        msg = format_signal_message(
            symbol="XRP/USDT:USDT",
            direction="long",
            timeframe="15m",
            strategy_type="trend",
            entry=0.58,
            tp=0.5916,
            sl=0.5742,
            signal_source="SIG",
            limit_hint=format_limit_hint(0.577, 0.52, "long"),
        )
        assert "📈 <b>LONG</b> · <b>XRP/USDT</b> · 15-min chart" in msg
        assert "🧭" in msg and "1-hour uptrend" in msg
        assert "💲" in msg and "Entry" in msg
        assert "🎯" in msg and "Take-profit" in msg
        assert "🛑" in msg and "Stop-loss" in msg
        assert "⚖️" in msg and "Reward/risk" in msg
        assert "📝" in msg and "Optional limit entry" in msg
        assert "🚫" in msg and "Invalidation" in msg
        assert "0.5–1%" in msg or "0.5-1%" in msg
        assert "not to buy at market" in msg
        assert "1h up" not in msg
        assert "Src:" not in msg

    def test_guide_and_outcome_copy(self):
        guide = format_signal_guide()
        assert "How to read" in guide
        assert "Invalidation" in guide
        assert "/macro" not in guide

        win = format_signal_outcome_message(
            {"symbol": "XRP/USDT:USDT", "direction": "long", "entry": 0.58, "tp": 0.59, "sl": 0.57},
            "win",
            2.0,
        )
        assert "Take-profit hit" in win
        assert "XRP/USDT" in win
