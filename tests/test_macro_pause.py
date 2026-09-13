"""Tests for US macro calendar pause windows and Telegram alerts."""

import os
import sys
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import config
from utils import macroCalendar as mc


def _event(name, release_at):
    return {
        "name": name,
        "scheduled_at": release_at,
        "source": "bls",
        "period": "August 2026",
        "actual": None,
    }


class TestMacroPauseWindow:
    def setup_method(self):
        mc.reset_pause_notify_state()
        config.MACRO_PAUSE_ENABLED = True
        config.MACRO_PAUSE_ARMED = True
        config.MACRO_PAUSE_BEFORE_MIN = 30
        config.MACRO_PAUSE_AFTER_MIN = 120
        config.MACRO_PAUSE_NOTIFY = True

    def test_active_during_pre_release_window(self):
        release = datetime(2026, 9, 11, 12, 30, tzinfo=timezone.utc)
        now = release - timedelta(minutes=10)
        with patch.object(mc, "get_macro_events", return_value=[_event("CPI", release)]):
            pause = mc.active_macro_pause(now)
        assert pause is not None
        assert pause["name"] == "CPI"
        assert pause["before_release"] is True
        assert pause["remaining_sec"] > 0

    def test_active_after_release_until_resume(self):
        release = datetime(2026, 9, 11, 12, 30, tzinfo=timezone.utc)
        now = release + timedelta(minutes=60)
        with patch.object(mc, "get_macro_events", return_value=[_event("CPI", release)]):
            pause = mc.active_macro_pause(now)
        assert pause is not None
        assert pause["before_release"] is False
        assert abs(pause["remaining_sec"] - 3600) < 2

    def test_inactive_outside_window(self):
        release = datetime(2026, 9, 11, 12, 30, tzinfo=timezone.utc)
        now = release + timedelta(minutes=121)
        with patch.object(mc, "get_macro_events", return_value=[_event("CPI", release)]):
            assert mc.active_macro_pause(now) is None

    def test_disarmed_never_pauses(self):
        config.MACRO_PAUSE_ARMED = False
        release = datetime(2026, 9, 11, 12, 30, tzinfo=timezone.utc)
        now = release + timedelta(minutes=5)
        with patch.object(mc, "get_macro_events", return_value=[_event("NFP", release)]):
            assert mc.active_macro_pause(now) is None

    def test_telegram_pause_message_includes_resume_time(self):
        release = datetime(2026, 9, 11, 12, 30, tzinfo=timezone.utc)
        pause = {
            "name": "CPI (Consumer Price Index)",
            "release_at": release,
            "pause_start": release - timedelta(minutes=30),
            "resume_at": release + timedelta(minutes=120),
            "remaining_sec": 3600,
            "before_release": False,
            "event_key": "x|CPI",
            "period": "August 2026",
        }
        msg = mc.format_pause_telegram(pause)
        assert "Macro pause" in msg
        assert "CPI" in msg
        assert "2026-09-11 14:30 UTC" in msg
        assert "60m" in msg or "1h" in msg

    def test_notify_sends_pause_then_resume_once(self):
        release = datetime(2026, 9, 11, 12, 30, tzinfo=timezone.utc)
        events = [_event("Nonfarm Payrolls", release)]
        sent = []

        def fake_send(text, parse_mode=None, bypass_rate_limit=False):
            sent.append(text)

        with patch.object(mc, "get_macro_events", return_value=events):
            mid = release + timedelta(minutes=30)
            assert mc.notify_macro_pause_transitions(fake_send, mid) is not None
            assert len(sent) == 1
            assert "Macro pause" in sent[0]

            # Still paused — no second alert
            assert mc.notify_macro_pause_transitions(fake_send, mid) is not None
            assert len(sent) == 1

            # After window — resume alert once
            after = release + timedelta(minutes=121)
            assert mc.notify_macro_pause_transitions(fake_send, after) is None
            assert len(sent) == 2
            assert "Macro pause ended" in sent[1]


class TestMacroMorningWarn:
    def setup_method(self):
        mc.reset_pause_notify_state()
        config.MACRO_PAUSE_ENABLED = True
        config.MACRO_PAUSE_ARMED = True
        config.MACRO_PAUSE_NOTIFY = True
        config.MACRO_MORNING_WARN_ENABLED = True
        config.MACRO_MORNING_WARN_HOUR = 8
        config.MACRO_MORNING_WARN_TZ = "America/New_York"
        config.MACRO_PAUSE_BEFORE_MIN = 30
        config.MACRO_PAUSE_AFTER_MIN = 120

    def test_morning_warn_once_after_us_morning(self):
        # CPI typically 8:30 AM ET = 12:30 UTC in September (EDT, UTC-4)
        release = datetime(2026, 9, 11, 12, 30, tzinfo=timezone.utc)
        # 8:05 AM ET = 12:05 UTC
        morning = datetime(2026, 9, 11, 12, 5, tzinfo=timezone.utc)
        sent = []

        def fake_send(text, parse_mode=None, bypass_rate_limit=False):
            sent.append(text)

        with patch.object(mc, "get_macro_events", return_value=[_event("CPI", release)]):
            out = mc.notify_macro_morning_warnings(fake_send, morning)
            assert len(out) == 1
            assert len(sent) == 1
            assert "Macro heads-up" in sent[0]
            assert "CPI" in sent[0]
            # Second call same morning — no duplicate
            assert mc.notify_macro_morning_warnings(fake_send, morning) == []
            assert len(sent) == 1

    def test_no_warn_before_us_morning_hour(self):
        release = datetime(2026, 9, 11, 12, 30, tzinfo=timezone.utc)
        # 7:00 AM ET = 11:00 UTC
        early = datetime(2026, 9, 11, 11, 0, tzinfo=timezone.utc)
        sent = []

        def fake_send(text, parse_mode=None, bypass_rate_limit=False):
            sent.append(text)

        with patch.object(mc, "get_macro_events", return_value=[_event("CPI", release)]):
            assert mc.notify_macro_morning_warnings(fake_send, early) == []
            assert sent == []

    def test_no_warn_when_disarmed(self):
        config.MACRO_PAUSE_ARMED = False
        release = datetime(2026, 9, 11, 12, 30, tzinfo=timezone.utc)
        morning = datetime(2026, 9, 11, 12, 5, tzinfo=timezone.utc)
        sent = []

        def fake_send(text, parse_mode=None, bypass_rate_limit=False):
            sent.append(text)

        with patch.object(mc, "get_macro_events", return_value=[_event("CPI", release)]):
            assert mc.notify_macro_morning_warnings(fake_send, morning) == []
            assert sent == []


class TestMacroTelegramCommand:
    def setup_method(self):
        config.MACRO_PAUSE_ENABLED = True
        config.MACRO_PAUSE_ARMED = True

    def test_macro_help_in_commands(self):
        from utils.telegramUtils import handle_telegram_command
        response, mode = handle_telegram_command("/help")
        assert "/macro" in response
        assert mode == "HTML"

    def test_macro_off_on(self, monkeypatch):
        from utils.telegramUtils import handle_telegram_command

        monkeypatch.setattr(config, "_persist_runtime_config", lambda: None)
        response, _ = handle_telegram_command("/macro off")
        assert config.MACRO_PAUSE_ARMED is False
        assert "disarmed" in response.lower()

        response2, _ = handle_telegram_command("/macro on")
        assert config.MACRO_PAUSE_ARMED is True
        assert "armed" in response2.lower()
