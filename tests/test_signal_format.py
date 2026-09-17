"""Tests for Pro channel signal message formatting."""

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from utils.signalFormat import display_symbol, format_signal_message


class TestSignalFormat:
    def test_display_symbol_strips_settle_suffix(self):
        assert display_symbol("XRP/USDT:USDT") == "XRP/USDT"
        assert display_symbol("SUI/USDT") == "SUI/USDT"

    def test_compact_long_signal(self):
        msg = format_signal_message(
            symbol="XRP/USDT:USDT",
            direction="long",
            timeframe="15m",
            strategy_type="trend",
            entry=0.58,
            tp=0.5916,
            sl=0.5742,
            signal_source="SIG",
            limit_hint="<b>Limit</b>  0.5770  <i>(~0.52% below)</i>",
        )
        assert "📈 <b>LONG</b> · <b>XRP/USDT</b> · 15m" in msg
        assert "Trend ·" in msg
        assert "<b>Entry</b>" in msg
        assert "<b>TP</b>" in msg
        assert "<b>SL</b>" in msg
        assert "<b>R:R</b>" in msg
        assert "Limit" in msg
        # Noise removed
        assert "Src:" not in msg
        assert "SIGNAL for" not in msg
        assert "Signals only" not in msg
        assert "indicative" not in msg.lower()
        assert "Reference price" not in msg
        assert "/macro" not in msg

    def test_limit_source_label(self):
        msg = format_signal_message(
            symbol="SUI/USDT:USDT",
            direction="short",
            timeframe="5m",
            strategy_type="range",
            entry=1.5,
            tp=1.47,
            sl=1.52,
            signal_source="LIM",
        )
        assert "📉 <b>SHORT</b>" in msg
        assert "limit idea" in msg.lower()
