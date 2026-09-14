"""Tests for Pro channel quiet-period heartbeats."""

import os
import sys
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import config
from utils import channelHeartbeat as hb
from utils.signalTracker import build_quiet_day_eod_message


class TestQuietHeartbeat:
    def setup_method(self):
        hb.reset_heartbeat_state_for_tests()
        config.CHANNEL_HEARTBEAT_ENABLED = True
        config.CHANNEL_HEARTBEAT_AFTER_QUIET_HOURS = 8
        config.CHANNEL_HEARTBEAT_EVERY_HOURS = 8
        config.TRADING_ENABLED = True
        config.NIGHT_QUIET_ENABLED = False
        config.NIGHT_QUIET_ARMED = False

    def test_not_due_while_recent_signal(self):
        now = datetime(2026, 9, 14, 18, 0, tzinfo=timezone.utc)
        hb.note_signal_sent(now - timedelta(hours=2))
        assert hb.should_send_heartbeat(now) is False

    def test_due_after_quiet_window(self):
        now = datetime(2026, 9, 14, 18, 0, tzinfo=timezone.utc)
        hb.note_signal_sent(now - timedelta(hours=9))
        assert hb.should_send_heartbeat(now) is True

    def test_respects_interval_after_send(self):
        now = datetime(2026, 9, 14, 18, 0, tzinfo=timezone.utc)
        hb.note_signal_sent(now - timedelta(hours=20))
        sent = []
        assert hb.maybe_send_quiet_heartbeat(
            lambda *a, **k: sent.append(a[0]), now=now
        ) is True
        assert sent and "Still scanning" in sent[0]
        assert hb.should_send_heartbeat(now + timedelta(hours=1)) is False
        assert hb.should_send_heartbeat(now + timedelta(hours=9)) is True

    def test_skips_when_scanning_off(self):
        config.TRADING_ENABLED = False
        now = datetime(2026, 9, 14, 18, 0, tzinfo=timezone.utc)
        hb.note_signal_sent(now - timedelta(hours=20))
        assert hb.should_send_heartbeat(now) is False

    def test_skips_night_quiet(self):
        config.NIGHT_QUIET_ENABLED = True
        config.NIGHT_QUIET_ARMED = True
        with patch.object(config, "should_skip_cycle_for_night_quiet", return_value=True):
            now = datetime(2026, 9, 14, 23, 0, tzinfo=timezone.utc)
            hb.note_signal_sent(now - timedelta(hours=20))
            assert hb.should_send_heartbeat(now) is False

    def test_message_mentions_selectivity(self):
        msg = hb.build_heartbeat_message()
        assert "Still scanning" in msg
        assert "good" in msg.lower() or "selective" in msg.lower()


class TestQuietDayEod:
    def test_quiet_day_copy(self):
        msg = build_quiet_day_eod_message()
        assert "Signals today: <b>0</b>" in msg
        assert "offline" in msg.lower()
