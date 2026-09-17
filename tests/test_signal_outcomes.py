"""Tests for channel signal outcome follow-ups."""

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import config
from utils.signalTracker import (
    monitor_signal_outcomes,
    record_signal,
    reset_daily_signals,
    reset_open_signals_for_tests,
)


class TestSignalOutcomeMonitor:
    def setup_method(self):
        reset_daily_signals()
        reset_open_signals_for_tests()
        config.SIGNAL_OUTCOME_ALERTS_ENABLED = True

    def teardown_method(self):
        reset_daily_signals()
        reset_open_signals_for_tests()

    def test_posts_take_profit_follow_up(self):
        record_signal("XRP/USDT:USDT", "long", "trend", 1.0, 1.02, 0.99, timeframe="15m")
        exchange = MagicMock()
        # Force OHLCV path: one candle that tags TP
        exchange.fetch_ohlcv.return_value = [
            [int(datetime.now(timezone.utc).timestamp() * 1000), 1.0, 1.03, 0.995, 1.02, 10],
        ]
        sent = []

        closed = monitor_signal_outcomes(
            exchange=exchange,
            send_fn=lambda *a, **k: sent.append(a[0]),
        )
        assert len(closed) == 1
        assert closed[0]["result"] == "win"
        assert sent and "Take-profit hit" in sent[0]

    def test_disabled_skips(self):
        config.SIGNAL_OUTCOME_ALERTS_ENABLED = False
        record_signal("XRP/USDT:USDT", "long", "trend", 1.0, 1.02, 0.99)
        closed = monitor_signal_outcomes(exchange=MagicMock(), send_fn=lambda *a, **k: None)
        assert closed == []
